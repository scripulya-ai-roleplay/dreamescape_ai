import logging
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from sqlalchemy import select, delete, func, and_, update, exists
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.logging.logger import Logger
from src.application.ports import IMessageGateway, Page
from src.application.message.schemas import MessagesFilterDto
from src.domain.models import Message, ChatRoles, MessageStatus
from src.infrastructure.database.models import Message as MessageModel, Chat as ChatModel


@dataclass
class MessageGateway(IMessageGateway):
	_session: AsyncSession
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)

	async def create(self, message: Message) -> Message:
		self.logger.info(f"Creating message in database for chat: {message.chat_id}")
		message_model = MessageModel(
			chat_id=message.chat_id,
			role=message.role.value,
			content=message.message,  # Domain uses 'message', DB uses 'content'
			status=message.status.value,
			cost_crystals=0,
		)

		self._session.add(message_model)
		await self._session.flush()
		await self._session.refresh(message_model)

		created_message = self._to_domain_message(message_model)
		self.logger.info(f"Successfully created message with ID: {created_message.id}")

		return created_message

	async def search(self, dto: MessagesFilterDto, actor_id: UUID | None = None) -> Page[Message]:
		self.logger.info(f"Searching messages with filters: {dto} (actor={actor_id})")

		# Build query with filters
		query = select(MessageModel)

		conditions = []

		# EXISTS keeps the SELECT a plain MessageModel; a None actor matches nothing
		# (chat.user_id is non-nullable).
		conditions.append(exists().where(and_(ChatModel.id == MessageModel.chat_id, ChatModel.user_id == actor_id)))

		if dto.ids:
			conditions.append(MessageModel.id.in_([str(id_) for id_ in dto.ids]))

		if dto.chats_ids:
			conditions.append(MessageModel.chat_id.in_([str(id_) for id_ in dto.chats_ids]))

		if dto.roles:
			role_values = [role.value for role in dto.roles]
			conditions.append(MessageModel.role.in_(role_values))

		query = query.where(and_(*conditions))

		# Get total count
		count_query = select(func.count(MessageModel.id)).where(and_(*conditions))

		count_result = await self._session.execute(count_query)
		total_count = count_result.scalar() or 0

		# Apply pagination and ordering (newest first)
		query = query.order_by(MessageModel.created_at.desc()).offset(dto.offset).limit(dto.limit)

		result = await self._session.execute(query)
		message_models = result.scalars().all()

		# Convert to domain models
		domain_messages = [self._to_domain_message(message_model) for message_model in message_models]

		self.logger.info(f"Found {len(domain_messages)} messages out of {total_count} total")

		return Page[Message](items=domain_messages, count=total_count, offset=dto.offset, limit=dto.limit)

	async def get_one(self, message_uuid: UUID) -> Message:
		self.logger.info(f"Getting message by ID: {message_uuid}")

		query = select(MessageModel).where(MessageModel.id == message_uuid)

		result = await self._session.execute(query)
		message_model = result.scalar_one_or_none()

		if not message_model:
			raise ValueError(f"Message with ID {message_uuid} not found")

		return self._to_domain_message(message_model)

	async def get_chat_owner_for_message(self, message_uuid: UUID) -> UUID | None:
		self.logger.info(f"Resolving chat owner for message: {message_uuid}")

		stmt = (
			select(ChatModel.user_id)
			.join(MessageModel, MessageModel.chat_id == ChatModel.id)
			.where(MessageModel.id == message_uuid)
		)
		return await self._session.scalar(stmt)

	async def update(self, message_uuid: UUID, updated_text: str) -> UUID:
		self.logger.info(f"Updating message {message_uuid} with new text")

		query = (
			update(MessageModel)
			.where(MessageModel.id == message_uuid)
			.values(content=updated_text, updated_at=func.now())
		)

		result = await self._session.execute(query)

		if result.rowcount == 0:
			raise ValueError(f"Message with ID {message_uuid} not found")

		self.logger.info(f"Successfully updated message: {message_uuid}")

		return message_uuid

	async def delete(self, message_uuid: UUID) -> UUID:
		self.logger.info(f"Deleting message from database: {message_uuid}")

		query = delete(MessageModel).where(MessageModel.id == message_uuid)
		result = await self._session.execute(query)

		if result.rowcount == 0:
			raise ValueError(f"Message with ID {message_uuid} not found")

		self.logger.info(f"Successfully deleted message: {message_uuid}")

		return message_uuid

	async def latest_model_message(self, chat_id: UUID) -> Optional[Message]:
		self.logger.info(f"Getting latest model message for chat: {chat_id}")
		query = (
			select(MessageModel)
			.where(MessageModel.chat_id == chat_id, MessageModel.role == ChatRoles.MODEL.value)
			.order_by(MessageModel.created_at.desc())
			.limit(1)
		)
		result = await self._session.execute(query)
		message_model = result.scalar_one_or_none()
		return self._to_domain_message(message_model) if message_model else None

	def _to_domain_message(self, message_model: MessageModel) -> Message:
		# Convert string role/status back to enums
		role = ChatRoles(message_model.role)
		status = MessageStatus(message_model.status)

		return Message(
			id=message_model.id,
			message=message_model.content,  # Convert DB 'content' to domain 'message'
			chat_id=message_model.chat_id,
			role=role,
			status=status,
			date_created=message_model.created_at,  # Convert DB 'created_at' to domain 'date_created'
			date_edited=message_model.updated_at,  # Convert DB 'updated_at' to domain 'date_edited'
		)
