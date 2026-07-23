"""THIS IS AUTHENTICATION MODULE. NOT AUTHORIZATION"""

import abc

from src.domain.models import User


class IJWTService(abc.ABC):
	@abc.abstractmethod
	def create_token(self, user: User) -> str: ...

	@abc.abstractmethod
	def verify_token(self, token: str) -> User: ...


class IPasswordHasher(abc.ABC):
	@abc.abstractmethod
	def hash_password(self, password: str) -> str: ...

	@abc.abstractmethod
	def verify_password(self, password: str, password_hash: str) -> bool: ...


class IAuthService(abc.ABC):
	@abc.abstractmethod
	async def authenticate(self, username: str, password: str) -> User: ...
