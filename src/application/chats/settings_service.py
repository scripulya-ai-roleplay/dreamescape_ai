import logging
from dataclasses import dataclass
from uuid import UUID

from src.application.chats.settings import ChatSettings
from src.application.ports import IChatSettingsGateway, IChatSettingsService

logger = logging.getLogger(__name__)


@dataclass
class ChatSettingsService(IChatSettingsService):
	chat_settings_gateway: IChatSettingsGateway

	async def get_for_chat(self, chat_uuid: UUID) -> ChatSettings | None:
		logger.info(f"Getting chat settings: {chat_uuid}")
		settings = await self.chat_settings_gateway.get_for_chat(chat_uuid)
		logger.info(f"Retrieved chat settings for: {chat_uuid}")
		return settings

	async def upsert(self, chat_uuid: UUID, settings: ChatSettings) -> ChatSettings:
		logger.info(f"Upserting chat settings: {chat_uuid}")
		result = await self.chat_settings_gateway.upsert(chat_uuid, settings)
		logger.info(f"Successfully upserted chat settings: {chat_uuid}")
		return result
