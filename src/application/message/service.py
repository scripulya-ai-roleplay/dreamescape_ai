import logging
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from src.infrastructure.logging.logger import Logger
from src.application.ports import IUnitOfWork
from src.application.message.schemas import MessagesFilterDto
from src.application.ports import IMessageService, IMessageGateway, Page, LLMResult
from src.domain.models import ChatRoles, Message, MessageStatus


@dataclass
class MessageService(IMessageService):
	message_gateway: IMessageGateway
	_uow: IUnitOfWork
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)

	async def send_message(self, message: Message) -> Message:
		async with self._uow:
			self.logger.info(f"Sending message to chat: {message.chat_id}")

			result = await self.message_gateway.create(message)
			self.logger.info(f"Successfully sent message with ID: {result.id}")
			return result

	async def search(self, dto: MessagesFilterDto) -> Page[Message]:
		self.logger.info(f"Searching messages with filters: {dto}")

		result = await self.message_gateway.search(dto)
		self.logger.info(f"Found {result.count} messages")
		return result

	async def get_one(self, message_uuid: UUID) -> Message:
		self.logger.info(f"Getting message: {message_uuid}")

		message = await self.message_gateway.get_one(message_uuid)
		self.logger.info(f"Successfully retrieved message: {message_uuid}")
		return message

	async def update(self, message_uuid: UUID, updated_text: str) -> UUID:
		self.logger.info(f"Updating message: {message_uuid}")

		result = await self.message_gateway.update(message_uuid, updated_text)
		self.logger.info(f"Successfully updated message: {message_uuid}")
		return result

	async def delete(self, message_uuid: UUID) -> UUID:
		self.logger.info(f"Deleting message: {message_uuid}")

		result = await self.message_gateway.delete(message_uuid)
		self.logger.info(f"Successfully deleted message: {message_uuid}")
		return result

	async def append_model_message(self, result: LLMResult) -> Message:
		if result.error is not None:
			content = result.error.message or result.error.reason or "LLM generation failed"
			status = MessageStatus.FAILED
		elif result.message is not None:
			content = result.message.message
			status = MessageStatus.COMPLETED
		else:
			self.logger.warning("LLMResult for chat_id=%s has neither message nor error", result.chat_id)
			content = "LLM returned neither a message nor an error"
			status = MessageStatus.FAILED

		async with self._uow:
			return await self.message_gateway.create(
				Message(
					message=content,
					chat_id=result.chat_id,
					role=ChatRoles.MODEL,
					status=status,
				)
			)

	async def latest_model_message(self, chat_id: UUID) -> Optional[Message]:
		return await self.message_gateway.latest_model_message(chat_id)
