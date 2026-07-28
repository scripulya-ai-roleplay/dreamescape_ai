import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.application.ports.memory import IGraphMemoryGateway
from src.infrastructure.logging.logger import Logger


@dataclass
class NullGraphMemoryGateway(IGraphMemoryGateway):
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)

	async def store(self, chat_id: UUID, user_msg: str, model_reply: str, reference_time: datetime) -> None:
		return None

	async def retrieve(self, chat_id: UUID, query: str) -> list[str]:
		return []

	async def delete_group(self, chat_id: UUID) -> None:
		return None
