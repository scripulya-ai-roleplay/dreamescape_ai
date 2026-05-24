import logging
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from sqlalchemy import select, delete, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.application.ports import IUserGateway, Page
from src.domain.models import User, UserRole
from src.application.user.schemas import UserDTO
from src.infrastructure.database.models import User as UserModel
from src.domain.models import Character, Scene, Chat


logger = logging.getLogger(__name__)


@dataclass
class UserGateway(IUserGateway):
	_session: AsyncSession

	async def find_users_by_filters(self, filters: UserDTO, offset: int = 10, limit: int = 0) -> Page[User]:
		logger.info(f"Finding users with filters: {filters}")

		# Build query with filters
		query = select(UserModel).options(
			selectinload(UserModel.characters), selectinload(UserModel.scenes), selectinload(UserModel.chats)
		)

		conditions = []

		if filters.user_ids:
			conditions.append(UserModel.id.in_([str(id_) for id_ in filters.user_ids]))

		if filters.usernames:
			conditions.append(UserModel.test_username.in_(filters.usernames))

		if filters.google_ids:
			conditions.append(UserModel.google_id.in_(filters.google_ids))

		if filters.roles:
			# Note: UserModel doesn't have role field, but keeping for interface compatibility
			pass

		if conditions:
			query = query.where(and_(*conditions))

		# Get total count
		count_query = select(func.count(UserModel.id))
		if conditions:
			count_query = count_query.where(and_(*conditions))

		count_result = await self._session.execute(count_query)
		total_count = count_result.scalar() or 0

		# Apply pagination
		query = query.offset(offset).limit(limit)

		result = await self._session.execute(query)
		user_models = result.scalars().all()

		# Convert to domain models
		domain_users = [self._to_domain_user(user_model) for user_model in user_models]

		logger.info(f"Found {len(domain_users)} users out of {total_count} total")

		return Page[User](items=domain_users, count=total_count, offset=offset, limit=limit)

	async def create_user(self, user: User) -> User:
		logger.info(f"Creating user in database: {user.username or user.test_username}")

		user_model = UserModel(
			test_username=user.test_username, google_id=user.google_id, crystal_balance=user.crystal_balance
		)

		self._session.add(user_model)
		await self._session.commit()
		await self._session.refresh(user_model)

		created_user = self._to_domain_user(user_model)
		logger.info(f"Successfully created user with ID: {created_user.id}")

		return created_user

	async def delete_user(self, user_id: UUID) -> None:
		logger.info(f"Deleting user from database: {user_id}")

		# The cascade delete in the database model will handle related records
		query = delete(UserModel).where(UserModel.id == user_id)
		result = await self._session.execute(query)

		if result.rowcount == 0:
			raise ValueError(f"User with ID {user_id} not found")

		await self._session.commit()
		logger.info(f"Successfully deleted user: {user_id}")

	async def get_user_by_id(self, user_id: UUID) -> Optional[User]:
		logger.info(f"Getting user by ID: {user_id}")

		query = (
			select(UserModel)
			.options(selectinload(UserModel.characters), selectinload(UserModel.scenes), selectinload(UserModel.chats))
			.where(UserModel.id == user_id)
		)

		result = await self._session.execute(query)
		user_model = result.scalar_one_or_none()

		if not user_model:
			return None

		return self._to_domain_user(user_model)

	def _to_domain_user(self, user_model: UserModel) -> User:

		# Convert characters
		characters = []
		for char_model in user_model.characters:
			characters.append(
				Character(
					id=char_model.id,
					owner_id=char_model.owner_id,
					name=char_model.name,
					system_prompt=char_model.system_prompt,
					is_public=char_model.is_public,
				)
			)

		# Convert scenes
		scenes = []
		for scene_model in user_model.scenes:
			scenes.append(
				Scene(
					id=scene_model.id,
					owner_id=scene_model.owner_id,
					title=scene_model.title,
					background_prompt=scene_model.background_prompt,
					initial_message_text=scene_model.initial_message_text,
				)
			)

		# Convert chats
		chats = []
		for chat_model in user_model.chats:
			chats.append(
				Chat(
					id=chat_model.id,
					title=chat_model.name,  # Database uses 'name', domain uses 'title'
					user_id=chat_model.user_id,
					scene_id=chat_model.scene_id,
				)
			)

		return User(
			id=user_model.id,
			test_username=user_model.test_username,
			google_id=user_model.google_id,
			role=user_model.role if hasattr(user_model, "role") else UserRole.API,  # Default role
			crystal_balance=user_model.crystal_balance,
			characters=characters,
			scenes=scenes,
			chats=chats,
		)
