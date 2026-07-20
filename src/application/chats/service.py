import logging
from dataclasses import dataclass
from uuid import UUID

from src.infrastructure.logging.logger import Logger
from src.application.ports import (
	IAuthorizationService,
	IChatService,
	IChatGateway,
	Page,
)
from src.application.chats.schemas import ChatFilterDTO
from src.domain.models import Chat


@dataclass
class ChatService(IChatService):
	chat_gateway: IChatGateway
	authz: IAuthorizationService
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)

	async def start_chat(self, chat: Chat) -> UUID:
		self.logger.info(f"Starting chat: {chat.title}")

		chat_id = await self.chat_gateway.create(chat)
		self.logger.info(f"Successfully started chat with ID: {chat_id}")
		return chat_id

	async def _require_owned(self, chat_uuid: UUID, actor_id: UUID) -> Chat:
		chat = await self.chat_gateway.get_one(chat_uuid)
		self.authz.require_owned(owner_id=chat.user_id, actor_id=actor_id, noun="chat")
		return chat

	async def get_one(self, chat_uuid: UUID, actor_id: UUID) -> Chat:
		self.logger.info(f"Getting chat: {chat_uuid}")
		return await self._require_owned(chat_uuid, actor_id)

	async def search(self, dto: ChatFilterDTO, actor_id: UUID) -> Page[Chat]:
		self.logger.info(f"Searching chats with filters: {dto}")
		return await self.chat_gateway.search(dto, actor_id=actor_id)

	async def delete(self, chat_uuid: UUID, actor_id: UUID) -> UUID:
		self.logger.info(f"Deleting chat: {chat_uuid}")
		await self._require_owned(chat_uuid, actor_id)
		return await self.chat_gateway.delete(chat_uuid)

	async def update(self, target_chat_uuid: UUID, chat_name: str, actor_id: UUID) -> UUID:
		self.logger.info(f"Updating chat {target_chat_uuid} with name: {chat_name}")
		await self._require_owned(target_chat_uuid, actor_id)
		return await self.chat_gateway.update(target_chat_uuid, chat_name)

	async def set_persona(self, chat_uuid: UUID, user_character_id: UUID, actor_id: UUID) -> UUID:
		self.logger.info(f"Setting persona {user_character_id} on chat {chat_uuid}")
		await self._require_owned(chat_uuid, actor_id)
		return await self.chat_gateway.set_persona(chat_uuid, user_character_id)
