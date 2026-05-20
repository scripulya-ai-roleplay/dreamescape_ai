import logging
from dataclasses import dataclass
from typing import Any

import jwt
from jwt import InvalidTokenError

from src.application.ports import IJWTService
from src.domain.models import User, UserRole


@dataclass(kw_only=True, frozen=True, slots=True)
class JWTService(IJWTService):
	logger: logging.Logger
	private_key: str
	public_key: str
	algorithm: str = "ES256"

	def create_token(self, user: User) -> str:
		self.logger.debug("Creating JWT token for user: %s", user.username)

		payload: dict[str, Any] = {
			"username": user.username,
			"role": user.role.value,
		}

		token = jwt.encode(payload, self.private_key, algorithm=self.algorithm)
		self.logger.info("JWT token created for user: %s", user.username)

		return token

	def verify_token(self, token: str) -> User:
		self.logger.debug("Verifying JWT token")

		try:
			payload = jwt.decode(token, self.public_key, algorithms=[self.algorithm])

			user = User(
				username=payload["username"],
				role=UserRole(payload["role"]),
			)

			self.logger.info("JWT token verified for user: %s", user.username)
			return user

		except InvalidTokenError as e:
			self.logger.warning("Invalid JWT token: %s", e)
			raise
		except (KeyError, ValueError) as e:
			self.logger.warning("Invalid token payload: %s", e)
			msg = "Invalid token payload"
			raise InvalidTokenError(msg) from e
