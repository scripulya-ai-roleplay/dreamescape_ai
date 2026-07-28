import logging
from dataclasses import dataclass, field
from uuid import UUID

from src.application.chats.budgeter import TokenCounter
from src.application.ports.common import IUnitOfWork
from src.application.ports.memory import ISummaryGateway
from src.application.ports.messages import IMessageGateway
from src.application.ports.summary_model import ISummaryModel
from src.conf import settings
from src.domain.models import ConversationSummary, Message
from src.infrastructure.logging.logger import Logger

_PER_MESSAGE_OVERHEAD = 4


@dataclass
class SummaryService:
	summary_gateway: ISummaryGateway
	message_gateway: IMessageGateway
	summary_model: ISummaryModel
	token_counter: TokenCounter
	_uow: IUnitOfWork
	logger: logging.Logger = field(default_factory=lambda: logging.getLogger(Logger.LOGGER_NAME))

	async def maybe_fold(self, chat_id: UUID) -> None:
		latest = await self.summary_gateway.latest(chat_id)
		boundary = latest.to_message_id if latest else None
		tail = await self.message_gateway.tail_after(chat_id, boundary, limit=None)
		if not tail:
			return
		tail_tokens = sum(self._tokens(message) for message in tail)
		if tail_tokens < settings.SUMMARY_TRIGGER_TOKENS:
			return
		batch = self._select_batch(tail)
		if not batch:
			return
		await self._fold(chat_id, latest, batch)

	async def _fold(self, chat_id: UUID, latest: ConversationSummary | None, batch: list[Message]) -> None:
		prior = latest.content if latest else None
		new_content = await self.summary_model.summarize(prior, batch)
		new_row = ConversationSummary(
			chat_id=chat_id,
			from_message_id=batch[0].id,
			to_message_id=batch[-1].id,
			content=new_content,
			token_count=self.token_counter.count(new_content),
			supersedes_id=latest.id if latest else None,
			model=settings.SUMMARY_MODEL,
		)
		try:
			async with self._uow:
				await self.summary_gateway.insert(new_row)
		except Exception:
			self.logger.warning(
				"summary insert skipped (likely redelivery duplicate) chat_id=%s to=%s",
				chat_id,
				new_row.to_message_id,
				exc_info=True,
			)

	def _select_batch(self, tail: list[Message]) -> list[Message]:
		batch: list[Message] = []
		acc = 0
		for message in tail:
			cost = self._tokens(message)
			if batch and acc + cost > settings.SUMMARY_FOLD_BATCH_TOKENS:
				break
			batch.append(message)
			acc += cost
		return batch

	def _tokens(self, message: Message) -> int:
		return self.token_counter.count(message.message) + _PER_MESSAGE_OVERHEAD
