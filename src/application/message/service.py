import logging
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from src.application.ports import IUnitOfWork
from src.application.message.schemas import MessagesFilterDto
from src.application.ports import IMessageService, IMessageGateway, Page, LLMResult
from src.domain.models import Message, MessageStatus

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

	async def complete_pending(self, result: LLMResult) -> Optional[Message]:
		"""Resolve the pending model message for result.chat_id.

		COMPLETED + the reply text on success; FAILED + the error message on error
		(or when the agent returned neither). Returns None if nothing was pending.
		"""
		if result.error is not None:
			content = result.error.message or result.error.reason or "LLM generation failed"
			status = MessageStatus.FAILED
		elif result.message is not None:
			content = result.message.message
			status = MessageStatus.COMPLETED
		else:
			logger.warning("LLMResult for chat_id=%s has neither message nor error", result.chat_id)
			content = "LLM returned neither a message nor an error"
			status = MessageStatus.FAILED

		async with self._uow:
			return await self.message_gateway.complete_pending(result.chat_id, content, status)

	async def latest_model_message(self, chat_id: UUID) -> Optional[Message]:
		return await self.message_gateway.latest_model_message(chat_id)
