import pytest
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from src.application.ports import (
	LLMErrorResponse,
	LLMModelType,
	LLMRequest,
	LLMResult,
	UserMessageDTO,
)
from src.domain.models import ChatRoles
from src.infrastructure.exceptions import (
	ContentSafetyException,
	JSONParsingException,
	LLMGatewayException,
	RateLimitException,
)
from src.infrastructure.gateways.scripulya_agent_gateway import (
	ScripulyaAgentClient,
	ScripulyaAgentGateway,
)


def _user_message(text: str = "hello", model: LLMModelType = LLMModelType.gemini_flash_preview) -> UserMessageDTO:
	return UserMessageDTO(chat_id=uuid4(), message=text, llm_model=model, role=ChatRoles.USER)


def _result(chat_id, message=None, error=None) -> LLMResult:
	return LLMResult(chat_id=chat_id, message=message, error=error)


@pytest.mark.unit
class TestScripulyaAgentGateway:
	"""Unit tests for ScripulyaAgentGateway (client mocked; no broker)."""

	@pytest.fixture
	def mock_client(self):
		client = Mock()
		client.request = AsyncMock()
		return client

	@pytest.fixture
	def mock_logger(self):
		return Mock()

	@pytest.fixture
	def gateway(self, mock_client, mock_logger):
		return ScripulyaAgentGateway(logger=mock_logger, _client=mock_client)

	@pytest.mark.asyncio
	async def test_success_maps_to_llm_response(self, gateway, mock_client):
		msg = _user_message("hello")
		reply = UserMessageDTO(chat_id=msg.chat_id, message="hi there", llm_model=msg.llm_model, role=ChatRoles.MODEL)
		mock_client.request.return_value = _result(msg.chat_id, message=reply)

		resp = await gateway.generate_response(msg, history=[])

		assert resp.text == "hi there"
		assert resp.model == LLMModelType.gemini_flash_preview
		assert resp.provider == "scripulya_agent"
		# request envelope carries the full message + history
		req: LLMRequest = mock_client.request.await_args.args[0]
		assert req.message == msg
		assert req.history == []

	@pytest.mark.asyncio
	async def test_history_is_forwarded(self, gateway, mock_client):
		msg = _user_message()
		prior = _user_message("earlier turn")
		mock_client.request.return_value = _result(
			msg.chat_id,
			message=UserMessageDTO(chat_id=msg.chat_id, message="ok", llm_model=msg.llm_model, role=ChatRoles.MODEL),
		)
		await gateway.generate_response(msg, history=[prior])

		req: LLMRequest = mock_client.request.await_args.args[0]
		assert req.history == [prior]

	@pytest.mark.asyncio
	@pytest.mark.parametrize(
		"code,expected",
		[
			("rate_limit_exceeded", RateLimitException),
			("content_safety_blocked", ContentSafetyException),
			("response_is_invalid", JSONParsingException),
			("provider_auth_failed", LLMGatewayException),
			("model_is_unknown", LLMGatewayException),
			("model_is_inaccessible", LLMGatewayException),
			("internal_error", LLMGatewayException),
			("some_unknown_code", LLMGatewayException),
		],
	)
	async def test_error_code_mapping(self, gateway, mock_client, code, expected):
		msg = _user_message()
		mock_client.request.return_value = _result(
			msg.chat_id,
			error=LLMErrorResponse(error_code=code, status=500, reason="r", message="m", provider="x"),
		)

		with pytest.raises(expected) as exc_info:
			await gateway.generate_response(msg, history=[])

		# original agent error_code/status preserved
		assert exc_info.value.details["agent_error_code"] == code
		assert exc_info.value.details["agent_status"] == 500

	@pytest.mark.asyncio
	async def test_null_message_and_no_error_raises(self, gateway, mock_client):
		msg = _user_message()
		mock_client.request.return_value = _result(msg.chat_id, message=None, error=None)

		with pytest.raises(LLMGatewayException):
			await gateway.generate_response(msg, history=[])


@pytest.mark.unit
class TestScripulyaAgentClient:
	"""Unit tests for the publish/await/resolve RPC client (fake broker)."""

	@pytest.fixture
	def fake_broker(self):
		broker = Mock()
		broker.publish = AsyncMock()
		return broker

	@pytest.fixture
	def client(self, fake_broker):
		return ScripulyaAgentClient(broker=fake_broker, request_queue="llm.agent.request", timeout=0.1, logger=Mock())

	@pytest.mark.asyncio
	async def test_request_is_resolved_by_chat_id(self, client, fake_broker):
		msg = _user_message()
		req = LLMRequest(message=msg, history=[])
		result = _result(
			msg.chat_id,
			message=UserMessageDTO(chat_id=msg.chat_id, message="ok", llm_model=msg.llm_model, role=ChatRoles.MODEL),
		)

		# simulate the subscriber resolving the result right after publish
		async def fake_publish(*args, **kwargs):
			client.resolve(result)

		fake_broker.publish.side_effect = fake_publish

		got = await client.request(req)

		assert got is result
		fake_broker.publish.assert_awaited_once()
		assert fake_broker.publish.await_args.kwargs["correlation_id"] == str(msg.chat_id)

	@pytest.mark.asyncio
	async def test_request_times_out(self, client, fake_broker):
		msg = _user_message()
		# publish succeeds but nothing ever resolves the future
		fake_broker.publish.return_value = None

		with pytest.raises(LLMGatewayException) as exc_info:
			await client.request(LLMRequest(message=msg, history=[]))

		assert "timed out" in exc_info.value.message

	@pytest.mark.asyncio
	async def test_resolve_without_pending_is_noop(self, client):
		# a late/duplicate result with no awaiting request must not raise
		client.resolve(_result(uuid4()))
