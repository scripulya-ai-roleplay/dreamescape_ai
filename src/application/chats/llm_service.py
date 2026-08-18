import asyncio
import logging
from dataclasses import dataclass, field
from typing import ClassVar
from uuid import UUID

from src.application.chats.schemas import ContextUsage, ModelContextUsage
from src.application.chats.settings import ChatSettings
from src.application.message.schemas import MessagesFilterDto
from src.application.ports.authorization import IAuthorizationService
from src.application.ports.characters import ICharacterGateway
from src.application.ports.chats import IChatEventGateway, IChatGateway, IChatSettingsGateway, IChatsService
from src.application.ports.common import Page
from src.application.ports.llm import (
	CONTEXT_WINDOW_MIN_USABLE_TOKENS,
	CONTEXT_WINDOW_SAFETY_FACTOR,
	DEFAULT_OUTPUT_RESERVE_TOKENS,
	LLM_MODEL_CONTEXT_WINDOWS,
	OUTPUT_RESERVE_BY_TOKEN_LIMIT,
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
from src.infrastructure.exceptions import (
	BaseAPIException,
	ChatReadOnlyException,
	ContextWindowExceededException,
	InitialMessageRequiredException,
	PersonaRequiredException,
)
from src.infrastructure.logging.logger import Logger

_MAX_SEARCH_LIMIT = 100_000


@dataclass
class LLMChatsService(IChatsService):
	MAX_SEARCH_LIMIT: ClassVar[int] = _MAX_SEARCH_LIMIT

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
	context_windows: dict[LLMModelType, int] = field(default_factory=lambda: dict(LLM_MODEL_CONTEXT_WINDOWS))
	safety_factor: float = CONTEXT_WINDOW_SAFETY_FACTOR
	_cached_base_prompt_tokens: int | None = None
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)

	async def send_message(self, chat_dto: UserMessageDTO, actor_id: UUID) -> Message:
		self.logger.info(f"Processing LLM chat message with model: {chat_dto.llm_model}")
		gateway = self.gateway_factory.create_gateway(chat_dto.llm_model.value)

		chat = await self.chat_gateway.get_one(chat_dto.chat_id)
		self.authz.require_owned(owner_id=chat.user_id, actor_id=actor_id, noun="chat")
		if chat.scene_id is None:
			raise ChatReadOnlyException()
		history_page = await self._search_history(chat_dto.chat_id, chat.user_id)
		history = self._page_to_history(history_page, chat_dto.chat_id, chat_dto.llm_model)
		if not history and chat.initial_message_id is None:
			raise InitialMessageRequiredException()
		system_prompt, chat_settings = await self._assemble_prompt(chat)

		await self._require_fits_window(system_prompt, history, chat_dto, chat_settings)

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
		history_page = await self._search_history(chat_id, chat.user_id)
		history = self._page_to_history(history_page, chat_id, None)
		system_prompt, chat_settings = await self._assemble_prompt(chat)

		cards_tokens, history_tokens = await asyncio.to_thread(
			self._count_parts, system_prompt, [m.message for m in history], None
		)
		total_tokens = cards_tokens + history_tokens

		models = [
			ModelContextUsage(
				llm_model=model,
				context_window_tokens=window,
				usable_tokens=usable,
				remaining_tokens=usable - total_tokens,
				fits=total_tokens <= usable,
				estimated=True,
			)
			for model in LLMModelType
			if (window := self.context_windows.get(model)) is not None
			for usable in (self._usable_tokens(model, chat_settings),)
		]
		return ContextUsage(
			cards_tokens=cards_tokens,
			history_tokens=history_tokens,
			history_messages_count=len(history),
			total_tokens=total_tokens,
			estimated=True,
			models=models,
		)

	async def _require_fits_window(
		self,
		system_prompt: str,
		history: list[UserMessageDTO],
		chat_dto: UserMessageDTO,
		chat_settings: ChatSettings | None,
	) -> None:
		window = self.context_windows.get(chat_dto.llm_model)
		if window is None:
			return
		usable = self._usable_tokens(chat_dto.llm_model, chat_settings)
		prompt_tokens, _ = await asyncio.to_thread(
			self._count_parts, system_prompt, [m.message for m in history], chat_dto.message, True
		)
		if prompt_tokens > usable:
			raise ContextWindowExceededException(
				details={
					"llm_model": chat_dto.llm_model.value,
					"context_window_tokens": window,
					"usable_tokens": usable,
					"prompt_tokens": prompt_tokens,
					"suggestion": "summarize some messages to continue",
				}
			)

	def _count_parts(
		self, system_prompt: str, history_texts: list[str], new_message: str | None, include_base_prompt: bool = False
	) -> tuple[int, int]:
		base = 0 if include_base_prompt else self._base_prompt_tokens()
		cards = self.token_counter.count(system_prompt) - base
		history_sum = sum(self.token_counter.count(text) for text in history_texts)
		if new_message is not None:
			history_sum += self.token_counter.count(new_message)
		return cards, history_sum

	def _usable_tokens(self, model: LLMModelType, chat_settings: ChatSettings | None) -> int:
		window = self.context_windows.get(model)
		if window is None:
			return 0
		limit = window
		if chat_settings is not None and chat_settings.contextLimitOverride is not None:
			limit = min(limit, chat_settings.contextLimitOverride)
		return max(
			int(limit * self.safety_factor) - self._output_reserve(chat_settings),
			CONTEXT_WINDOW_MIN_USABLE_TOKENS,
		)

	@staticmethod
	def _output_reserve(chat_settings: ChatSettings | None) -> int:
		if chat_settings is None:
			return DEFAULT_OUTPUT_RESERVE_TOKENS
		return OUTPUT_RESERVE_BY_TOKEN_LIMIT.get(chat_settings.responseTokenLimit, DEFAULT_OUTPUT_RESERVE_TOKENS)

	def _base_prompt_tokens(self) -> int:
		if self._cached_base_prompt_tokens is None:
			self._cached_base_prompt_tokens = self.token_counter.count(settings.SYSTEM_PROMPT.strip())
		return self._cached_base_prompt_tokens

	async def _search_history(self, chat_id: UUID, owner_id: UUID) -> Page[Message]:
		return await self.message_service.search(
			MessagesFilterDto(chats_ids=[chat_id], limit=self.MAX_SEARCH_LIMIT), owner_id
		)

	@staticmethod
	def _page_to_history(page: Page[Message], chat_id: UUID, llm_model: LLMModelType | None) -> list[UserMessageDTO]:
		return [
			UserMessageDTO(message=m.message, chat_id=chat_id, llm_model=llm_model, role=m.role)
			for m in reversed(page.items)
		]

	async def _assemble_prompt(self, chat: Chat) -> tuple[str, ChatSettings | None]:
		scene = None
		characters = []
		if chat.scene_id is not None:
			scene = await self.scene_gateway.get_one(chat.scene_id)
			characters = await self.character_gateway.get_for_scene(chat.scene_id)
		if chat.user_character_id is None:
			raise PersonaRequiredException()
		user_character = await self.character_gateway.get_one(chat.user_character_id)
		chat_settings = await self.chat_settings_gateway.get_for_chat(chat.id)
		system_prompt = self.prompt_service.build_system_prompt(scene, characters, user_character, chat_settings)
		return system_prompt, chat_settings
