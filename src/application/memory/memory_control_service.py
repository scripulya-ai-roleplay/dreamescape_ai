import logging
from dataclasses import dataclass, field
from uuid import UUID

from src.application.chats.budgeter import TokenCounter, budget
from src.application.chats.prompt_sections import render_system_prompt
from src.application.ports.authorization import IAuthorizationService
from src.application.ports.characters import ICharacterGateway
from src.application.ports.chats import IChatGateway, IChatSettingsGateway
from src.application.ports.common import IUnitOfWork
from src.application.ports.llm import IPromptService, UserMessageDTO
from src.application.ports.memory import IMemoryControlService, IMemoryService, ISummaryGateway
from src.application.ports.messages import IMessageGateway
from src.application.ports.scenes import ISceneGateway
from src.conf import settings
from src.domain.models import ChatRoles, ConversationSummary
from src.infrastructure.logging.logger import Logger


@dataclass
class MemoryControlService(IMemoryControlService):
	chat_gateway: IChatGateway
	scene_gateway: ISceneGateway
	character_gateway: ICharacterGateway
	chat_settings_gateway: IChatSettingsGateway
	summary_gateway: ISummaryGateway
	message_gateway: IMessageGateway
	prompt_service: IPromptService
	memory_service: IMemoryService
	token_counter: TokenCounter
	authz: IAuthorizationService
	_uow: IUnitOfWork
	logger: logging.Logger = field(default_factory=lambda: logging.getLogger(Logger.LOGGER_NAME))

	async def _require_owned(self, chat_id: UUID, actor_id: UUID):
		chat = await self.chat_gateway.get_one(chat_id)
		self.authz.require_owned(owner_id=chat.user_id, actor_id=actor_id, noun="chat")
		return chat

	async def current_summary(self, chat_id: UUID, actor_id: UUID) -> ConversationSummary | None:
		await self._require_owned(chat_id, actor_id)
		return await self.summary_gateway.latest(chat_id)

	async def set_summary(self, chat_id: UUID, content: str, actor_id: UUID) -> ConversationSummary:
		await self._require_owned(chat_id, actor_id)
		current = await self.summary_gateway.latest(chat_id)
		if current is not None:
			from_message_id = current.from_message_id
			to_message_id = current.to_message_id
		else:
			messages = await self.message_gateway.tail_after(chat_id, limit=None)
			if not messages:
				raise ValueError("cannot set a summary for a chat with no messages")
			from_message_id = messages[0].id
			to_message_id = messages[-1].id
		new_row = ConversationSummary(
			chat_id=chat_id,
			from_message_id=from_message_id,
			to_message_id=to_message_id,
			content=content,
			token_count=self.token_counter.count(content),
			supersedes_id=current.id if current is not None else None,
			model="manual",
		)
		async with self._uow:
			return await self.summary_gateway.insert(new_row)

	async def context_usage(self, chat_id: UUID, actor_id: UUID) -> dict:
		chat = await self._require_owned(chat_id, actor_id)
		scene = await self.scene_gateway.get_one(chat.scene_id)
		characters = await self.character_gateway.get_for_scene(chat.scene_id)
		user_character = (
			await self.character_gateway.get_one(chat.user_character_id) if chat.user_character_id else None
		)
		chat_settings = await self.chat_settings_gateway.get_for_chat(chat_id)
		memory_settings = chat_settings.memory if chat_settings is not None else None
		summary_enabled = settings.SUMMARY_ENABLED and (memory_settings.summaryEnabled if memory_settings else True)

		sections = self.prompt_service.build_prompt_sections(scene, characters, user_character)
		query = self._last_user_query()
		enriched = await self.memory_service.enrich(chat_id, query, memory_settings)
		sections.summary = enriched.sections.summary
		sections.memories = enriched.sections.memories
		sections.facts = enriched.sections.facts
		if summary_enabled:
			sections.reminder = self.prompt_service.build_reminder(scene, characters, user_character)

		history = [
			UserMessageDTO(message=m.message, chat_id=chat_id, llm_model=None, role=m.role) for m in enriched.tail
		]
		limit = chat_settings.contextLimitOverride if chat_settings is not None else None
		limit = (limit or settings.DEFAULT_CONTEXT_LIMIT) if summary_enabled else None
		placeholder = UserMessageDTO(message="", chat_id=chat_id, llm_model=None, role=ChatRoles.USER)
		budgeted = budget(sections, history, placeholder, limit, self.token_counter)
		return {
			"sections": budgeted.section_tokens,
			"total": budgeted.used_tokens,
			"limit": limit,
			"system_prompt": render_system_prompt(budgeted.sections),
		}

	@staticmethod
	def _last_user_query() -> str:
		return ""
