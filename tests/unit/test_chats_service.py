import pytest
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

from fastapi import HTTPException

from src.application.authz import AuthorizationService
from src.application.chats.llm_service import LLMChatsService
from src.application.chats.prompt_service import PromptService
from src.application.ports import (
	UserMessageDTO,
	LLMModelType,
	LLMResponse,
	IGatewayFactory,
	ICharacterGateway,
	IChatEventGateway,
	IChatGateway,
	IChatSettingsGateway,
	ILLMChatGateway,
	IMessageService,
	ISceneGateway,
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
from src.conf import settings
from src.domain.models import Character, Chat, ChatRoles, Message, MessageStatus, Scene
from src.infrastructure.exceptions import PersonaRequiredException


def _persist(message: Message) -> Message:
	"""Stand-in for MessageService.send_message(): echo back with a generated id."""
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
	def mock_message_service(self):
		service = AsyncMock(spec=IMessageService)
		service.search.return_value = Page[Message](items=[], count=0, offset=0, limit=10)
		service.send_message.side_effect = _persist
		return service

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
	def sample_user_id(self):
		return uuid4()

	@pytest.fixture
	def mock_chat_gateway(self, sample_user_id):
		gateway = AsyncMock(spec=IChatGateway)
		gateway.get_one.return_value = Chat(
			title="chat", user_id=sample_user_id, scene_id=uuid4(), user_character_id=uuid4()
		)
		return gateway

	@pytest.fixture
	def mock_scene_gateway(self):
		gateway = AsyncMock(spec=ISceneGateway)
		gateway.get_one.return_value = Scene(
			title="scene", owner_id=uuid4(), background_prompt="bg", initial_message_text="init"
		)
		return gateway

	@pytest.fixture
	def mock_character_gateway(self):
		gateway = AsyncMock(spec=ICharacterGateway)
		gateway.get_for_scene.return_value = []
		gateway.get_one.return_value = Character(name="Persona", system_prompt="persona")
		return gateway

	@pytest.fixture
	def chats_service(
		self,
		mock_gateway_factory,
		mock_message_service,
		mock_chat_settings_gateway,
		mock_chat_gateway,
		mock_scene_gateway,
		mock_character_gateway,
		mock_events,
	):
		return LLMChatsService(
			gateway_factory=mock_gateway_factory,
			message_service=mock_message_service,
			chat_settings_gateway=mock_chat_settings_gateway,
			chat_gateway=mock_chat_gateway,
			scene_gateway=mock_scene_gateway,
			character_gateway=mock_character_gateway,
			prompt_service=PromptService(),
			authz=AuthorizationService(),
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
		self, chats_service, mock_gateway, mock_message_service, mock_events, sample_user_message_dto, sample_user_id
	):
		"""Fire-and-forget gateway: persists only the user message, returns it, and
		does not append a model reply inline or notify SSE."""
		result = await chats_service.send_message(sample_user_message_dto, sample_user_id)

		assert isinstance(result, Message)
		assert result.message == "Hello, how are you?"
		assert result.role == ChatRoles.USER
		assert result.status == MessageStatus.COMPLETED
		# persisted exactly the user message — no placeholder, no inline reply
		assert mock_message_service.send_message.await_count == 1
		# no SSE push (the reply arrives later via the result subscriber)
		mock_events.publish_message.assert_not_called()
		# gateway received the turn
		mock_gateway.submit.assert_awaited_once()
		args = mock_gateway.submit.await_args.args
		assert args[0] is sample_user_message_dto

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_async_path_routes_by_model_value(
		self, chats_service, mock_gateway_factory, sample_user_message_dto, sample_user_id
	):
		await chats_service.send_message(sample_user_message_dto, sample_user_id)
		mock_gateway_factory.create_gateway.assert_called_once_with("gemini-3-flash-preview")

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_mock_path_appends_reply_inline_and_notifies_sse(
		self, chats_service, mock_gateway, mock_message_service, mock_events, sample_user_message_dto, sample_user_id
	):
		"""Offline gateway returns a response: a COMPLETED model reply is appended
		inline (INSERT) and the SSE broker is notified within the same request."""
		mock_gateway.submit.return_value = LLMResponse(
			text="Mock response for: Hello",
			model=LLMModelType.testing_mock,
			usage={"tokens": 10},
			provider="mock",
		)

		await chats_service.send_message(sample_user_message_dto, sample_user_id)

		# user message + appended model reply
		assert mock_message_service.send_message.await_count == 2
		appended = mock_message_service.send_message.await_args_list[1].args[0]
		assert appended.role == ChatRoles.MODEL
		assert appended.status == MessageStatus.COMPLETED
		assert appended.message == "Mock response for: Hello"
		assert appended.chat_id == sample_user_message_dto.chat_id
		# SSE received the appended message (send_message echoes it back with an id via _persist)
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
		mock_message_service,
		mock_gateway,
		mock_chat_settings_gateway,
		mock_chat_gateway,
		mock_scene_gateway,
		mock_character_gateway,
		mock_events,
		sample_user_message_dto,
		sample_user_id,
	):
		"""Prior history is forwarded to the gateway as UserMessageDTOs."""
		prior_done = Message(message="previous turn", chat_id=sample_user_message_dto.chat_id, role=ChatRoles.MODEL)
		mock_message_service.search.return_value = Page[Message](items=[prior_done], count=1, offset=0, limit=10)
		chats_service = LLMChatsService(
			gateway_factory=mock_gateway_factory,
			message_service=mock_message_service,
			chat_settings_gateway=mock_chat_settings_gateway,
			chat_gateway=mock_chat_gateway,
			scene_gateway=mock_scene_gateway,
			character_gateway=mock_character_gateway,
			prompt_service=PromptService(),
			authz=AuthorizationService(),
			_events=mock_events,
		)

		await chats_service.send_message(sample_user_message_dto, sample_user_id)

		_, history = mock_gateway.submit.await_args.args
		assert len(history) == 1
		assert history[0].message == "previous turn"
		assert history[0].role == ChatRoles.MODEL
		assert history[0].chat_id == sample_user_message_dto.chat_id
		assert history[0].llm_model == sample_user_message_dto.llm_model

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_send_message_rejects_chat_owned_by_another_user(
		self, mock_chat_gateway, mock_message_service, mock_gateway, sample_user_message_dto
	):
		"""The chat must belong to the actor: a foreign-owned chat 403s before any
		persistence or LLM call (authorization lives in the service, not the caller)."""
		mock_chat_gateway.get_one.return_value = Chat(
			title="not yours", user_id=uuid4(), scene_id=uuid4(), user_character_id=uuid4()
		)
		service = LLMChatsService(
			gateway_factory=MagicMock(spec=IGatewayFactory, create_gateway=Mock(return_value=mock_gateway)),
			message_service=mock_message_service,
			chat_settings_gateway=AsyncMock(spec=IChatSettingsGateway),
			chat_gateway=mock_chat_gateway,
			scene_gateway=AsyncMock(spec=ISceneGateway),
			character_gateway=AsyncMock(spec=ICharacterGateway),
			prompt_service=PromptService(),
			authz=AuthorizationService(),
			_events=Mock(spec=IChatEventGateway),
		)

		with pytest.raises(HTTPException) as exc:
			await service.send_message(sample_user_message_dto, uuid4())
		assert exc.value.status_code == 403

		mock_message_service.send_message.assert_not_called()
		mock_gateway.submit.assert_not_called()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_gateway_factory_error_propagates(
		self,
		mock_gateway_factory,
		mock_message_service,
		mock_chat_settings_gateway,
		mock_chat_gateway,
		mock_scene_gateway,
		mock_character_gateway,
		mock_events,
		sample_user_message_dto,
		sample_user_id,
	):
		mock_gateway_factory.create_gateway.side_effect = Exception("Gateway creation failed")
		chats_service = LLMChatsService(
			gateway_factory=mock_gateway_factory,
			message_service=mock_message_service,
			chat_settings_gateway=mock_chat_settings_gateway,
			chat_gateway=mock_chat_gateway,
			scene_gateway=mock_scene_gateway,
			character_gateway=mock_character_gateway,
			prompt_service=PromptService(),
			authz=AuthorizationService(),
			_events=mock_events,
		)

		with pytest.raises(Exception, match="Gateway creation failed"):
			await chats_service.send_message(sample_user_message_dto, sample_user_id)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_stored_chat_settings_forwarded_to_gateway(
		self,
		mock_gateway_factory,
		mock_message_service,
		mock_gateway,
		mock_chat_settings_gateway,
		mock_chat_gateway,
		mock_scene_gateway,
		mock_character_gateway,
		mock_events,
		sample_user_message_dto,
		sample_user_id,
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
			message_service=mock_message_service,
			chat_settings_gateway=mock_chat_settings_gateway,
			chat_gateway=mock_chat_gateway,
			scene_gateway=mock_scene_gateway,
			character_gateway=mock_character_gateway,
			prompt_service=PromptService(),
			authz=AuthorizationService(),
			_events=mock_events,
		)

		await chats_service.send_message(sample_user_message_dto, sample_user_id)

		mock_chat_settings_gateway.get_for_chat.assert_awaited_once_with(sample_user_message_dto.chat_id)
		assert mock_gateway.submit.await_args.kwargs["chat_settings"] is settings_obj

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_submit_error_propagates(self, chats_service, mock_gateway, sample_user_message_dto, sample_user_id):
		"""If publishing fails, the error surfaces to the HTTP client (the user message
		is already committed)."""
		mock_gateway.submit.side_effect = Exception("Response generation failed")

		with pytest.raises(Exception, match="Response generation failed"):
			await chats_service.send_message(sample_user_message_dto, sample_user_id)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_system_prompt_assembled_from_scene_and_characters(
		self,
		chats_service,
		mock_character_gateway,
		mock_scene_gateway,
		mock_gateway,
		sample_user_message_dto,
		sample_user_id,
	):
		mock_character_gateway.get_for_scene.return_value = [
			Character(name="Aria", system_prompt="A brave and cautious knight."),
		]
		mock_scene_gateway.get_one.return_value = Scene(
			title="Dark Forest",
			owner_id=uuid4(),
			background_prompt="A misty woodland at dusk.",
			initial_message_text="init",
		)

		await chats_service.send_message(sample_user_message_dto, sample_user_id)

		system_prompt = mock_gateway.submit.await_args.kwargs["system_prompt"]
		assert settings.SYSTEM_PROMPT.strip() in system_prompt
		assert "Aria" in system_prompt
		assert "A brave and cautious knight." in system_prompt
		assert "Dark Forest" in system_prompt
		assert "A misty woodland at dusk." in system_prompt

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_user_persona_included_when_chat_has_one(
		self,
		chats_service,
		mock_chat_gateway,
		mock_character_gateway,
		mock_gateway,
		sample_user_message_dto,
		sample_user_id,
	):
		"""When the chat carries a user_character_id, that persona is resolved and rendered
		as a # User section in the assembled system prompt."""
		persona_id = uuid4()
		persona = Character(name="Kael", system_prompt="A wandering bard with a silver tongue.")
		mock_chat_gateway.get_one.return_value = Chat(
			title="chat", user_id=sample_user_id, scene_id=uuid4(), user_character_id=persona_id
		)
		mock_character_gateway.get_one.return_value = persona

		await chats_service.send_message(sample_user_message_dto, sample_user_id)

		mock_character_gateway.get_one.assert_awaited_once_with(persona_id)
		system_prompt = mock_gateway.submit.await_args.kwargs["system_prompt"]
		assert "# User" in system_prompt
		assert "Kael" in system_prompt
		assert "A wandering bard with a silver tongue." in system_prompt

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_send_message_requires_play_as_character(
		self, mock_chat_gateway, mock_message_service, chats_service, sample_user_message_dto, sample_user_id
	):
		"""A chat without a chosen play-as character is rejected with a graceful error
		before the user message is persisted or the LLM is called."""
		mock_chat_gateway.get_one.return_value = Chat(
			title="chat", user_id=sample_user_id, scene_id=uuid4(), user_character_id=None
		)

		with pytest.raises(PersonaRequiredException):
			await chats_service.send_message(sample_user_message_dto, sample_user_id)

		# Nothing is written when the request is rejected.
		mock_message_service.send_message.assert_not_called()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_history_forwarded_in_chronological_order(
		self, chats_service, mock_message_service, mock_gateway, sample_user_message_dto, sample_user_id
	):
		newest = Message(message="newest", chat_id=sample_user_message_dto.chat_id, role=ChatRoles.USER)
		oldest = Message(message="oldest", chat_id=sample_user_message_dto.chat_id, role=ChatRoles.MODEL)
		mock_message_service.search.return_value = Page[Message](items=[newest, oldest], count=2, offset=0, limit=10)

		await chats_service.send_message(sample_user_message_dto, sample_user_id)

		_, history = mock_gateway.submit.await_args.args
		assert [m.message for m in history] == ["oldest", "newest"]
