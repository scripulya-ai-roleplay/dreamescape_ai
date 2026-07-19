import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, delete, func, and_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.infrastructure.logging.logger import Logger
from src.application.ports import IChatGateway, Page
from src.application.chats.schemas import ChatFilterDTO
from src.domain.models import Chat
from src.infrastructure.database.models import Chat as ChatModel, Character as CharacterModel


@dataclass
class ChatGateway(IChatGateway):
	_session: AsyncSession
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)

	async def create(self, chat: Chat) -> UUID:
		self.logger.info(f"Creating chat in database: {chat.title}")

		chat_model = ChatModel(
			name=chat.title,  # Database uses 'name' field
			user_id=chat.user_id,
			scene_id=chat.scene_id,
			user_character_id=chat.user_character_id,
		)

		self._session.add(chat_model)
		await self._session.commit()
		await self._session.refresh(chat_model)

		self.logger.info(f"Successfully created chat with ID: {chat_model.id}")
		return chat_model.id

	async def get_one(self, chat_uuid: UUID) -> Chat:
		self.logger.info(f"Getting chat by ID: {chat_uuid}")

		query = select(ChatModel).options(selectinload(ChatModel.messages)).where(ChatModel.id == chat_uuid)

		result = await self._session.execute(query)
		chat_model = result.scalar_one_or_none()

		if not chat_model:
			raise ValueError(f"Chat with ID {chat_uuid} not found")

		return self._to_domain_chat(chat_model)

	async def search(self, dto: ChatFilterDTO) -> Page[Chat]:
		self.logger.info(f"Searching chats with filters: {dto}")

		query = select(ChatModel).options(selectinload(ChatModel.messages))

		conditions = []

		if dto.ids:
			conditions.append(ChatModel.id.in_([str(id_) for id_ in dto.ids]))

		if dto.titles:
			conditions.append(ChatModel.name.in_(dto.titles))  # Database uses 'name' field

		if dto.user_ids:
			conditions.append(ChatModel.user_id.in_([str(id_) for id_ in dto.user_ids]))

		if dto.scene_ids:
			conditions.append(ChatModel.scene_id.in_([str(id_) for id_ in dto.scene_ids]))

		if conditions:
			query = query.where(and_(*conditions))

		count_query = select(func.count(ChatModel.id))
		if conditions:
			count_query = count_query.where(and_(*conditions))

		count_result = await self._session.execute(count_query)
		total_count = count_result.scalar() or 0

		query = query.offset(dto.offset).limit(dto.limit)

		result = await self._session.execute(query)
		chat_models = result.scalars().all()

		domain_chats = [self._to_domain_chat(chat_model) for chat_model in chat_models]

		self.logger.info(f"Found {len(domain_chats)} chats out of {total_count} total")

		return Page[Chat](items=domain_chats, count=total_count, offset=dto.offset, limit=dto.limit)

	async def delete(self, chat_uuid: UUID) -> UUID:
		self.logger.info(f"Deleting chat from database: {chat_uuid}")

		query = delete(ChatModel).where(ChatModel.id == chat_uuid)
		result = await self._session.execute(query)

		if result.rowcount == 0:
			raise ValueError(f"Chat with ID {chat_uuid} not found")

		await self._session.commit()
		self.logger.info(f"Successfully deleted chat: {chat_uuid}")

		return chat_uuid

	async def update(self, target_chat_uuid: UUID, chat_name: str) -> UUID:
		self.logger.info(f"Updating chat {target_chat_uuid} with name: {chat_name}")

		query = update(ChatModel).where(ChatModel.id == target_chat_uuid).values(name=chat_name)

		result = await self._session.execute(query)

		if result.rowcount == 0:
			raise ValueError(f"Chat with ID {target_chat_uuid} not found")

		await self._session.commit()
		self.logger.info(f"Successfully updated chat: {target_chat_uuid}")

		return target_chat_uuid

	async def set_persona(self, chat_uuid: UUID, user_character_id: UUID) -> UUID:
		self.logger.info(f"Setting persona {user_character_id} on chat {chat_uuid}")

		character_exists = await self._session.scalar(
			select(func.count()).select_from(CharacterModel).where(CharacterModel.id == user_character_id)
		)
		if not character_exists:
			raise ValueError(f"Character with ID {user_character_id} not found")

		result = await self._session.execute(
			update(ChatModel).where(ChatModel.id == chat_uuid).values(user_character_id=user_character_id)
		)
		if result.rowcount == 0:
			raise ValueError(f"Chat with ID {chat_uuid} not found")

		await self._session.commit()
		self.logger.info(f"Successfully set persona on chat: {chat_uuid}")

		return chat_uuid

	def _to_domain_chat(self, chat_model: ChatModel) -> Chat:
		return Chat(
			id=chat_model.id,
			title=chat_model.name,  # Convert database 'name' to domain 'title'
			user_id=chat_model.user_id,
			scene_id=chat_model.scene_id,
			user_character_id=chat_model.user_character_id,
		)
