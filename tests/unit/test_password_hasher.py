from unittest.mock import Mock

import pytest

from src.application.auth.password_hasher import Argon2PasswordHasher


@pytest.mark.unit
class TestArgon2PasswordHasher:
	@pytest.fixture
	def hasher(self):
		return Argon2PasswordHasher(logger=Mock())

	def test_hash_then_verify_roundtrip(self, hasher):
		h = hasher.hash_password("correct horse battery staple")

		assert h != "correct horse battery staple"
		assert hasher.verify_password("correct horse battery staple", h) is True

	def test_verify_rejects_wrong_password(self, hasher):
		h = hasher.hash_password("right")

		assert hasher.verify_password("wrong", h) is False

	def test_hash_differs_per_call(self, hasher):
		assert hasher.hash_password("same") != hasher.hash_password("same")

	def test_verify_malformed_hash_is_false_not_raise(self, hasher):
		assert hasher.verify_password("anything", "not-a-valid-argon2-hash") is False
