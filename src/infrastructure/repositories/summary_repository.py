import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from src.application.ports.common import Page
from src.application.ports.summarization import ISummaryRepository, SummarySourceMessage
from src.application.summarization.schemas import SummariesFilterDTO
from src.domain.models import ChatRoles, ChatSummary, MessageStatus, SummaryStatus
from src.infrastructure.database.models import ChatSummary as ChatSummaryModel
from src.infrastructure.database.models import Message as MessageModel
from src.infrastructure.logging.logger import Logger


@dataclass
class SummaryRepository(ISummaryRepository):
	_session: AsyncSession
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)

	async def list_source_messages(self, chat_id: UUID) -> list[SummarySourceMessage]:
		query = (
			select(MessageModel)
			.where(MessageModel.chat_id == chat_id)
			.order_by(MessageModel.created_at.asc(), MessageModel.id.asc())
		)
		result = await self._session.execute(query)
		return [self._to_source_message(row) for row in result.scalars().all()]

	async def list_summary_messages(self, summary_id: UUID) -> list[SummarySourceMessage]:
		query = (
			select(MessageModel)
			.where(MessageModel.summary_id == summary_id)
			.order_by(MessageModel.created_at.asc(), MessageModel.id.asc())
		)
		result = await self._session.execute(query)
		return [self._to_source_message(row) for row in result.scalars().all()]

	async def create(self, summary: ChatSummary) -> ChatSummary:
		model = ChatSummaryModel(
			chat_id=summary.chat_id,
			content=summary.content,
			status=summary.status.value,
			llm_model=summary.llm_model,
			from_message_id=summary.from_message_id,
			until_message_id=summary.until_message_id,
			covered_from_at=summary.covered_from_at,
			covered_until_at=summary.covered_until_at,
			messages_count=summary.messages_count,
			source_tokens=summary.source_tokens,
			summary_tokens=summary.summary_tokens,
			error=summary.error,
		)
		self._session.add(model)
		await self._session.flush()
		await self._session.refresh(model)
		self.logger.info("Created summary %s for chat %s", model.id, model.chat_id)
		return self._to_domain(model)

	async def claim_messages(self, summary_id: UUID, message_ids: list[UUID]) -> int:
		query = (
			update(MessageModel)
			.where(
				MessageModel.id.in_(message_ids),
				MessageModel.summary_id.is_(None),
				MessageModel.is_archived.is_(False),
			)
			.values(summary_id=summary_id)
		)
		result = await self._session.execute(query)
		return result.rowcount

	async def get_one(self, summary_id: UUID) -> ChatSummary | None:
		model = await self._session.get(ChatSummaryModel, summary_id, populate_existing=True)
		return self._to_domain(model) if model is not None else None

	async def search(self, dto: SummariesFilterDTO) -> Page[ChatSummary]:
		condition = ChatSummaryModel.chat_id == dto.chat_id
		total = await self._session.scalar(select(func.count(ChatSummaryModel.id)).where(condition)) or 0
		query = (
			select(ChatSummaryModel)
			.where(condition)
			.order_by(ChatSummaryModel.covered_from_at.asc(), ChatSummaryModel.created_at.asc())
			.offset(dto.offset)
			.limit(dto.limit)
		)
		result = await self._session.execute(query)
		items = [self._to_domain(row) for row in result.scalars().all()]
		return Page[ChatSummary](items=items, count=total, offset=dto.offset, limit=dto.limit)

	async def list_for_chat(self, chat_id: UUID, statuses: list[SummaryStatus]) -> list[ChatSummary]:
		query = (
			select(ChatSummaryModel)
			.where(
				ChatSummaryModel.chat_id == chat_id,
				ChatSummaryModel.status.in_([s.value for s in statuses]),
			)
			.order_by(ChatSummaryModel.covered_from_at.asc(), ChatSummaryModel.created_at.asc())
		)
		result = await self._session.execute(query)
		return [self._to_domain(row) for row in result.scalars().all()]

	async def dispatch_next_queued(self, chat_id: UUID) -> ChatSummary | None:
		in_flight = aliased(ChatSummaryModel)
		next_id = (
			select(ChatSummaryModel.id)
			.where(
				ChatSummaryModel.chat_id == chat_id,
				ChatSummaryModel.status == SummaryStatus.QUEUED.value,
				~exists().where(and_(in_flight.chat_id == chat_id, in_flight.status == SummaryStatus.PENDING.value)),
			)
			.order_by(ChatSummaryModel.covered_from_at.asc())
			.limit(1)
			.with_for_update(skip_locked=True)
			.scalar_subquery()
		)
		query = (
			update(ChatSummaryModel)
			.where(ChatSummaryModel.id == next_id)
			.values(status=SummaryStatus.PENDING.value, updated_at=func.now())
			.returning(ChatSummaryModel.id)
		)
		dispatched = await self._session.scalar(query)
		if dispatched is None:
			return None
		return await self.get_one(dispatched)

	async def complete(self, summary_id: UUID, content: str, summary_tokens: int) -> ChatSummary:
		return await self._update(
			summary_id,
			status=SummaryStatus.COMPLETED.value,
			content=content,
			summary_tokens=summary_tokens,
			error=None,
		)

	async def fail(self, summary_id: UUID, error: str) -> ChatSummary:
		return await self._update(summary_id, status=SummaryStatus.FAILED.value, error=error)

	async def archive_messages(self, summary_id: UUID) -> int:
		query = (
			update(MessageModel)
			.where(MessageModel.summary_id == summary_id, MessageModel.is_archived.is_(False))
			.values(is_archived=True)
		)
		result = await self._session.execute(query)
		return result.rowcount

	async def release_messages(self, summary_id: UUID) -> int:
		query = (
			update(MessageModel)
			.where(MessageModel.summary_id == summary_id, MessageModel.is_archived.is_(False))
			.values(summary_id=None)
		)
		result = await self._session.execute(query)
		return result.rowcount

	async def update_content(self, summary_id: UUID, content: str, summary_tokens: int) -> ChatSummary:
		return await self._update(summary_id, content=content, summary_tokens=summary_tokens)

	async def expire_pending(self, chat_id: UUID, older_than: datetime) -> list[UUID]:
		query = (
			update(ChatSummaryModel)
			.where(
				ChatSummaryModel.chat_id == chat_id,
				ChatSummaryModel.status == SummaryStatus.PENDING.value,
				ChatSummaryModel.updated_at < older_than,
			)
			.values(
				status=SummaryStatus.FAILED.value,
				error="The summarization model did not respond in time",
				updated_at=func.now(),
			)
			.returning(ChatSummaryModel.id)
		)
		result = await self._session.execute(query)
		return list(result.scalars().all())

	async def _update(self, summary_id: UUID, **values) -> ChatSummary:
		query = (
			update(ChatSummaryModel)
			.where(ChatSummaryModel.id == summary_id)
			.values(**values, updated_at=func.now())
			.returning(ChatSummaryModel.id)
		)
		if await self._session.scalar(query) is None:
			raise ValueError(f"Summary with ID {summary_id} not found")
		summary = await self.get_one(summary_id)
		if summary is None:
			raise ValueError(f"Summary with ID {summary_id} not found")
		return summary

	@staticmethod
	def _to_source_message(model: MessageModel) -> SummarySourceMessage:
		return SummarySourceMessage(
			id=model.id,
			role=ChatRoles(model.role),
			content=model.content,
			status=MessageStatus(model.status),
			created_at=model.created_at,
			is_archived=model.is_archived,
			summary_id=model.summary_id,
		)

	@staticmethod
	def _to_domain(model: ChatSummaryModel) -> ChatSummary:
		return ChatSummary(
			id=model.id,
			chat_id=model.chat_id,
			content=model.content,
			status=SummaryStatus(model.status),
			llm_model=model.llm_model,
			from_message_id=model.from_message_id,
			until_message_id=model.until_message_id,
			covered_from_at=model.covered_from_at,
			covered_until_at=model.covered_until_at,
			messages_count=model.messages_count,
			source_tokens=model.source_tokens,
			summary_tokens=model.summary_tokens,
			error=model.error,
			date_created=model.created_at,
			date_edited=model.updated_at,
		)
