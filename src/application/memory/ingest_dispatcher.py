import asyncio
import logging
from dataclasses import dataclass, field
from uuid import UUID

from dishka import AsyncContainer, Scope

from src.application.ports.memory import IMemoryService
from src.infrastructure.logging.logger import Logger


@dataclass
class MemoryIngestDispatcher:
	_container: AsyncContainer
	logger: logging.Logger = field(default_factory=lambda: logging.getLogger(Logger.LOGGER_NAME))
	_inflight: set = field(default_factory=set)

	def dispatch(self, chat_id: UUID, model_reply_message_id: UUID) -> None:
		task = asyncio.create_task(self._run(chat_id, model_reply_message_id))
		self._inflight.add(task)
		task.add_done_callback(self._inflight.discard)

	async def _run(self, chat_id: UUID, model_reply_message_id: UUID) -> None:
		try:
			async with self._container(scope=Scope.REQUEST) as request_container:
				memory_service = await request_container.get(IMemoryService)
				await memory_service.ingest(chat_id, model_reply_message_id)
		except Exception:
			self.logger.exception(
				"memory ingest failed chat_id=%s model_reply_message_id=%s",
				chat_id,
				model_reply_message_id,
			)
