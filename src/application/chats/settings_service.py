import logging
from dataclasses import dataclass
from uuid import UUID

from src.application.chats.settings import ChatSettings
from src.application.ports.chats import IChatSettingsGateway, IChatSettingsService
from src.application.ports.common import IUnitOfWork
from src.infrastructure.logging.logger import Logger


@dataclass
class ChatSettingsService(IChatSettingsService):
	chat_settings_gateway: IChatSettingsGateway
	uow: IUnitOfWork
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)

	async def get_for_chat(self, chat_uuid: UUID) -> ChatSettings | None:
		self.logger.info(f"Getting chat settings: {chat_uuid}")
		settings = await self.chat_settings_gateway.get_for_chat(chat_uuid)
		self.logger.info(f"Retrieved chat settings for: {chat_uuid}")
		return settings

	async def upsert(self, chat_uuid: UUID, settings: ChatSettings) -> ChatSettings:
		self.logger.info(f"Upserting chat settings: {chat_uuid}")
		async with self.uow:
			result = await self.chat_settings_gateway.upsert(chat_uuid, settings)
		self.logger.info(f"Successfully upserted chat settings: {chat_uuid}")
		return result
