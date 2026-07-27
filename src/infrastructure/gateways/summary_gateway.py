import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.memory import ISummaryGateway
from src.domain.models import ConversationSummary
from src.infrastructure.database.models import ConversationSummary as ConversationSummaryModel
from src.infrastructure.logging.logger import Logger


@dataclass
class SummaryGateway(ISummaryGateway):
	_session: AsyncSession
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)

	async def latest(self, chat_id: UUID) -> ConversationSummary | None:
		stmt = (
			select(ConversationSummaryModel)
			.where(
				ConversationSummaryModel.chat_id == chat_id,
				ConversationSummaryModel.supersedes_id.is_(None),
			)
			.order_by(ConversationSummaryModel.created_at.desc())
			.limit(1)
		)
		row = (await self._session.execute(stmt)).scalar_one_or_none()
		return self._to_domain(row) if row else None

	async def insert(self, summary: ConversationSummary) -> ConversationSummary:
		row = ConversationSummaryModel(
			chat_id=summary.chat_id,
			from_message_id=summary.from_message_id,
			to_message_id=summary.to_message_id,
			content=summary.content,
			token_count=summary.token_count,
			supersedes_id=summary.supersedes_id,
			model=summary.model,
		)
		self._session.add(row)
		await self._session.flush()
		await self._session.refresh(row)
		return self._to_domain(row)

	def _to_domain(self, row: ConversationSummaryModel) -> ConversationSummary:
		return ConversationSummary(
			id=row.id,
			chat_id=row.chat_id,
			from_message_id=row.from_message_id,
			to_message_id=row.to_message_id,
			content=row.content,
			token_count=row.token_count,
			supersedes_id=row.supersedes_id,
			model=row.model,
			created_at=row.created_at,
		)
