import logging
from dataclasses import dataclass, field
from uuid import UUID

from src.application.chats.schemas import ContextUsage, ModelContextUsage
from src.application.chats.settings import ChatSettings
from src.application.message.schemas import MessagesFilterDto
from src.application.ports.authorization import IAuthorizationService
from src.application.ports.characters import ICharacterGateway
from src.application.ports.chats import IChatEventGateway, IChatGateway, IChatSettingsGateway, IChatsService
from src.application.ports.llm import (
	LLM_MODEL_CONTEXT_WINDOWS,
	IGatewayFactory,
	IPromptService,
	ITokenCounter,
	LLMErrorResponse,
	LLMModelType,
	LLMResult,
	UserMessageDTO,
)
from src.application.ports.messages import IMessageService
from src.application.ports.scenes import ISceneGateway
from src.conf import settings
from src.domain.models import Chat, ChatRoles, Message, MessageStatus
from src.infrastructure.exceptions import BaseAPIException, InitialMessageRequiredException, PersonaRequiredException
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
	token_counter: ITokenCounter
	authz: IAuthorizationService
	_events: IChatEventGateway
	context_windows: dict[LLMModelType, int] = field(default_factory=lambda: LLM_MODEL_CONTEXT_WINDOWS)
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)

	async def send_message(self, chat_dto: UserMessageDTO, actor_id: UUID) -> Message:
		self.logger.info(f"Processing LLM chat message with model: {chat_dto.llm_model}")
		gateway = self.gateway_factory.create_gateway(chat_dto.llm_model.value)

		chat = await self.chat_gateway.get_one(chat_dto.chat_id)
		self.authz.require_owned(owner_id=chat.user_id, actor_id=actor_id, noun="chat")
		history = await self._load_history(chat_dto.chat_id, chat.user_id, chat_dto.llm_model)
		if not history and chat.initial_message_id is None:
			raise InitialMessageRequiredException()
		system_prompt, chat_settings = await self._assemble_prompt(chat)

		# A client-authored message is always role=USER; never persist a role
		# supplied by the caller, which would let it forge assistant messages.
		user_message = await self.message_service.send_message(
			Message(
				message=chat_dto.message,
				chat_id=chat_dto.chat_id,
				role=ChatRoles.USER,
				status=MessageStatus.COMPLETED,
			)
		)

		if settings.DEBUG:
			history_preview = "\n\n".join(f"[{m.role}] {m.message}" for m in history) or "(none)"
			self.logger.debug(
				f"LLM prompt for chat {chat_dto.chat_id} | model={chat_dto.llm_model}\n"
				f"===== SYSTEM PROMPT =====\n{system_prompt}\n"
				f"===== HISTORY ({len(history)} turns) =====\n{history_preview}\n"
				f"===== NEW MESSAGE [{ChatRoles.USER}] =====\n{chat_dto.message}\n"
				f"===== END PROMPT ====="
			)

		try:
			response = await gateway.submit(chat_dto, history, chat_settings=chat_settings, system_prompt=system_prompt)
		except BaseAPIException as exc:
			self.logger.warning("LLM submit failed for chat %s: %s", chat_dto.chat_id, exc)
			try:
				failed = await self.message_service.append_model_message(
					LLMResult(
						chat_id=chat_dto.chat_id,
						error=LLMErrorResponse(
							error_code=exc.error_code.lower(),
							status=exc.status_code,
							reason="Failed to queue model generation",
							message=str(exc) or "Failed to queue model generation",
						),
					)
				)
				self._events.publish_message(chat_dto.chat_id, failed)
			except Exception:
				self.logger.exception(
					"Failed to record LLM submit failure in-state for chat %s "
					"(user message committed, no FAILED row/event emitted)",
					chat_dto.chat_id,
				)
			return user_message

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

	async def get_context_usage(self, chat_id: UUID, actor_id: UUID) -> ContextUsage:
		chat = await self.chat_gateway.get_one(chat_id)
		self.authz.require_owned(owner_id=chat.user_id, actor_id=actor_id, noun="chat")
		history = await self._load_history(chat_id, chat.user_id, None)
		system_prompt, _ = await self._assemble_prompt(chat)

		system_prompt_tokens = self.token_counter.count(system_prompt)
		history_tokens = sum(self.token_counter.count(m.message) for m in history)
		total_tokens = system_prompt_tokens + history_tokens

		models = [
			ModelContextUsage(
				llm_model=model,
				context_window_tokens=window,
				remaining_tokens=window - total_tokens,
				fits=total_tokens <= window,
			)
			for model in LLMModelType
			if (window := self.context_windows.get(model)) is not None
		]
		return ContextUsage(
			system_prompt_tokens=system_prompt_tokens,
			history_tokens=history_tokens,
			history_messages_count=len(history),
			total_tokens=total_tokens,
			models=models,
		)

	async def _load_history(
		self, chat_id: UUID, owner_id: UUID, llm_model: LLMModelType | None
	) -> list[UserMessageDTO]:
		history_page = await self.message_service.search(MessagesFilterDto(chats_ids=[chat_id]), owner_id)
		return [
			UserMessageDTO(message=m.message, chat_id=chat_id, llm_model=llm_model, role=m.role)
			for m in reversed(history_page.items)
		]

	async def _assemble_prompt(self, chat: Chat) -> tuple[str, ChatSettings | None]:
		scene = await self.scene_gateway.get_one(chat.scene_id)
		characters = await self.character_gateway.get_for_scene(chat.scene_id)
		if chat.user_character_id is None:
			raise PersonaRequiredException()
		user_character = await self.character_gateway.get_one(chat.user_character_id)
		chat_settings = await self.chat_settings_gateway.get_for_chat(chat.id)
		system_prompt = self.prompt_service.build_system_prompt(scene, characters, user_character, chat_settings)
		return system_prompt, chat_settings
