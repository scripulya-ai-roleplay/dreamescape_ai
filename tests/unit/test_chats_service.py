import pytest
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

from src.application.chats.llm_service import LLMChatsService
from src.application.ports import (
	UserMessageDTO,
	LLMModelType,
	LLMResponse,
	IGatewayFactory,
	IChatEventGateway,
	ILLMChatGateway,
	IMessageGateway,
	IUnitOfWork,
	IChatSettingsGateway,
	Page,
)
from src.application.chats.settings import (
	ChatSettings,
	ControlBehavior,
	FunctionsSettings,
	Perspective,
	Preset,
	ReasoningEffort,
	ResponseLength,
	TemperatureSettings,
	TokenLimit,
	Toggle,
)
from src.domain.models import ChatRoles, Message, MessageStatus


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
		return Mock(spec=IChatEventGateway)

	@pytest.fixture
	def mock_chat_settings_gateway(self):
		"""Mock settings gateway. get_for_chat() returns None by default (no settings stored)."""
		gateway = AsyncMock(spec=IChatSettingsGateway)
		gateway.get_for_chat.return_value = None
		return gateway

	@pytest.fixture
	def chats_service(
		self, mock_gateway_factory, mock_messages_gateway, mock_chat_settings_gateway, mock_uow, mock_events
	):
		return LLMChatsService(
			gateway_factory=mock_gateway_factory,
			messages_gateway=mock_messages_gateway,
			chat_settings_gateway=mock_chat_settings_gateway,
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
	async def test_async_path_returns_user_message_only(
		self, chats_service, mock_gateway, mock_messages_gateway, mock_events, sample_user_message_dto
	):
		"""Fire-and-forget gateway: persists only the user message, returns it, and
		does not append a model reply inline or notify SSE."""
		result = await chats_service.send_message(sample_user_message_dto)

		assert isinstance(result, Message)
		assert result.message == "Hello, how are you?"
		assert result.role == ChatRoles.USER
		assert result.status == MessageStatus.COMPLETED
		# persisted exactly the user message — no placeholder, no inline reply
		assert mock_messages_gateway.create.await_count == 1
		# no SSE push (the reply arrives later via the result subscriber)
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
	async def test_mock_path_appends_reply_inline_and_notifies_sse(
		self, chats_service, mock_gateway, mock_messages_gateway, mock_events, sample_user_message_dto
	):
		"""Offline gateway returns a response: a COMPLETED model reply is appended
		inline (INSERT) and the SSE broker is notified within the same request."""
		mock_gateway.submit.return_value = LLMResponse(
			text="Mock response for: Hello",
			model=LLMModelType.testing_mock,
			usage={"tokens": 10},
			provider="mock",
		)

		await chats_service.send_message(sample_user_message_dto)

		# user message + appended model reply
		assert mock_messages_gateway.create.await_count == 2
		appended = mock_messages_gateway.create.await_args_list[1].args[0]
		assert appended.role == ChatRoles.MODEL
		assert appended.status == MessageStatus.COMPLETED
		assert appended.message == "Mock response for: Hello"
		assert appended.chat_id == sample_user_message_dto.chat_id
		# SSE received the appended message (create echoes it back with an id via _persist)
		mock_events.publish_message.assert_called_once()
		published = mock_events.publish_message.call_args.args
		assert published[0] == sample_user_message_dto.chat_id
		assert published[1].role == ChatRoles.MODEL
		assert published[1].status == MessageStatus.COMPLETED
		assert published[1].message == "Mock response for: Hello"

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_history_forwarded_includes_all_prior_turns(
		self,
		mock_gateway_factory,
		mock_messages_gateway,
		mock_gateway,
		mock_chat_settings_gateway,
		mock_uow,
		mock_events,
		sample_user_message_dto,
	):
		"""Prior history is forwarded to the gateway as UserMessageDTOs."""
		prior_done = Message(message="previous turn", chat_id=sample_user_message_dto.chat_id, role=ChatRoles.MODEL)
		mock_messages_gateway.search.return_value = Page[Message](items=[prior_done], count=1, offset=0, limit=10)
		chats_service = LLMChatsService(
			gateway_factory=mock_gateway_factory,
			messages_gateway=mock_messages_gateway,
			chat_settings_gateway=mock_chat_settings_gateway,
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
		self,
		mock_gateway_factory,
		mock_messages_gateway,
		mock_chat_settings_gateway,
		mock_uow,
		mock_events,
		sample_user_message_dto,
	):
		mock_gateway_factory.create_gateway.side_effect = Exception("Gateway creation failed")
		chats_service = LLMChatsService(
			gateway_factory=mock_gateway_factory,
			messages_gateway=mock_messages_gateway,
			chat_settings_gateway=mock_chat_settings_gateway,
			_uow=mock_uow,
			_events=mock_events,
		)

		with pytest.raises(Exception, match="Gateway creation failed"):
			await chats_service.send_message(sample_user_message_dto)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_stored_chat_settings_forwarded_to_gateway(
		self,
		mock_gateway_factory,
		mock_messages_gateway,
		mock_gateway,
		mock_chat_settings_gateway,
		mock_uow,
		mock_events,
		sample_user_message_dto,
	):
		"""Per-chat settings are fetched and forwarded to the gateway as chat_settings."""
		settings_obj = ChatSettings(
			aiControlBehavior=ControlBehavior.CONTROL,
			continueBehavior=ControlBehavior.CONTROL,
			perspective=Perspective.THIRD_PERSON,
			temperature=TemperatureSettings(preset=Preset.MID, value=0.7),
			responseLength=ResponseLength.MEDIUM,
			responseTokenLimit=TokenLimit.HIGH,
			reasoning=Toggle.OFF,
			reasoningEffort=ReasoningEffort.MID,
			aiMediaPicker=Toggle.OFF,
			functions=FunctionsSettings(),
		)
		mock_chat_settings_gateway.get_for_chat.return_value = settings_obj
		chats_service = LLMChatsService(
			gateway_factory=mock_gateway_factory,
			messages_gateway=mock_messages_gateway,
			chat_settings_gateway=mock_chat_settings_gateway,
			_uow=mock_uow,
			_events=mock_events,
		)

		await chats_service.send_message(sample_user_message_dto)

		mock_chat_settings_gateway.get_for_chat.assert_awaited_once_with(sample_user_message_dto.chat_id)
		assert mock_gateway.submit.await_args.kwargs["chat_settings"] is settings_obj

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_submit_error_propagates(self, chats_service, mock_gateway, sample_user_message_dto):
		"""If publishing fails, the error surfaces to the HTTP client (the user message
		is already committed)."""
		mock_gateway.submit.side_effect = Exception("Response generation failed")

		with pytest.raises(Exception, match="Response generation failed"):
			await chats_service.send_message(sample_user_message_dto)
