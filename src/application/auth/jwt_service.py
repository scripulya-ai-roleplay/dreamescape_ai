import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

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
			"sub": str(user.id),  # Standard JWT subject claim for user ID
			"username": user.username,
			"role": user.role.value,
		}

		# Use private_key as the secret key for HS256, or actual private key for ES256
		secret_or_key = self.private_key
		token = jwt.encode(payload, secret_or_key, algorithm=self.algorithm)
		self.logger.info("JWT token created for user: %s", user.username)

		return token

	def verify_token(self, token: str) -> User:
		self.logger.debug("Verifying JWT token")

		try:
			# For HS256, use private_key as secret key; for ES256, use public_key
			if self.algorithm.startswith("HS"):
				secret_or_key = self.private_key
			else:
				secret_or_key = self.public_key

			payload = jwt.decode(token, secret_or_key, algorithms=[self.algorithm])

			user = User(
				id=UUID(payload["sub"]),  # Extract user ID from sub field
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
