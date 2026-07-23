import logging
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from src.infrastructure.logging.logger import Logger
from src.application.ports.common import IUnitOfWork
from src.application.message.schemas import MessagesFilterDto
from src.application.ports.authorization import IAuthorizationService
from src.application.ports.messages import IMessageService, IMessageGateway
from src.application.ports.common import Page
from src.application.ports.llm import LLMResult
from src.domain.models import ChatRoles, Message, MessageStatus


@dataclass
class MessageService(IMessageService):
	message_gateway: IMessageGateway
	authz: IAuthorizationService
	_uow: IUnitOfWork
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)

	async def send_message(self, message: Message) -> Message:
		async with self._uow:
			self.logger.info(f"Sending message to chat: {message.chat_id}")

			result = await self.message_gateway.create(message)
			self.logger.info(f"Successfully sent message with ID: {result.id}")
			return result

	async def search(self, dto: MessagesFilterDto, actor_id: UUID) -> Page[Message]:
		self.logger.info(f"Searching messages with filters: {dto}")
		return await self.message_gateway.search(dto, actor_id=actor_id)

	async def _require_owned(self, message_uuid: UUID, actor_id: UUID) -> Message:
		message = await self.message_gateway.get_one(message_uuid)
		owner = await self.message_gateway.get_chat_owner_for_message(message_uuid)
		self.authz.require_owned(owner_id=owner, actor_id=actor_id, noun="message")
		return message

	async def get_one(self, message_uuid: UUID, actor_id: UUID) -> Message:
		self.logger.info(f"Getting message: {message_uuid}")
		return await self._require_owned(message_uuid, actor_id)

	async def update(self, message_uuid: UUID, updated_text: str, actor_id: UUID) -> UUID:
		self.logger.info(f"Updating message: {message_uuid}")
		await self._require_owned(message_uuid, actor_id)
		async with self._uow:
			return await self.message_gateway.update(message_uuid, updated_text)

	async def delete(self, message_uuid: UUID, actor_id: UUID) -> UUID:
		self.logger.info(f"Deleting message: {message_uuid}")
		await self._require_owned(message_uuid, actor_id)
		async with self._uow:
			return await self.message_gateway.delete(message_uuid)

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

	async def record_failed_generation(self, chat_id: UUID, reason: str) -> Message:
		self.logger.info("Recording failed generation for chat: %s", chat_id)
		async with self._uow:
			return await self.message_gateway.create(
				Message(
					message=reason,
					chat_id=chat_id,
					role=ChatRoles.MODEL,
					status=MessageStatus.FAILED,
				)
			)

	async def latest_model_message(self, chat_id: UUID) -> Optional[Message]:
		return await self.message_gateway.latest_model_message(chat_id)
