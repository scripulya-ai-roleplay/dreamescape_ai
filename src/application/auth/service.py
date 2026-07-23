import logging
from dataclasses import dataclass

from src.infrastructure.logging.logger import Logger
from src.application.ports.auth import IAuthService, IPasswordHasher
from src.application.ports.user import IUserGateway
from src.domain.models import User
from src.application.auth.errors import InvalidCredentialsError

# Substituted for a stored hash when the username is unknown, so a missing-user
# login still pays the argon2 cost and matches a wrong-password attempt's timing
# (prevents user enumeration via response-time side channels).
_DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$+jN0Vldj69N4fUgOdzx9bQ$dqM9quBbp6EIxTLOFy2HYb4+pMF4TWf/3TtHEH8UJn4"


@dataclass
class AuthService(IAuthService):
	_user_gateway: IUserGateway
	_password_hasher: IPasswordHasher
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)

	async def authenticate(self, username: str, password: str) -> User:
		record = await self._user_gateway.get_user_auth(username)

		stored_hash = record.password_hash if record is not None and record.password_hash else _DUMMY_HASH
		password_ok = self._password_hasher.verify_password(password, stored_hash)

		if record is None or not password_ok:
			self.logger.info("Failed password login for username: %s", username)
			raise InvalidCredentialsError()

		self.logger.info("Password login succeeded for user id: %s", record.id)
		return User(id=record.id, username=record.username, role=record.role)
