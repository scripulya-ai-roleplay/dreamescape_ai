import logging
from dataclasses import dataclass
from uuid import UUID

from src.application.ports import IUserService, IUserGateway, Page, IUnitOfWork
from src.domain.models import User
from src.application.user.schemas import UserDTO


@dataclass
class UserService(IUserService):
	_user_gateway: IUserGateway
	uow: IUnitOfWork
	logger: logging.Logger

	async def find_users_by_dto(self, user_filters_dto: UserDTO) -> Page[User]:
		self.logger.info(f"Searching users with filters: {user_filters_dto}")

		try:
			result = await self._user_gateway.find_users_by_filters(
				user_filters_dto, user_filters_dto.offset, user_filters_dto.limit
			)
			self.logger.info(f"Found {result.count} users")
			return result
		except Exception as e:
			self.logger.error(f"Failed to find users: {e}")
			raise

	async def create_user(self, user: User) -> User:
		self.logger.info(f"Creating user: {user.username or user.test_username}")

		async with self.uow:
			if not user.google_id and not (user.username or user.test_username):
				raise ValueError("User must have either google_id or username")

			if user.google_id:
				existing_users = await self._user_gateway.find_users_by_filters(
					UserDTO(google_ids=[user.google_id]), limit=1, offset=0
				)
				if existing_users.items:
					raise ValueError(f"User with google_id {user.google_id} already exists")

			created_user = await self._user_gateway.create_user(user)
			self.logger.info(f"Successfully created user with ID: {created_user.id}")
			return created_user

	async def delete_user(self, user_id: UUID) -> None:
		self.logger.info(f"Deleting user: {user_id}")

		async with self.uow:
			existing_user = await self._user_gateway.get_user_by_id(user_id)
			if not existing_user:
				raise ValueError(f"User with ID {user_id} not found")

			await self._user_gateway.delete_user(user_id)
			self.logger.info(f"Successfully deleted user: {user_id}")
