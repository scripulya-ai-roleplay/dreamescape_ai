import logging
from dataclasses import dataclass
from uuid import UUID

from src.application.chats.budgeter import TokenCounter, budget
from src.application.chats.prompt_sections import render_system_prompt
from src.application.ports.authorization import IAuthorizationService
from src.application.ports.characters import ICharacterGateway
from src.application.ports.chats import IChatEventGateway, IChatGateway, IChatSettingsGateway, IChatsService
from src.application.ports.llm import IGatewayFactory, IPromptService, UserMessageDTO
from src.application.ports.memory import IMemoryService
from src.application.ports.messages import IMessageService
from src.application.ports.scenes import ISceneGateway
from src.conf import settings
from src.domain.models import ChatRoles, Message, MessageStatus
from src.infrastructure.exceptions import InitialMessageRequiredException, PersonaRequiredException
from src.infrastructure.logging.logger import Logger


@dataclass
class LLMChatsService(IChatsService):
	gateway_factory: IGatewayFactory
	message_service: IMessageService
	chat_settings_gateway: IChatSettingsGateway
	chat_gateway: IChatGateway
	scene_gateway: ISceneGateway
	character_gateway: ICharacterGateway
	prompt_service: IPromptService
	memory_service: IMemoryService
	token_counter: TokenCounter
	authz: IAuthorizationService
	_events: IChatEventGateway
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)

	async def send_message(self, chat_dto: UserMessageDTO, actor_id: UUID) -> Message:
		self.logger.info(f"Processing LLM chat message with model: {chat_dto.llm_model}")
		gateway = self.gateway_factory.create_gateway(chat_dto.llm_model.value)

		chat = await self.chat_gateway.get_one(chat_dto.chat_id)
		self.authz.require_owned(owner_id=chat.user_id, actor_id=actor_id, noun="chat")

		chat_settings = await self.chat_settings_gateway.get_for_chat(chat_dto.chat_id)
		memory_settings = chat_settings.memory if chat_settings is not None else None

		# Gates fire before scene/character resolution or persistence, and in the order the API
		# contract guarantees: a chat with no history must choose an initial message first, and a
		# chat with no play-as persona is rejected next. Enrich runs first only to load the tail
		# the initial-message gate needs.
		enriched = await self.memory_service.enrich(chat_dto.chat_id, chat_dto.message, memory_settings)
		if not enriched.tail and chat.initial_message_id is None:
			raise InitialMessageRequiredException()
		if chat.user_character_id is None:
			raise PersonaRequiredException()

		scene = await self.scene_gateway.get_one(chat.scene_id)
		characters = await self.character_gateway.get_for_scene(chat.scene_id)
		user_character = await self.character_gateway.get_one(chat.user_character_id)

		# A client-authored message is always role=USER; never persist a role supplied by the
		# caller, which would let it forge assistant messages.
		user_message = await self.message_service.send_message(
			Message(
				message=chat_dto.message,
				chat_id=chat_dto.chat_id,
				role=ChatRoles.USER,
				status=MessageStatus.COMPLETED,
			)
		)

		system_prompt, history = self._assemble_prompt(
			chat_dto, chat_settings, memory_settings, enriched, scene, characters, user_character
		)

		# Submit is the only outward action; a failure here is a real error and propagates to the
		# global exception handler (which owns the HTTP error response). The service does not
		# intercept it — see docs/adr/0001-send-message-exception-boundary.md.
		response = await gateway.submit(chat_dto, history, chat_settings=chat_settings, system_prompt=system_prompt)

		if response is not None:
			model_message = await self.message_service.send_message(
				Message(
					message=response.text,
					chat_id=chat_dto.chat_id,
					role=ChatRoles.MODEL,
					status=MessageStatus.COMPLETED,
				)
			)
			self._events.publish_message(chat_dto.chat_id, model_message)

		return user_message

	def _assemble_prompt(
		self,
		chat_dto: UserMessageDTO,
		chat_settings,
		memory_settings,
		enriched,
		scene,
		characters,
		user_character,
	) -> tuple[str, list[UserMessageDTO]]:
		summary_enabled = settings.SUMMARY_ENABLED and (memory_settings.summaryEnabled if memory_settings else True)
		sections = self.prompt_service.build_prompt_sections(scene, characters, user_character)
		sections.summary = enriched.sections.summary
		sections.memories = enriched.sections.memories
		sections.facts = enriched.sections.facts
		if summary_enabled:
			sections.reminder = self.prompt_service.build_reminder(scene, characters, user_character)

		history = [
			UserMessageDTO(message=m.message, chat_id=chat_dto.chat_id, llm_model=chat_dto.llm_model, role=m.role)
			for m in enriched.tail
		]
		pinned_ids = set(memory_settings.pinnedMessageIds) if memory_settings else set()
		pinned_indices = {i for i, message in enumerate(enriched.tail) if message.id in pinned_ids}

		# Budgeting only kicks in when the rolling summary can recover what history drops; with the
		# summary layer off the full tail is forwarded unchanged (legacy behavior).
		limit = None
		if summary_enabled:
			limit = (
				chat_settings.contextLimitOverride if chat_settings is not None else None
			) or settings.DEFAULT_CONTEXT_LIMIT
		budgeted = budget(sections, history, chat_dto, limit, self.token_counter, pinned_indices=pinned_indices)
		system_prompt = render_system_prompt(budgeted.sections)

		if settings.DEBUG:
			history_preview = "\n\n".join(f"[{m.role}] {m.message}" for m in budgeted.history) or "(none)"
			self.logger.debug(
				f"LLM prompt for chat {chat_dto.chat_id} | model={chat_dto.llm_model}\n"
				f"===== SYSTEM PROMPT =====\n{system_prompt}\n"
				f"===== HISTORY ({len(budgeted.history)} turns) =====\n{history_preview}\n"
				f"===== NEW MESSAGE [{ChatRoles.USER}] =====\n{chat_dto.message}\n"
				f"===== END PROMPT ====="
			)

		return system_prompt, budgeted.history
