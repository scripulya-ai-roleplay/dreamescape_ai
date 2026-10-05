import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from src.application.chats.settings import (
	DEFAULT_CHAT_SETTINGS,
	ChatSettings,
	Preset,
	ReasoningEffort,
	TemperatureSettings,
	Toggle,
	TokenLimit,
)
from src.application.ports.authorization import IAuthorizationService
from src.application.ports.characters import ICharacterGateway
from src.application.ports.chats import IChatEventGateway, IChatGateway
from src.application.ports.common import IUnitOfWork, Page
from src.application.ports.llm import ITokenCounter, LLMModelType
from src.application.ports.summarization import (
	ISummarizationAgentGateway,
	ISummarizationService,
	ISummaryRepository,
	SummaryRequest,
	SummaryResult,
	SummarySourceMessage,
)
from src.application.summarization import prompts
from src.application.summarization.chapters import PlannedChapter, plan_chapters
from src.application.summarization.schemas import (
	CreateSummariesDTO,
	SummariesFilterDTO,
	SummaryChapter,
	UpdateSummaryDTO,
)
from src.conf import settings
from src.domain.models import Chat, ChatSummary, SummaryStatus
from src.infrastructure.exceptions import (
	ChatReadOnlyException,
	LLMGatewayException,
	SummaryChapterStaleException,
	SummaryNotEditableException,
	SummaryNotFoundException,
)
from src.infrastructure.logging.logger import Logger

SUMMARY_CHAT_SETTINGS = DEFAULT_CHAT_SETTINGS.model_copy(
	update={
		"temperature": TemperatureSettings(preset=Preset.LOW, value=0.2),
		"responseTokenLimit": TokenLimit.HIGH,
		"reasoning": Toggle.OFF,
		"reasoningEffort": ReasoningEffort.MIN,
	}
)


