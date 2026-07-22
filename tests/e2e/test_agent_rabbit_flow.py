"""Broker integration test for the scripulya_agent publish wiring.

The gateway is now fire-and-forget: `submit()` publishes an LLMRequest to
llm.agent.request (correlated by chat_id) and returns immediately. This test
verifies that publish using a TestRabbitBroker, with a stand-in subscriber on the
request queue (the real consumer is the separate scripulya_agent process).

The result side (llm.agent.result -> append_model_message -> SSE) is covered by the
unit tests for MessageService.append_model_message and ChatEventGateway, and by the
manual end-to-end check in the plan's verification section (it requires a DB).
"""

import logging
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from dishka.integrations.faststream import setup_dishka
from faststream.rabbit import TestRabbitBroker

from src.application.ports import LLMModelType, LLMRequest, UserMessageDTO
from src.conf import settings
from src.controllers.rabbit.v1 import llm as rabbit_llm  # noqa: F401  registers the result subscriber
from src.controllers.rabbit.v1.broker import broker
from src.domain.models import ChatRoles
from src.infrastructure.di import create_container
from src.infrastructure.exceptions import LLMGatewayException
from src.infrastructure.gateways.scripulya_agent_gateway import ScripulyaAgentClient, ScripulyaAgentGateway


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_submit_publishes_to_request_queue_via_broker():
	"""submit() publishes the LLMRequest to llm.agent.request, correlated by chat_id."""
	container = create_container()
	setup_dishka(container=container, broker=broker, auto_inject=True)

	captured: dict[str, LLMRequest] = {}

	async def fake_agent(req: LLMRequest) -> None:
		"""Stand-in for scripulya_agent: capture the published request."""
		captured["req"] = req

	# Register the stand-in on the request queue (FastStream's TestRabbitBroker
	# otherwise raises SubscriberNotFound for publishes to a queue with no subscriber).
	broker.subscriber(settings.LLM_AGENT_REQUEST_QUEUE)(fake_agent)

	try:
		# Construct the client with a mock heartbeat so this test exercises only the
		# publish wiring (the real client's heartbeat hits Redis — covered elsewhere).
		client = ScripulyaAgentClient(
			broker=broker,
			request_queue=settings.LLM_AGENT_REQUEST_QUEUE,
			timeout=settings.LLM_AGENT_TIMEOUT,
			logger=logging.getLogger("test"),
			heartbeat=AsyncMock(),
		)
		gateway = ScripulyaAgentGateway(logger=logging.getLogger("test"), _client=client)
		msg = UserMessageDTO(
			chat_id=uuid4(), message="hi", llm_model=LLMModelType.gemini_flash_preview, role=ChatRoles.USER
		)

		async with TestRabbitBroker(broker):
			resp = await gateway.submit(msg, [])

		assert resp is None  # fire-and-forget
		assert captured["req"].message.chat_id == msg.chat_id
		assert captured["req"].message.message == "hi"
	finally:
		await container.close()


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_publish_failure_wraps_as_llm_gateway_exception():
	"""A broker publish failure (broker down / confirm timeout) is wrapped as
	LLMGatewayException carrying the chat_id — never raised raw. send_message catches
	BaseAPIException to record a FAILED turn and return 202 instead of 5xx-ing, so a raw
	RuntimeError here would bypass that recovery path."""
	chat_id = uuid4()
	failing_broker = AsyncMock()
	failing_broker.publish.side_effect = RuntimeError("broker unreachable")

	client = ScripulyaAgentClient(
		broker=failing_broker,
		request_queue=settings.LLM_AGENT_REQUEST_QUEUE,
		timeout=settings.LLM_AGENT_TIMEOUT,
		logger=logging.getLogger("test"),
		heartbeat=AsyncMock(),
	)
	req = LLMRequest(
		message=UserMessageDTO(
			chat_id=chat_id, message="hi", llm_model=LLMModelType.gemini_flash_preview, role=ChatRoles.USER
		),
		history=[],
	)

	with pytest.raises(LLMGatewayException) as exc_info:
		await client.publish(req)

	assert exc_info.value.details["chat_id"] == str(chat_id)
