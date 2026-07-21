import logging
from dataclasses import dataclass, field

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from src.application.ports import IPasswordHasher


@dataclass(kw_only=True, frozen=True, slots=True)
class Argon2PasswordHasher(IPasswordHasher):
	_hasher: PasswordHasher = field(default_factory=PasswordHasher)
	logger: logging.Logger

	def hash_password(self, password: str) -> str:
		return self._hasher.hash(password)

	def verify_password(self, password: str, password_hash: str) -> bool:
		try:
			self._hasher.verify(password_hash, password)
			return True
		except VerifyMismatchError:
			return False
		except (VerificationError, InvalidHashError):
			self.logger.warning("Password hash could not be verified", exc_info=True)
			return False
