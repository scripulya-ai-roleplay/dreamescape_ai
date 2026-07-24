from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest

from src.application.ports.chats import IChatEventGateway
from src.application.ports.llm import LLMModelType, LLMRequest, UserMessageDTO
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
	def heartbeat(self):
		return AsyncMock()

	@pytest.fixture
	def client(self, fake_broker, heartbeat):
		return ScripulyaAgentClient(
			broker=fake_broker,
			request_queue="llm.agent.request",
			timeout=5.0,
			logger=Mock(),
			heartbeat=heartbeat,
		)

	@pytest.mark.asyncio
	async def test_publish_correlates_by_request_id_and_registers_heartbeat(
		self, client, fake_broker, heartbeat, monkeypatch
	):
		fixed_rid = UUID("11111111-2222-3333-4444-555555555555")
		monkeypatch.setattr("src.infrastructure.gateways.scripulya_agent_gateway.uuid4", lambda: fixed_rid)
		msg = _user_message()
		req = LLMRequest(message=msg, history=[])

		await client.publish(req)

		fake_broker.publish.assert_awaited_once()
		args, kwargs = fake_broker.publish.await_args
		payload, queue = args
		assert queue == "llm.agent.request"
		assert payload == req.model_dump(mode="json")
		assert kwargs["correlation_id"] == str(fixed_rid)  # per-call request_id, not chat_id
		assert kwargs["correlation_id"] != str(msg.chat_id)
		assert kwargs["timeout"] == 5.0
		heartbeat.register_inflight.assert_awaited_once_with(str(fixed_rid), msg.chat_id)

	@pytest.mark.asyncio
	async def test_publish_wraps_failure_and_skips_heartbeat(self, client, fake_broker, heartbeat):
		fake_broker.publish.side_effect = RuntimeError("broker down")

		with pytest.raises(LLMGatewayException) as exc_info:
			await client.publish(LLMRequest(message=_user_message(), history=[]))

		assert "failed to publish" in exc_info.value.message
		heartbeat.register_inflight.assert_not_awaited()


@pytest.mark.unit
class TestTokenRelay:
	"""Per-token streaming relay: subscribe on publish, drain Redis frames into SSE events."""

	@pytest.mark.asyncio
	async def test_publish_starts_relay_when_redis_and_events_present(self, monkeypatch):
		fixed_rid = UUID("11111111-2222-3333-4444-555555555555")
		monkeypatch.setattr("src.infrastructure.gateways.scripulya_agent_gateway.uuid4", lambda: fixed_rid)

		client = ScripulyaAgentClient(
			broker=AsyncMock(),
			request_queue="llm.agent.request",
			timeout=5.0,
			logger=Mock(),
			heartbeat=AsyncMock(),
			redis=Mock(),
			events=Mock(spec=IChatEventGateway),
		)
		client._start_token_relay = AsyncMock()

		msg = _user_message()
		await client.publish(LLMRequest(message=msg, history=[]))

		client._start_token_relay.assert_awaited_once_with(str(fixed_rid), msg.chat_id)

	@pytest.mark.asyncio
	async def test_publish_skips_relay_without_redis(self, monkeypatch):
		# Default client (no redis/events) must not attempt a relay.
		client = ScripulyaAgentClient(
			broker=AsyncMock(),
			request_queue="llm.agent.request",
			timeout=5.0,
			logger=Mock(),
			heartbeat=AsyncMock(),
		)
		await client.publish(LLMRequest(message=_user_message(), history=[]))
		assert client._relays == set()

	@pytest.mark.asyncio
	async def test_drain_relays_token_frames_then_terminal_close(self):
		events = Mock(spec=IChatEventGateway)
		client = ScripulyaAgentClient(
			broker=AsyncMock(),
			request_queue="llm.agent.request",
			timeout=5.0,
			logger=Mock(),
			heartbeat=AsyncMock(),
			events=events,
		)
		chat_id = uuid4()
		request_id = uuid4()

		pubsub = _FakePubSub(
			[
				{"type": "message", "data": '{"type": "token", "text": "Hel"}'},
				{"type": "message", "data": '{"type": "token", "text": "lo"}'},
				{"type": "message", "data": '{"type": "token", "text": " world"}'},
				{"type": "message", "data": '{"type": "done"}'},
			]
		)

		await client._drain_tokens(pubsub, str(request_id), chat_id)

		events.publish_generation_start.assert_called_once_with(chat_id, request_id)
		delivered = "".join(call.args[2] for call in events.publish_token.call_args_list)
		assert delivered == "Hello world"
		for call in events.publish_token.call_args_list:
			assert call.args[0] == chat_id
			assert call.args[1] == request_id
		events.publish_generation_done.assert_called_once_with(chat_id, request_id)
		assert pubsub.closed is True

	@pytest.mark.asyncio
	async def test_drain_flushes_buffer_on_error_terminal(self):
		events = Mock(spec=IChatEventGateway)
		client = ScripulyaAgentClient(
			broker=AsyncMock(),
			request_queue="llm.agent.request",
			timeout=5.0,
			logger=Mock(),
			heartbeat=AsyncMock(),
			events=events,
		)
		pubsub = _FakePubSub(
			[
				{"type": "message", "data": '{"type": "token", "text": "partial"}'},
				{"type": "message", "data": '{"type": "error"}'},
			]
		)
		await client._drain_tokens(pubsub, str(uuid4()), uuid4())

		delivered = "".join(call.args[2] for call in events.publish_token.call_args_list)
		assert delivered == "partial"
		events.publish_generation_done.assert_called_once()


class _FakePubSub:
	"""Minimal async pubsub: yields queued frames, then None forever; records close()."""

	def __init__(self, frames):
		self._frames = list(frames)
		self.closed = False

	async def get_message(self, ignore_subscribe_messages=False, timeout=None):  # noqa: ARG002
		if self._frames:
			return self._frames.pop(0)
		return None

	async def aclose(self):
		self.closed = True
