import logging
from dataclasses import dataclass
from uuid import UUID

from src.infrastructure.logging.logger import Logger
from src.application.ports import (
	IChatService,
	IChatGateway,
	Page,
)
from src.application.chats.schemas import ChatFilterDTO
from src.domain.models import Chat


@dataclass
class ChatService(IChatService):
	chat_gateway: IChatGateway
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)

	async def start_chat(self, chat: Chat) -> UUID:
		self.logger.info(f"Starting chat: {chat.title}")

		chat_id = await self.chat_gateway.create(chat)
		self.logger.info(f"Successfully started chat with ID: {chat_id}")
		return chat_id

	async def get_one(self, chat_uuid: UUID) -> Chat:
		self.logger.info(f"Getting chat: {chat_uuid}")

		chat = await self.chat_gateway.get_one(chat_uuid)
		self.logger.info(f"Successfully retrieved chat: {chat_uuid}")
		return chat

	async def search(self, dto: ChatFilterDTO) -> Page[Chat]:
		self.logger.info(f"Searching chats with filters: {dto}")

		result = await self.chat_gateway.search(dto)
		self.logger.info(f"Found {result.count} chats")
		return result

	async def delete(self, chat_uuid: UUID) -> UUID:
		self.logger.info(f"Deleting chat: {chat_uuid}")

		result = await self.chat_gateway.delete(chat_uuid)
		self.logger.info(f"Successfully deleted chat: {chat_uuid}")
		return result

	async def update(self, target_chat_uuid: UUID, chat_name: str) -> UUID:
		self.logger.info(f"Updating chat {target_chat_uuid} with name: {chat_name}")

		result = await self.chat_gateway.update(target_chat_uuid, chat_name)
		self.logger.info(f"Successfully updated chat: {target_chat_uuid}")
		return result

	async def set_persona(self, chat_uuid: UUID, user_character_id: UUID) -> UUID:
		self.logger.info(f"Setting persona {user_character_id} on chat {chat_uuid}")

		result = await self.chat_gateway.set_persona(chat_uuid, user_character_id)
		self.logger.info(f"Successfully set persona on chat: {chat_uuid}")
		return result
