import logging
from dataclasses import dataclass
from uuid import UUID

from application.ports import IUnitOfWork
from src.application.message.schemas import MessagesFilterDto
from src.application.ports import IMessageService, IMessageGateway, Page
from src.domain.models import Message

logger = logging.getLogger(__name__)


@dataclass
class MessageService(IMessageService):
	message_gateway: IMessageGateway
	_uow: IUnitOfWork

	async def send_message(self, message: Message) -> Message:
		async with self._uow:
			logger.info(f"Sending message to chat: {message.chat_id}")

			result = await self.message_gateway.create(message)
			logger.info(f"Successfully sent message with ID: {result.id}")
			return result

	async def search(self, dto: MessagesFilterDto) -> Page[Message]:
		logger.info(f"Searching messages with filters: {dto}")

		result = await self.message_gateway.search(dto)
		logger.info(f"Found {result.count} messages")
		return result

	async def get_one(self, message_uuid: UUID) -> Message:
		logger.info(f"Getting message: {message_uuid}")

		message = await self.message_gateway.get_one(message_uuid)
		logger.info(f"Successfully retrieved message: {message_uuid}")
		return message

	async def update(self, message_uuid: UUID, updated_text: str) -> UUID:
		logger.info(f"Updating message: {message_uuid}")

		result = await self.message_gateway.update(message_uuid, updated_text)
		logger.info(f"Successfully updated message: {message_uuid}")
		return result

	async def delete(self, message_uuid: UUID) -> UUID:
		logger.info(f"Deleting message: {message_uuid}")

		result = await self.message_gateway.delete(message_uuid)
		logger.info(f"Successfully deleted message: {message_uuid}")
		return result
