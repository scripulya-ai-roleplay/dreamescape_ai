import pytest
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from src.application.ports import (
	LLMModelType,
	LLMRequest,
	UserMessageDTO,
)
from src.domain.models import ChatRoles
from src.infrastructure.exceptions import LLMGatewayException
from src.infrastructure.gateways.scripulya_agent_gateway import (
	ScripulyaAgentClient,
	ScripulyaAgentGateway,
)


def _user_message(text: str = "hello", model: LLMModelType = LLMModelType.gemini_flash_preview) -> UserMessageDTO:
	return UserMessageDTO(chat_id=uuid4(), message=text, llm_model=model, role=ChatRoles.USER)


@pytest.mark.unit
class TestScripulyaAgentGateway:
	"""Unit tests for ScripulyaAgentGateway (client mocked; no broker)."""

	@pytest.fixture
	def mock_client(self):
		client = Mock()
		client.publish = AsyncMock()
		return client

	@pytest.fixture
	def mock_logger(self):
		return Mock()

	@pytest.fixture
	def gateway(self, mock_client, mock_logger):
		return ScripulyaAgentGateway(logger=mock_logger, _client=mock_client)

	@pytest.mark.asyncio
	async def test_submit_publishes_request_envelope_and_returns_none(self, gateway, mock_client):
		msg = _user_message("hello")

		resp = await gateway.submit(msg, history=[])

		assert resp is None  # fire-and-forget: reply arrives via the result subscriber
		req: LLMRequest = mock_client.publish.await_args.args[0]
		assert req.message == msg
		assert req.history == []

	@pytest.mark.asyncio
	async def test_submit_forwards_history(self, gateway, mock_client):
		msg = _user_message()
		prior = _user_message("earlier turn")

		await gateway.submit(msg, history=[prior])

		req: LLMRequest = mock_client.publish.await_args.args[0]
		assert req.history == [prior]

	@pytest.mark.asyncio
	async def test_submit_propagates_publish_error(self, gateway, mock_client):
		mock_client.publish.side_effect = LLMGatewayException(message="boom", details={})

		with pytest.raises(LLMGatewayException):
			await gateway.submit(_user_message(), history=[])


@pytest.mark.unit
class TestScripulyaAgentClient:
	"""Unit tests for the fire-and-forget publisher (fake broker)."""

	@pytest.fixture
	def fake_broker(self):
		broker = Mock()
		broker.publish = AsyncMock()
		return broker

	@pytest.fixture
	def client(self, fake_broker):
		return ScripulyaAgentClient(broker=fake_broker, request_queue="llm.agent.request", timeout=5.0, logger=Mock())

	@pytest.mark.asyncio
	async def test_publish_correlates_by_chat_id(self, client, fake_broker):
		msg = _user_message()
		req = LLMRequest(message=msg, history=[])

		await client.publish(req)

		fake_broker.publish.assert_awaited_once()
		args, kwargs = fake_broker.publish.await_args
		payload, queue = args
		assert queue == "llm.agent.request"
		assert payload == req.model_dump(mode="json")
		assert kwargs["correlation_id"] == str(msg.chat_id)
		assert kwargs["timeout"] == 5.0

	@pytest.mark.asyncio
	async def test_publish_wraps_failure_in_gateway_exception(self, client, fake_broker):
		fake_broker.publish.side_effect = RuntimeError("broker down")

		with pytest.raises(LLMGatewayException) as exc_info:
			await client.publish(LLMRequest(message=_user_message(), history=[]))

		assert "failed to publish" in exc_info.value.message
