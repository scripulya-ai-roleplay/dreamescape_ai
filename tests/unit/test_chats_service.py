import pytest
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

from src.application.chats.llm_service import LLMChatsService
from src.application.ports import (
	UserMessageDTO,
	LLMModelType,
	LLMResponse,
	IGatewayFactory,
	ILLMChatGateway,
	IMessageGateway,
	IUnitOfWork,
	Page,
	SendMessageResult,
)
from src.domain.models import ChatRoles, Message, MessageStatus
from src.infrastructure.web.chat_event_broker import ChatEventBroker


def _persist(message: Message) -> Message:
	"""Stand-in for the gateway's create(): echo back with a generated id."""
	return Message(
		id=uuid4(),
		message=message.message,
		chat_id=message.chat_id,
		role=message.role,
		status=message.status,
	)


class TestChatsService:
	@pytest.fixture
	def mock_gateway(self):
		"""Mock LLM gateway. submit() returns None by default (async agent path)."""
		gateway = AsyncMock(spec=ILLMChatGateway)
		gateway.submit.return_value = None
		return gateway

	@pytest.fixture
	def mock_gateway_factory(self, mock_gateway):
		factory = MagicMock(spec=IGatewayFactory)
		factory.create_gateway.return_value = mock_gateway
		return factory

	@pytest.fixture
	def mock_messages_gateway(self):
		gateway = AsyncMock(spec=IMessageGateway)
		gateway.search.return_value = Page[Message](items=[], count=0, offset=0, limit=10)
		gateway.create.side_effect = _persist
		return gateway

	@pytest.fixture
	def mock_uow(self):
		uow = AsyncMock(spec=IUnitOfWork)
		uow.__aenter__ = AsyncMock(return_value=None)
		uow.__aexit__ = AsyncMock(return_value=False)
		return uow

	@pytest.fixture
	def mock_events(self):
		return Mock(spec=ChatEventBroker)

	@pytest.fixture
	def chats_service(self, mock_gateway_factory, mock_messages_gateway, mock_uow, mock_events):
		return LLMChatsService(
			gateway_factory=mock_gateway_factory,
			messages_gateway=mock_messages_gateway,
			_uow=mock_uow,
			_events=mock_events,
		)

	@pytest.fixture
	def sample_chat_id(self):
		return uuid4()

	@pytest.fixture
	def sample_user_message_dto(self, sample_chat_id):
		return UserMessageDTO(
			message="Hello, how are you?",
			llm_model=LLMModelType.gemini_flash_preview,
			chat_id=sample_chat_id,
			role=ChatRoles.USER,
		)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_async_path_returns_pending_placeholder(
		self, chats_service, mock_gateway, mock_messages_gateway, mock_events, sample_user_message_dto
	):
		"""Fire-and-forget gateway: returns the user message + a PENDING model message,
		does not resolve inline or notify SSE."""
		result = await chats_service.send_message(sample_user_message_dto)

		assert isinstance(result, SendMessageResult)
		assert result.user_message.message == "Hello, how are you?"
		assert result.user_message.role == ChatRoles.USER
		assert result.user_message.status == MessageStatus.COMPLETED
		assert result.model_message.role == ChatRoles.MODEL
		assert result.model_message.status == MessageStatus.PENDING
		# persisted exactly the user message + the placeholder
		assert mock_messages_gateway.create.await_count == 2
		# no inline completion, no SSE push
		mock_messages_gateway.complete_pending.assert_not_called()
		mock_events.publish_message.assert_not_called()
		# gateway received the turn
		mock_gateway.submit.assert_awaited_once()
		args = mock_gateway.submit.await_args.args
		assert args[0] is sample_user_message_dto

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_async_path_routes_by_model_value(self, chats_service, mock_gateway_factory, sample_user_message_dto):
		await chats_service.send_message(sample_user_message_dto)
		mock_gateway_factory.create_gateway.assert_called_once_with("gemini-3-flash-preview")

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_mock_path_resolves_inline_and_notifies_sse(
		self, chats_service, mock_gateway, mock_messages_gateway, mock_events, sample_user_message_dto
	):
		"""Offline gateway returns a response: placeholder is completed inline and the
		SSE broker is notified within the same request."""
		mock_gateway.submit.return_value = LLMResponse(
			text="Mock response for: Hello",
			model=LLMModelType.testing_mock,
			usage={"tokens": 10},
			provider="mock",
		)
		resolved = Message(
			id=uuid4(),
			message="Mock response for: Hello",
			chat_id=sample_user_message_dto.chat_id,
			role=ChatRoles.MODEL,
		)
		mock_messages_gateway.complete_pending.return_value = resolved

		result = await chats_service.send_message(sample_user_message_dto)

		mock_messages_gateway.complete_pending.assert_awaited_once_with(
			sample_user_message_dto.chat_id, "Mock response for: Hello", MessageStatus.COMPLETED
		)
		mock_events.publish_message.assert_called_once_with(sample_user_message_dto.chat_id, resolved)
		assert result.model_message is resolved
		assert result.model_message.status == MessageStatus.COMPLETED

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_placeholder_is_created_pending(self, chats_service, mock_messages_gateway, sample_user_message_dto):
		await chats_service.send_message(sample_user_message_dto)

		created_messages = [c.args[0] for c in mock_messages_gateway.create.call_args_list]
		assert len(created_messages) == 2
		assert created_messages[0].role == ChatRoles.USER
		assert created_messages[0].status == MessageStatus.COMPLETED
		assert created_messages[1].role == ChatRoles.MODEL
		assert created_messages[1].status == MessageStatus.PENDING
		assert created_messages[1].message == ""

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_history_forwarded_excludes_pending(
		self, mock_gateway_factory, mock_messages_gateway, mock_gateway, mock_uow, mock_events, sample_user_message_dto
	):
		"""Prior history is forwarded to the gateway as UserMessageDTOs, but PENDING
		(in-flight) model messages are filtered out."""
		prior_done = Message(message="previous turn", chat_id=sample_user_message_dto.chat_id, role=ChatRoles.MODEL)
		prior_pending = Message(
			message="", chat_id=sample_user_message_dto.chat_id, role=ChatRoles.MODEL, status=MessageStatus.PENDING
		)
		mock_messages_gateway.search.return_value = Page[Message](
			items=[prior_pending, prior_done], count=2, offset=0, limit=10
		)
		chats_service = LLMChatsService(
			gateway_factory=mock_gateway_factory,
			messages_gateway=mock_messages_gateway,
			_uow=mock_uow,
			_events=mock_events,
		)

		await chats_service.send_message(sample_user_message_dto)

		_, history = mock_gateway.submit.await_args.args
		assert len(history) == 1
		assert history[0].message == "previous turn"
		assert history[0].role == ChatRoles.MODEL
		assert history[0].chat_id == sample_user_message_dto.chat_id
		assert history[0].llm_model == sample_user_message_dto.llm_model

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_gateway_factory_error_propagates(
		self, mock_gateway_factory, mock_messages_gateway, mock_uow, mock_events, sample_user_message_dto
	):
		mock_gateway_factory.create_gateway.side_effect = Exception("Gateway creation failed")
		chats_service = LLMChatsService(
			gateway_factory=mock_gateway_factory,
			messages_gateway=mock_messages_gateway,
			_uow=mock_uow,
			_events=mock_events,
		)

		with pytest.raises(Exception, match="Gateway creation failed"):
			await chats_service.send_message(sample_user_message_dto)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_submit_error_propagates(self, chats_service, mock_gateway, sample_user_message_dto):
		"""If publishing fails, the error surfaces to the HTTP client (the user message
		+ PENDING placeholder are already committed)."""
		mock_gateway.submit.side_effect = Exception("Response generation failed")

		with pytest.raises(Exception, match="Response generation failed"):
			await chats_service.send_message(sample_user_message_dto)
