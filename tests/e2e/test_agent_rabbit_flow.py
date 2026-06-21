"""In-memory broker integration test for the scripulya_agent client/gateway wiring.

Full round trip without a real RabbitMQ or scripulya_agent process:
  gateway.publish(llm.agent.request) -> stand-in agent subscriber replies
  -> llm.agent.result subscriber resolves the client -> gateway returns.

A stand-in subscriber is registered on llm.agent.request because scripulya_ai is a
*client* of that queue (the real consumer is the separate scripulya_agent process);
FastStream's TestRabbitBroker otherwise raises SubscriberNotFound for publishes to a
queue with no local subscriber.
"""

import asyncio
import logging
from uuid import uuid4

import pytest
from dishka.integrations.faststream import setup_dishka
from faststream.rabbit import TestRabbitBroker

from src.application.ports import LLMModelType, LLMRequest, LLMResult, UserMessageDTO
from src.conf import settings
from src.controllers.rabbit.v1 import llm as rabbit_llm  # noqa: F401  registers the result subscriber
from src.controllers.rabbit.v1.broker import broker
from src.domain.models import ChatRoles
from src.infrastructure.di import create_container
from src.infrastructure.gateways.scripulya_agent_gateway import ScripulyaAgentClient, ScripulyaAgentGateway


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_request_result_roundtrip_via_broker():
	"""The gateway request is answered via the broker and mapped back to an LLMResponse."""
	container = create_container()
	setup_dishka(container=container, broker=broker, auto_inject=True)

	async def fake_agent(req: LLMRequest) -> None:
		"""Stand-in for scripulya_agent: echo a correlated LLMResult to the result queue."""
		reply = UserMessageDTO(
			chat_id=req.message.chat_id, message="hello back", llm_model=req.message.llm_model, role=ChatRoles.MODEL
		)
		await broker.publish(
			LLMResult(chat_id=req.message.chat_id, message=reply).model_dump(mode="json"),
			settings.LLM_AGENT_RESULT_QUEUE,
		)

	# Register the stand-in on the request queue (idempotent-ish; this is the only e2e
	# broker test, so registering once per session is acceptable).
	broker.subscriber(settings.LLM_AGENT_REQUEST_QUEUE)(fake_agent)

	try:
		client = await container.get(ScripulyaAgentClient)
		gateway = ScripulyaAgentGateway(logger=logging.getLogger("test"), _client=client)
		msg = UserMessageDTO(
			chat_id=uuid4(), message="hi", llm_model=LLMModelType.gemini_flash_preview, role=ChatRoles.USER
		)

		async with TestRabbitBroker(broker):
			resp = await asyncio.wait_for(gateway.generate_response(msg, []), timeout=5)

		assert resp.text == "hello back"
		assert resp.model == LLMModelType.gemini_flash_preview
		assert resp.provider == "scripulya_agent"
	finally:
		await container.close()
