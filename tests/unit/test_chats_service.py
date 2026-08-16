from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.application.auth.authz import AuthorizationService
from src.application.chats.llm_service import LLMChatsService
from src.application.chats.prompt_service import PromptService
from src.application.chats.settings import (
	ChatSettings,
	ControlBehavior,
	FunctionsSettings,
	Perspective,
	Preset,
	ReasoningEffort,
	ResponseLength,
	TemperatureSettings,
	Toggle,
	TokenLimit,
)
from src.application.ports.characters import ICharacterGateway
from src.application.ports.chats import IChatEventGateway, IChatGateway, IChatSettingsGateway
from src.application.ports.common import Page
from src.application.ports.llm import (
	CONTEXT_WINDOW_SAFETY_FACTOR,
	DEFAULT_OUTPUT_RESERVE_TOKENS,
	IGatewayFactory,
	ILLMChatGateway,
	ITokenCounter,
	LLMModelType,
	LLMResponse,
	UserMessageDTO,
)
from src.application.ports.messages import IMessageService
from src.application.ports.scenes import ISceneGateway
from src.conf import settings
from src.domain.models import Character, Chat, ChatRoles, Message, MessageStatus, Scene
from src.infrastructure.exceptions import (
	ContextWindowExceededException,
	InitialMessageRequiredException,
	LLMGatewayException,
	PersonaRequiredException,
)


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
	def stub_token_counter(self):
		counter = Mock(spec=ITokenCounter)
		counter.count.side_effect = len
		return counter

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
	def mock_chat_gateway(self, sample_user_id, sample_chat_id):
		gateway = AsyncMock(spec=IChatGateway)
		gateway.get_one.return_value = Chat(
			id=sample_chat_id,
			title="chat",
			user_id=sample_user_id,
			scene_id=uuid4(),
			user_character_id=uuid4(),
			initial_message_id=uuid4(),
		)
		return gateway

	@pytest.fixture
	def mock_scene_gateway(self):
		gateway = AsyncMock(spec=ISceneGateway)
		gateway.get_one.return_value = Scene(title="scene", owner_id=uuid4(), background_prompt="bg")
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
		stub_token_counter,
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
			token_counter=stub_token_counter,
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
		stub_token_counter,
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
			token_counter=stub_token_counter,
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
		self, mock_chat_gateway, mock_message_service, mock_gateway, stub_token_counter, sample_user_message_dto
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
			token_counter=stub_token_counter,
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
	async def test_send_message_requires_chosen_initial_message(
		self,
		mock_chat_gateway,
		mock_message_service,
		mock_gateway,
		stub_token_counter,
		sample_user_message_dto,
		sample_user_id,
	):
		"""Until the user picks an initial message inside the chat, sending is rejected
		with INITIAL_MESSAGE_REQUIRED before any persistence or LLM call."""
		mock_chat_gateway.get_one.return_value = Chat(
			title="fresh chat",
			user_id=sample_user_id,
			scene_id=uuid4(),
			user_character_id=uuid4(),
			initial_message_id=None,
		)
		service = LLMChatsService(
			gateway_factory=MagicMock(spec=IGatewayFactory, create_gateway=Mock(return_value=mock_gateway)),
			message_service=mock_message_service,
			chat_settings_gateway=AsyncMock(spec=IChatSettingsGateway),
			chat_gateway=mock_chat_gateway,
			scene_gateway=AsyncMock(spec=ISceneGateway),
			character_gateway=AsyncMock(spec=ICharacterGateway),
			prompt_service=PromptService(),
			token_counter=stub_token_counter,
			authz=AuthorizationService(),
			_events=Mock(spec=IChatEventGateway),
		)

		with pytest.raises(InitialMessageRequiredException):
			await service.send_message(sample_user_message_dto, sample_user_id)

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
		stub_token_counter,
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
			token_counter=stub_token_counter,
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
		stub_token_counter,
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
			token_counter=stub_token_counter,
			authz=AuthorizationService(),
			_events=mock_events,
		)

		await chats_service.send_message(sample_user_message_dto, sample_user_id)

		mock_chat_settings_gateway.get_for_chat.assert_awaited_once_with(sample_user_message_dto.chat_id)
		assert mock_gateway.submit.await_args.kwargs["chat_settings"] is settings_obj

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_submit_failure_records_failed_turn_and_returns_user_message(
		self, chats_service, mock_gateway, mock_message_service, mock_events, sample_user_message_dto, sample_user_id
	):
		"""A submit/publish failure is recorded in-state — a FAILED model message via
		append_model_message plus an SSE error event — and the request still returns the
		user message (202). The user message is already committed, so raising a 5xx here
		would leave history mutated with no record of the failure and push clients to
		retry-and-duplicate the turn."""
		mock_gateway.submit.side_effect = LLMGatewayException(
			message="failed to publish request to scripulya_agent: broker down", details={}
		)
		failed_row = Message(
			id=uuid4(),
			message="failed to publish request to scripulya_agent: broker down",
			chat_id=sample_user_message_dto.chat_id,
			role=ChatRoles.MODEL,
			status=MessageStatus.FAILED,
		)
		mock_message_service.append_model_message.return_value = failed_row

		result = await chats_service.send_message(sample_user_message_dto, sample_user_id)

		# the user message is returned, not raised as a 5xx
		assert result.role == ChatRoles.USER
		# exactly the user-message persist; the FAILED row went through append_model_message
		assert mock_message_service.send_message.await_count == 1
		mock_message_service.append_model_message.assert_awaited_once()
		llm_result = mock_message_service.append_model_message.await_args.args[0]
		assert llm_result.chat_id == sample_user_message_dto.chat_id
		assert llm_result.error is not None
		assert llm_result.error.status == 502
		# the SSE error event fans out the FAILED model message
		mock_events.publish_message.assert_called_once_with(sample_user_message_dto.chat_id, failed_row)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_submit_failure_preserves_provider_error_code_and_status(
		self, chats_service, mock_gateway, mock_message_service, sample_user_message_dto, sample_user_id
	):
		"""A quota/rate-limit style failure keeps its own status/error_code on the
		recorded FAILED row instead of being flattened to a generic 502."""
		from src.infrastructure.exceptions import QuotaExceededException

		mock_gateway.submit.side_effect = QuotaExceededException(message="over quota")
		mock_message_service.append_model_message.return_value = Message(
			id=uuid4(),
			message="x",
			chat_id=sample_user_message_dto.chat_id,
			role=ChatRoles.MODEL,
			status=MessageStatus.FAILED,
		)

		await chats_service.send_message(sample_user_message_dto, sample_user_id)

		llm_result = mock_message_service.append_model_message.await_args.args[0]
		assert llm_result.error.status == 429
		assert llm_result.error.error_code == "quota_exceeded"

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_submit_failure_recovery_failure_still_returns_user_message(
		self, chats_service, mock_gateway, mock_message_service, mock_events, sample_user_message_dto, sample_user_id
	):
		"""If recording the failure itself raises (e.g. a DB outage right after the
		gateway failure), the request must still return the user message rather than
		5xx. The user message is already committed, so propagating here would
		re-introduce the partial-apply this path exists to prevent."""
		mock_gateway.submit.side_effect = LLMGatewayException(message="broker down")
		mock_message_service.append_model_message.side_effect = RuntimeError("DB outage")

		result = await chats_service.send_message(sample_user_message_dto, sample_user_id)

		# user message returned, not raised
		assert result.role == ChatRoles.USER
		# recording was attempted
		mock_message_service.append_model_message.assert_awaited_once()
		# but no SSE event could be emitted since recording failed
		mock_events.publish_message.assert_not_called()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_unexpected_submit_error_propagates_not_flattened_to_failed(
		self, chats_service, mock_gateway, mock_message_service, mock_events, sample_user_message_dto, sample_user_id
	):
		"""A non-gateway exception (programming bug like TypeError/AttributeError)
		propagates as a real 5xx instead of being recorded as a generic FAILED turn —
		otherwise a genuine bug is indistinguishable from a legitimate gateway outage."""
		mock_gateway.submit.side_effect = TypeError("bad arg")

		with pytest.raises(TypeError, match="bad arg"):
			await chats_service.send_message(sample_user_message_dto, sample_user_id)

		# no FAILED row recorded, no SSE event fanned out
		mock_message_service.append_model_message.assert_not_called()
		mock_events.publish_message.assert_not_called()

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
		as a # Player Character section in the assembled system prompt."""
		persona_id = uuid4()
		persona = Character(name="Kael", system_prompt="A wandering bard with a silver tongue.")
		mock_chat_gateway.get_one.return_value = Chat(
			title="chat",
			user_id=sample_user_id,
			scene_id=uuid4(),
			user_character_id=persona_id,
			initial_message_id=uuid4(),
		)
		mock_character_gateway.get_one.return_value = persona

		await chats_service.send_message(sample_user_message_dto, sample_user_id)

		mock_character_gateway.get_one.assert_awaited_once_with(persona_id)
		system_prompt = mock_gateway.submit.await_args.kwargs["system_prompt"]
		assert "# Player Character" in system_prompt
		assert "plays AS Kael" in system_prompt
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
			title="chat",
			user_id=sample_user_id,
			scene_id=uuid4(),
			user_character_id=None,
			initial_message_id=uuid4(),
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

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_history_forwarded_is_not_truncated_to_page_default(
		self, chats_service, mock_message_service, mock_gateway, sample_user_message_dto, sample_user_id
	):
		"""The LLM receives the full chat history: the search asks for MAX_SEARCH_LIMIT
		instead of the filter's 50-message default (pagination is a mobile-app concern,
		not a prompt-assembly one)."""
		messages = [
			Message(message=f"msg{i}", chat_id=sample_user_message_dto.chat_id, role=ChatRoles.USER) for i in range(73)
		]
		mock_message_service.search.return_value = Page[Message](
			items=list(reversed(messages)), count=73, offset=0, limit=LLMChatsService.MAX_SEARCH_LIMIT
		)

		await chats_service.send_message(sample_user_message_dto, sample_user_id)

		assert mock_message_service.search.await_args.args[0].limit == LLMChatsService.MAX_SEARCH_LIMIT
		_, history = mock_gateway.submit.await_args.args
		assert len(history) == 73
		assert [m.message for m in history] == [f"msg{i}" for i in range(73)]

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_context_usage_totals_are_cards_plus_full_history(
		self,
		chats_service,
		mock_message_service,
		mock_scene_gateway,
		mock_character_gateway,
		sample_chat_id,
		sample_user_id,
	):
		"""The total covers every message in the chat plus the assembled cards
		(characters/scene/persona), with the fixed base SYSTEM_PROMPT excluded —
		it does not scale with the chat, so it is not part of the summarization
		volume the caller wants to track."""
		m1 = Message(message="hello there", chat_id=sample_chat_id, role=ChatRoles.USER)
		m2 = Message(message="greetings and salutations", chat_id=sample_chat_id, role=ChatRoles.MODEL)
		mock_message_service.search.return_value = Page[Message](items=[m2, m1], count=2, offset=0, limit=10)

		result = await chats_service.get_context_usage(sample_chat_id, sample_user_id)

		expected_prompt = PromptService().build_system_prompt(
			mock_scene_gateway.get_one.return_value,
			mock_character_gateway.get_for_scene.return_value,
			mock_character_gateway.get_one.return_value,
			None,
		)
		expected_cards = len(expected_prompt) - len(settings.SYSTEM_PROMPT.strip())
		assert result.cards_tokens == expected_cards
		assert result.history_tokens == len("hello there") + len("greetings and salutations")
		assert result.history_messages_count == 2
		assert result.total_tokens == expected_cards + result.history_tokens

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_context_usage_counts_every_message_beyond_send_page_limit(
		self, chats_service, mock_message_service, sample_chat_id, sample_user_id
	):
		"""Usage measures the whole chat, not the 50-message slice send_message
		assembles: the search is issued with a large limit and every returned
		message is counted."""
		messages = [Message(message=f"msg{i}", chat_id=sample_chat_id, role=ChatRoles.USER) for i in range(75)]
		mock_message_service.search.return_value = Page[Message](
			items=list(reversed(messages)), count=75, offset=0, limit=100_000
		)

		result = await chats_service.get_context_usage(sample_chat_id, sample_user_id)

		requested_filter = mock_message_service.search.await_args.args[0]
		assert requested_filter.limit == LLMChatsService.MAX_SEARCH_LIMIT
		assert result.history_messages_count == 75
		assert result.history_tokens == sum(len(m.message) for m in messages)
		assert result.total_tokens == result.cards_tokens + result.history_tokens

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_context_usage_cards_exclude_base_system_prompt(
		self, chats_service, mock_scene_gateway, sample_chat_id, sample_user_id
	):
		"""cards_tokens is the assembled system prompt minus the fixed base prompt, so
		it tracks only the chat-dependent sections (characters, scene, persona,
		storytelling)."""
		mock_scene_gateway.get_one.return_value = Scene(
			title="SceneTitleXYZ",
			owner_id=uuid4(),
			background_prompt="background text",
		)

		result = await chats_service.get_context_usage(sample_chat_id, sample_user_id)

		full_prompt = PromptService().build_system_prompt(
			Scene(title="SceneTitleXYZ", owner_id=uuid4(), background_prompt="background text"),
			[],
			Character(name="Persona", system_prompt="persona"),
			None,
		)
		expected = len(full_prompt) - len(settings.SYSTEM_PROMPT.strip())
		assert result.cards_tokens == expected

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_context_usage_models_ordered_by_enum_with_fits_math(
		self,
		mock_gateway_factory,
		mock_message_service,
		mock_chat_settings_gateway,
		mock_chat_gateway,
		mock_scene_gateway,
		mock_character_gateway,
		stub_token_counter,
		mock_events,
		sample_chat_id,
		sample_user_id,
	):
		"""Per-model rows follow enum declaration order, and remaining_tokens/fits are
		derived from the safety-margined window minus the output reserve, not the raw
		provider limit."""
		chats_service = LLMChatsService(
			gateway_factory=mock_gateway_factory,
			message_service=mock_message_service,
			chat_settings_gateway=mock_chat_settings_gateway,
			chat_gateway=mock_chat_gateway,
			scene_gateway=mock_scene_gateway,
			character_gateway=mock_character_gateway,
			prompt_service=PromptService(),
			token_counter=stub_token_counter,
			authz=AuthorizationService(),
			_events=mock_events,
			context_windows={LLMModelType.gemini_flash_preview: 10_000_000, LLMModelType.qwen_max: 12},
		)

		result = await chats_service.get_context_usage(sample_chat_id, sample_user_id)

		assert [m.llm_model for m in result.models] == [
			LLMModelType.gemini_flash_preview,
			LLMModelType.qwen_max,
		]
		gemini, qwen = result.models
		assert gemini.context_window_tokens == 10_000_000
		assert gemini.usable_tokens == 9_000_000 - DEFAULT_OUTPUT_RESERVE_TOKENS
		assert gemini.remaining_tokens == gemini.usable_tokens - result.total_tokens
		assert gemini.fits is True
		assert qwen.context_window_tokens == 12
		assert qwen.usable_tokens == 10 - DEFAULT_OUTPUT_RESERVE_TOKENS
		assert qwen.remaining_tokens == qwen.usable_tokens - result.total_tokens
		assert qwen.fits is False
		assert result.estimated is True
		assert all(m.estimated is True for m in result.models)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_context_usage_safety_margin_flips_borderline_fit(
		self,
		mock_gateway_factory,
		mock_message_service,
		mock_chat_settings_gateway,
		mock_chat_gateway,
		mock_scene_gateway,
		mock_character_gateway,
		stub_token_counter,
		mock_events,
		sample_chat_id,
		sample_user_id,
	):
		"""Token counts come from a single o200k_base estimate for every provider, so a
		chat inside the raw window can still overflow the provider's own tokenizer.
		fits is therefore decided against the margined window: a total within 10% of
		the limit reports fits=False."""
		big = Message(message="x" * 120_000, chat_id=sample_chat_id, role=ChatRoles.USER)
		mock_message_service.search.return_value = Page[Message](items=[big], count=1, offset=0, limit=10)
		chats_service = LLMChatsService(
			gateway_factory=mock_gateway_factory,
			message_service=mock_message_service,
			chat_settings_gateway=mock_chat_settings_gateway,
			chat_gateway=mock_chat_gateway,
			scene_gateway=mock_scene_gateway,
			character_gateway=mock_character_gateway,
			prompt_service=PromptService(),
			token_counter=stub_token_counter,
			authz=AuthorizationService(),
			_events=mock_events,
			context_windows={LLMModelType.glm_4_5: 128_000},
		)

		result = await chats_service.get_context_usage(sample_chat_id, sample_user_id)

		glm = result.models[0]
		assert glm.usable_tokens == int(128_000 * CONTEXT_WINDOW_SAFETY_FACTOR) - DEFAULT_OUTPUT_RESERVE_TOKENS
		assert result.total_tokens < glm.context_window_tokens
		assert result.total_tokens > glm.usable_tokens
		assert glm.fits is False

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_send_message_rejects_prompt_above_context_window(
		self,
		mock_gateway_factory,
		mock_message_service,
		mock_chat_settings_gateway,
		mock_chat_gateway,
		mock_scene_gateway,
		mock_character_gateway,
		stub_token_counter,
		mock_events,
		sample_chat_id,
		sample_user_id,
		sample_user_message_dto,
	):
		"""A prompt that cannot fit the model's (margined, reserve-adjusted) window is
		rejected with CONTEXT_WINDOW_EXCEEDED before anything is persisted or queued —
		the recovery action for the client is to summarize messages."""
		mock_message_service.search.return_value = Page[Message](items=[], count=0, offset=0, limit=10)
		chats_service = LLMChatsService(
			gateway_factory=mock_gateway_factory,
			message_service=mock_message_service,
			chat_settings_gateway=mock_chat_settings_gateway,
			chat_gateway=mock_chat_gateway,
			scene_gateway=mock_scene_gateway,
			character_gateway=mock_character_gateway,
			prompt_service=PromptService(),
			token_counter=stub_token_counter,
			authz=AuthorizationService(),
			_events=mock_events,
			context_windows={LLMModelType.gemini_flash_preview: 500},
		)
		mock_gateway_factory.create_gateway.return_value = Mock()

		with pytest.raises(ContextWindowExceededException) as exc:
			await chats_service.send_message(sample_user_message_dto, sample_user_id)

		assert exc.value.status_code == 413
		assert exc.value.error_code == "CONTEXT_WINDOW_EXCEEDED"
		assert "summarize" in str(exc.value).lower()
		details = exc.value.details
		assert details["llm_model"] == "gemini-3-flash-preview"
		assert details["usable_tokens"] == int(500 * CONTEXT_WINDOW_SAFETY_FACTOR) - DEFAULT_OUTPUT_RESERVE_TOKENS

		mock_message_service.send_message.assert_not_called()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_send_message_allows_prompt_within_context_window(
		self,
		mock_gateway_factory,
		mock_message_service,
		mock_chat_settings_gateway,
		mock_chat_gateway,
		mock_scene_gateway,
		mock_character_gateway,
		stub_token_counter,
		mock_events,
		sample_user_message_dto,
		sample_user_id,
	):
		"""A prompt inside the usable window passes the gate and is submitted as before."""
		mock_gateway = AsyncMock(spec=ILLMChatGateway)
		mock_gateway.submit.return_value = None
		mock_gateway_factory.create_gateway.return_value = mock_gateway
		chats_service = LLMChatsService(
			gateway_factory=mock_gateway_factory,
			message_service=mock_message_service,
			chat_settings_gateway=mock_chat_settings_gateway,
			chat_gateway=mock_chat_gateway,
			scene_gateway=mock_scene_gateway,
			character_gateway=mock_character_gateway,
			prompt_service=PromptService(),
			token_counter=stub_token_counter,
			authz=AuthorizationService(),
			_events=mock_events,
			context_windows={LLMModelType.gemini_flash_preview: 1_000_000},
		)

		result = await chats_service.send_message(sample_user_message_dto, sample_user_id)

		assert result.role == ChatRoles.USER
		mock_gateway.submit.assert_awaited_once()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_context_usage_honors_context_limit_override(
		self,
		mock_gateway_factory,
		mock_message_service,
		mock_chat_settings_gateway,
		mock_chat_gateway,
		mock_scene_gateway,
		mock_character_gateway,
		stub_token_counter,
		mock_events,
		sample_chat_id,
		sample_user_id,
	):
		"""A chat's contextLimitOverride caps usable_tokens below the provider window:
		the user-set spend limit wins over the model's raw capacity."""
		mock_chat_settings_gateway.get_for_chat.return_value = ChatSettings(
			aiControlBehavior=ControlBehavior.DONT_CONTROL,
			continueBehavior=ControlBehavior.DONT_CONTROL,
			perspective=Perspective.SECOND_PERSON,
			temperature=TemperatureSettings(preset=Preset.MID, value=0.7),
			responseLength=ResponseLength.MEDIUM,
			responseTokenLimit=TokenLimit.CAPPED,
			reasoning=Toggle.OFF,
			reasoningEffort=ReasoningEffort.MID,
			aiMediaPicker=Toggle.OFF,
			contextLimitOverride=8_000,
			functions=FunctionsSettings(),
		)
		chats_service = LLMChatsService(
			gateway_factory=mock_gateway_factory,
			message_service=mock_message_service,
			chat_settings_gateway=mock_chat_settings_gateway,
			chat_gateway=mock_chat_gateway,
			scene_gateway=mock_scene_gateway,
			character_gateway=mock_character_gateway,
			prompt_service=PromptService(),
			token_counter=stub_token_counter,
			authz=AuthorizationService(),
			_events=mock_events,
			context_windows={LLMModelType.claude_sonnet: 200_000},
		)

		result = await chats_service.get_context_usage(sample_chat_id, sample_user_id)

		sonnet = result.models[0]
		assert sonnet.context_window_tokens == 200_000
		assert sonnet.usable_tokens == int(8_000 * CONTEXT_WINDOW_SAFETY_FACTOR) - 2048
		assert sonnet.remaining_tokens == sonnet.usable_tokens - result.total_tokens

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_context_usage_excludes_testing_mock(self, chats_service, sample_chat_id, sample_user_id):
		result = await chats_service.get_context_usage(sample_chat_id, sample_user_id)

		model_values = {m.llm_model for m in result.models}
		assert LLMModelType.testing_mock not in model_values
		assert len(result.models) == len(LLMModelType) - 1

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_context_usage_requires_persona(
		self, mock_chat_gateway, mock_message_service, chats_service, sample_chat_id, sample_user_id
	):
		"""The persona section is part of the assembled prompt, so a chat without one
		cannot be measured: _assemble_prompt raises before any counting, and nothing
		is persisted."""
		mock_chat_gateway.get_one.return_value = Chat(
			title="chat",
			user_id=sample_user_id,
			scene_id=uuid4(),
			user_character_id=None,
			initial_message_id=uuid4(),
		)

		with pytest.raises(PersonaRequiredException):
			await chats_service.get_context_usage(sample_chat_id, sample_user_id)

		mock_message_service.send_message.assert_not_called()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_context_usage_skips_initial_message_gate(
		self, mock_chat_gateway, chats_service, sample_chat_id, sample_user_id
	):
		"""The preview is read-only: a fresh chat with no initial message chosen still
		reports usage instead of raising INITIAL_MESSAGE_REQUIRED."""
		mock_chat_gateway.get_one.return_value = Chat(
			title="fresh chat",
			user_id=sample_user_id,
			scene_id=uuid4(),
			user_character_id=uuid4(),
			initial_message_id=None,
		)

		result = await chats_service.get_context_usage(sample_chat_id, sample_user_id)

		assert result.history_messages_count == 0
		assert result.history_tokens == 0
		assert result.total_tokens == result.cards_tokens

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_context_usage_rejects_chat_owned_by_another_user(
		self, mock_chat_gateway, mock_message_service, chats_service, sample_chat_id
	):
		mock_chat_gateway.get_one.return_value = Chat(
			title="not yours", user_id=uuid4(), scene_id=uuid4(), user_character_id=uuid4()
		)

		with pytest.raises(HTTPException) as exc:
			await chats_service.get_context_usage(sample_chat_id, uuid4())
		assert exc.value.status_code == 403

		mock_message_service.search.assert_not_awaited()
