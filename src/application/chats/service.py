import logging
from dataclasses import dataclass
from uuid import UUID

from src.application.chats.schemas import ChatFilterDTO
from src.application.ports.authorization import IAuthorizationService
from src.application.ports.chats import IChatGateway, IChatService
from src.application.ports.common import IUnitOfWork, Page
from src.application.ports.messages import IMessageGateway
from src.application.ports.scenes import IInitialMessageGateway
from src.domain.models import Chat, ChatRoles, Message, MessageStatus
from src.infrastructure.logging.logger import Logger


@dataclass
class ChatService(IChatService):
	chat_gateway: IChatGateway
	initial_message_gateway: IInitialMessageGateway
	message_gateway: IMessageGateway
	uow: IUnitOfWork
	authz: IAuthorizationService
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)

	async def start_chat(self, chat: Chat) -> UUID:
		self.logger.info(f"Starting chat: {chat.title}")

		async with self.uow:
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
		async with self.uow:
			return await self.chat_gateway.delete(chat_uuid)

	async def update(self, target_chat_uuid: UUID, chat_name: str, actor_id: UUID) -> UUID:
		self.logger.info(f"Updating chat {target_chat_uuid} with name: {chat_name}")
		await self._require_owned(target_chat_uuid, actor_id)
		async with self.uow:
			return await self.chat_gateway.update(target_chat_uuid, chat_name)

	async def set_persona(self, chat_uuid: UUID, user_character_id: UUID, actor_id: UUID) -> UUID:
		self.logger.info(f"Setting persona {user_character_id} on chat {chat_uuid}")
		await self._require_owned(chat_uuid, actor_id)
		async with self.uow:
			return await self.chat_gateway.set_persona(chat_uuid, user_character_id)

	async def choose_initial_message(self, chat_uuid: UUID, initial_message_uuid: UUID, actor_id: UUID) -> Message:
		self.logger.info(f"Choosing initial message {initial_message_uuid} for chat {chat_uuid}")

		chat = await self.chat_gateway.get_one(chat_uuid)
		self.authz.require_owned(owner_id=chat.user_id, actor_id=actor_id, noun="chat")

		initial_message = await self.initial_message_gateway.get_one(initial_message_uuid)
		# The chosen initial message must belong to the scene the chat was started
		# from, otherwise a user could seed an arbitrary scene's greeting into a chat.
		if initial_message.scene_id != chat.scene_id:
			raise ValueError("Initial message does not belong to this chat's scene")

		if chat.initial_message_id is not None:
			raise ValueError("Chat already has an initial message")

		# Seed the greeting as a real model message and record the choice on the
		# chat in one transaction; the message then behaves like any other
		# (editable/deletable) and flows through to the LLM as history.
		async with self.uow:
			await self.chat_gateway.set_initial_message(chat_uuid, initial_message_uuid)
			seeded = await self.message_gateway.create(
				Message(
					message=initial_message.text,
					chat_id=chat_uuid,
					role=ChatRoles.MODEL,
					status=MessageStatus.COMPLETED,
				)
			)
		self.logger.info(f"Successfully seeded initial message for chat: {chat_uuid}")
		return seeded
