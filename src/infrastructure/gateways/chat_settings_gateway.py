import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.chats.settings import ChatSettings
from src.application.ports.chats import IChatSettingsGateway
from src.infrastructure.database.models import ChatSettings as ChatSettingsModel
from src.infrastructure.logging.logger import Logger


@dataclass
class ChatSettingsGateway(IChatSettingsGateway):
	_session: AsyncSession
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)

	async def get_for_chat(self, chat_id: UUID) -> ChatSettings | None:
		self.logger.info(f"Getting chat settings for chat: {chat_id}")

		query = select(ChatSettingsModel).where(ChatSettingsModel.chat_id == chat_id)
		result = await self._session.execute(query)
		row = result.scalar_one_or_none()

		if row is None:
			self.logger.info(f"No settings stored for chat: {chat_id}")
			return None

		return ChatSettings(**row.settings)

	async def upsert(self, chat_id: UUID, settings: ChatSettings) -> ChatSettings:
		self.logger.info(f"Upserting chat settings for chat: {chat_id}")

		stmt = pg_insert(ChatSettingsModel).values(
			chat_id=chat_id,
			settings=settings.model_dump(mode="json"),
		)
		stmt = stmt.on_conflict_do_update(
			index_elements=[ChatSettingsModel.chat_id],
			set_={"settings": stmt.excluded.settings, "updated_at": func.now()},
		)
		await self._session.execute(stmt)

		self.logger.info(f"Successfully stored settings for chat: {chat_id}")
		return settings