@dataclass
class SummarizationService(ISummarizationService):
	repository: ISummaryRepository
	agent_gateway: ISummarizationAgentGateway
	mock_gateway: ISummarizationAgentGateway
	chat_gateway: IChatGateway
	character_gateway: ICharacterGateway
	token_counter: ITokenCounter
	authz: IAuthorizationService
	events: IChatEventGateway
	uow: IUnitOfWork
	chunk_tokens: int = settings.SUMMARY_CHUNK_TOKENS
	target_ratio: float = settings.SUMMARY_TARGET_RATIO
	min_target_tokens: int = settings.SUMMARY_MIN_TARGET_TOKENS
	pending_timeout_seconds: int = settings.SUMMARY_PENDING_TIMEOUT_SECONDS
	chat_settings: ChatSettings = field(default_factory=lambda: SUMMARY_CHAT_SETTINGS)
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)

	async def list_chapters(self, chat_id: UUID, actor_id: UUID) -> list[SummaryChapter]:
		chat = await self._require_owned_chat(chat_id, actor_id)
		await self._expire_stale(chat_id)
		planned = await self._plan(chat)
		return [chapter.to_chapter() for chapter in planned]

	async def summarize(self, dto: CreateSummariesDTO, actor_id: UUID) -> list[ChatSummary]:
		chat = await self._require_owned_chat(dto.chat_id, actor_id)
		if chat.scene_id is None:
			raise ChatReadOnlyException()
		await self._expire_stale(dto.chat_id)
		planned = {(c.from_message_id, c.until_message_id): c for c in await self._plan(chat)}

		selected: dict[tuple[UUID, UUID], PlannedChapter] = {}
		for requested in dto.chapters:
			key = (requested.from_message_id, requested.until_message_id)
			chapter = planned.get(key)
			if chapter is None:
				raise SummaryChapterStaleException(
					details={
						"from_message_id": str(requested.from_message_id),
						"until_message_id": str(requested.until_message_id),
					}
				)
			selected[key] = chapter

		created: list[ChatSummary] = []
		async with self.uow:
			for chapter in sorted(selected.values(), key=lambda c: c.covered_from_at):
				summary = await self.repository.create(
					ChatSummary(
						chat_id=dto.chat_id,
						status=SummaryStatus.QUEUED,
						llm_model=dto.llm_model.value,
						from_message_id=chapter.from_message_id,
						until_message_id=chapter.until_message_id,
						covered_from_at=chapter.covered_from_at,
						covered_until_at=chapter.covered_until_at,
						messages_count=len(chapter.message_ids),
						source_tokens=chapter.tokens_count,
					)
				)
				claimed = await self.repository.claim_messages(summary.id, chapter.message_ids)
				if claimed != len(chapter.message_ids):
					raise SummaryChapterStaleException(
						details={
							"from_message_id": str(chapter.from_message_id),
							"until_message_id": str(chapter.until_message_id),
						}
					)
				created.append(summary)

		self.logger.info("Queued %d summaries for chat %s with model %s", len(created), dto.chat_id, dto.llm_model)
		await self._pump(dto.chat_id)
		return [await self.repository.get_one(summary.id) or summary for summary in created]

	async def search(self, dto: SummariesFilterDTO, actor_id: UUID) -> Page[ChatSummary]:
		await self._require_owned_chat(dto.chat_id, actor_id)
		await self._expire_stale(dto.chat_id)
		return await self.repository.search(dto)

	async def get_one(self, summary_id: UUID, actor_id: UUID) -> ChatSummary:
		summary = await self.repository.get_one(summary_id)
		if summary is None:
			raise SummaryNotFoundException(details={"summary_id": str(summary_id)})
		await self._require_owned_chat(summary.chat_id, actor_id)
		return summary

	async def update(self, summary_id: UUID, dto: UpdateSummaryDTO, actor_id: UUID) -> ChatSummary:
		summary = await self.get_one(summary_id, actor_id)
		if summary.status != SummaryStatus.COMPLETED:
			raise SummaryNotEditableException(details={"summary_id": str(summary_id), "status": summary.status})
		tokens = await asyncio.to_thread(self.token_counter.count, dto.content)
		async with self.uow:
			updated = await self.repository.update_content(summary_id, dto.content, tokens)
		self.events.publish_summary(updated.chat_id, updated)
		return updated

	async def handle_result(self, result: SummaryResult) -> ChatSummary | None:
		summary = await self.repository.get_one(result.summary_id)
		if summary is None or summary.status != SummaryStatus.PENDING:
			self.logger.warning(
				"Ignoring summary result for %s: summary is %s",
				result.summary_id,
				"missing" if summary is None else summary.status,
			)
			return None

		text = (result.text or "").strip()
		if result.error is not None or not text:
			reason = result.error.message if result.error is not None else "The model returned an empty summary"
			self.logger.warning("Summary %s for chat %s failed: %s", summary.id, summary.chat_id, reason)
			async with self.uow:
				updated = await self.repository.fail(summary.id, reason)
				await self.repository.release_messages(summary.id)
		else:
			tokens = await asyncio.to_thread(self.token_counter.count, text)
			async with self.uow:
				updated = await self.repository.complete(summary.id, text, tokens)
				archived = await self.repository.archive_messages(summary.id)
			self.logger.info(
				"Summary %s for chat %s completed: %d messages archived, %d -> %d tokens",
				summary.id,
				summary.chat_id,
				archived,
				summary.source_tokens,
				tokens,
			)

		self.events.publish_summary(updated.chat_id, updated)
		await self._pump(updated.chat_id)
		return updated

	async def prompt_summaries(self, chat_id: UUID) -> list[ChatSummary]:
		return await self.repository.list_for_chat(chat_id, [SummaryStatus.COMPLETED])

	async def _require_owned_chat(self, chat_id: UUID, actor_id: UUID) -> Chat:
		chat = await self.chat_gateway.get_one(chat_id)
		self.authz.require_owned(owner_id=chat.user_id, actor_id=actor_id, noun="chat")
		return chat

	async def _player(self, chat: Chat) -> str:
		if chat.user_character_id is None:
			return prompts.player_label(None)
		persona = await self.character_gateway.get_one(chat.user_character_id)
		return prompts.player_label(persona.name)

	async def _plan(self, chat: Chat) -> list[PlannedChapter]:
		player = await self._player(chat)
		messages = await self.repository.list_source_messages(chat.id)
		return await asyncio.to_thread(
			plan_chapters, messages, lambda m: self._line_tokens(m, player), self.chunk_tokens
		)

	def _line_tokens(self, message: SummarySourceMessage, player: str) -> int:
		line = prompts.format_line(message, player)
		return self.token_counter.count(line) if line else 0

	async def _expire_stale(self, chat_id: UUID) -> None:
		cutoff = datetime.now(UTC) - timedelta(seconds=self.pending_timeout_seconds)
		async with self.uow:
			expired = await self.repository.expire_pending(chat_id, cutoff)
			for summary_id in expired:
				await self.repository.release_messages(summary_id)
		if not expired:
			return
		self.logger.warning("Expired %d stuck summaries for chat %s", len(expired), chat_id)
		for summary_id in expired:
			summary = await self.repository.get_one(summary_id)
			if summary is not None:
				self.events.publish_summary(chat_id, summary)
		await self._pump(chat_id)

	async def _pump(self, chat_id: UUID) -> None:
		async with self.uow:
			summary = await self.repository.dispatch_next_queued(chat_id)
		if summary is None:
			return
		self.events.publish_summary(chat_id, summary)

		try:
			request = await self._build_request(summary)
		except Exception as exc:
			self.logger.exception("Could not build summary request %s", summary.id)
			await self._fail_dispatch(summary, f"Could not build the summary request: {exc}")
			return

		gateway = self.mock_gateway if request.llm_model == LLMModelType.testing_mock else self.agent_gateway
		try:
			result = await gateway.submit(request)
		except LLMGatewayException as exc:
			await self._fail_dispatch(summary, exc.message)
			return
		if result is not None:
			await self.handle_result(result)

	async def _fail_dispatch(self, summary: ChatSummary, reason: str) -> None:
		async with self.uow:
			failed = await self.repository.fail(summary.id, reason)
			await self.repository.release_messages(summary.id)
		self.events.publish_summary(summary.chat_id, failed)
		await self._pump(summary.chat_id)

	async def _build_request(self, summary: ChatSummary) -> SummaryRequest:
		chat = await self.chat_gateway.get_one(summary.chat_id)
		player = await self._player(chat)
		messages = await self.repository.list_summary_messages(summary.id)
		previous = [
			s
			for s in await self.repository.list_for_chat(summary.chat_id, [SummaryStatus.COMPLETED])
			if s.covered_until_at <= summary.covered_from_at
		]
		previous_content = previous[-1].content if previous else None
		target = prompts.target_tokens(summary.source_tokens, self.target_ratio, self.min_target_tokens)
		return SummaryRequest(
			summary_id=summary.id,
			chat_id=summary.chat_id,
			llm_model=LLMModelType(summary.llm_model),
			system_prompt=prompts.build_system_prompt(player, target),
			content=prompts.build_content(prompts.format_transcript(messages, player), previous_content),
			chat_settings=self.chat_settings,
		)
