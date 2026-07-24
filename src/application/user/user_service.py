import logging
from dataclasses import dataclass
from uuid import UUID

from src.application.ports.authorization import IAuthorizationService
from src.application.ports.common import IUnitOfWork, Page
from src.application.ports.user import IUserGateway, IUserService
from src.application.user.schemas import UserDTO
from src.domain.models import User
from src.infrastructure.logging.logger import Logger


@dataclass
class UserService(IUserService):
	_user_gateway: IUserGateway
	uow: IUnitOfWork
	authz: IAuthorizationService
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)

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
		self.logger.info(f"Creating user: {user.username}")

		async with self.uow:
			if not user.google_id and not user.username:
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

	async def delete_user(self, user_id: UUID, actor_id: UUID) -> None:
		self.logger.info(f"Deleting user: {user_id}")

		existing_user = await self._user_gateway.get_user_by_id(user_id)
		if not existing_user:
			raise ValueError(f"User with ID {user_id} not found")

		self.authz.require_owned(owner_id=existing_user.id, actor_id=actor_id, noun="user")

		async with self.uow:
			await self._user_gateway.delete_user(user_id)
		self.logger.info(f"Successfully deleted user: {user_id}")
