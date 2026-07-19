import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
	access_token_expire_minutes: int = 30

	def create_token(self, user: User) -> str:
		# User.id is optional in the domain model, but a token without a subject
		# can never be verified back. Fail fast instead of emitting sub/user_id="None".
		if user.id is None:
			raise ValueError("Cannot create token: user.id is missing")

		self.logger.debug("Creating JWT token for user id: %s", user.id)

		# Agreed token shape: {sub, user_id, role, exp}. ``sub`` and ``user_id``
		# both carry the user id (sub is the standard JWT subject claim).
		payload: dict[str, Any] = {
			"sub": str(user.id),
			"user_id": str(user.id),
			"role": user.role.value,
			"exp": datetime.now(timezone.utc) + timedelta(minutes=self.access_token_expire_minutes),
		}

		# Use private_key as the secret key for HS256, or actual private key for ES256
		token = jwt.encode(payload, self.private_key, algorithm=self.algorithm)
		self.logger.info("JWT token created for user id: %s", user.id)

		return token

	def verify_token(self, token: str) -> User:
		self.logger.debug("Verifying JWT token")

		try:
			# For HS256, use private_key as secret key; for ES256, use public_key
			secret_or_key = self.private_key if self.algorithm.startswith("HS") else self.public_key

			payload = jwt.decode(token, secret_or_key, algorithms=[self.algorithm])

			raw_id = payload.get("user_id") or payload.get("sub")
			if raw_id is None:
				msg = "Invalid token payload"
				raise InvalidTokenError(msg)

			user = User(
				id=UUID(raw_id),
				username=None,
				role=UserRole(payload["role"]),
			)

			self.logger.info("JWT token verified for user id: %s", user.id)
			return user

		except InvalidTokenError as e:
			self.logger.warning("Invalid JWT token: %s", e)
			raise
		except (KeyError, ValueError) as e:
			self.logger.warning("Invalid token payload: %s", e)
			msg = "Invalid token payload"
			raise InvalidTokenError(msg) from e
