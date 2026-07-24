from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest

from src.application.auth.errors import InvalidCredentialsError
from src.application.auth.schemas import UserAuthRecord
from src.application.auth.service import _DUMMY_HASH, AuthService
from src.domain.models import UserRole


@pytest.mark.unit
class TestAuthService:
	@pytest.fixture
	def gateway(self):
		return AsyncMock()

	@pytest.fixture
	def hasher(self):
		return Mock()

	@pytest.fixture
	def service(self, gateway, hasher):
		return AuthService(_user_gateway=gateway, _password_hasher=hasher, logger=Mock())

	@pytest.fixture
	def mobile_record(self):
		return UserAuthRecord(
			id=UUID("00000000-0000-0000-0000-000000000001"),
			username="mobile",
			role=UserRole.API,
			password_hash="$argon2id$v=19$m=65536,t=3,p=4$storedhash",
		)

	async def test_authenticate_success_returns_user(self, service, gateway, hasher, mobile_record):
		gateway.get_user_auth.return_value = mobile_record
		hasher.verify_password.return_value = True

		user = await service.authenticate("mobile", "password")

		assert user.id == mobile_record.id
		assert user.role == UserRole.API
		assert user.username == "mobile"
		hasher.verify_password.assert_called_once_with("password", mobile_record.password_hash)

	async def test_authenticate_wrong_password_raises(self, service, gateway, hasher, mobile_record):
		gateway.get_user_auth.return_value = mobile_record
		hasher.verify_password.return_value = False

		with pytest.raises(InvalidCredentialsError) as exc:
			await service.authenticate("mobile", "wrong")

		assert exc.value.message == "Invalid username or password"
		hasher.verify_password.assert_called_once_with("wrong", mobile_record.password_hash)

	async def test_unknown_user_runs_dummy_verify_then_401(self, service, gateway, hasher):
		gateway.get_user_auth.return_value = None
		hasher.verify_password.return_value = False

		with pytest.raises(InvalidCredentialsError):
			await service.authenticate("ghost", "password")

		hasher.verify_password.assert_called_once_with("password", _DUMMY_HASH)

	async def test_user_without_password_hash_runs_dummy_verify(self, service, gateway, hasher):
		gateway.get_user_auth.return_value = UserAuthRecord(
			id=UUID("11111111-2222-3333-4444-555555555555"),
			username="google_only",
			role=UserRole.API,
			password_hash=None,
		)
		hasher.verify_password.return_value = False

		with pytest.raises(InvalidCredentialsError):
			await service.authenticate("google_only", "password")

		hasher.verify_password.assert_called_once_with("password", _DUMMY_HASH)

	async def test_failure_is_generic_no_username_hint(self, service, gateway, hasher, mobile_record):
		gateway.get_user_auth.return_value = mobile_record
		hasher.verify_password.return_value = False
		wrong_pw = await _capture(service, "mobile", "bad")

		gateway.get_user_auth.return_value = None
		unknown = await _capture(service, "ghost", "bad")

		assert wrong_pw.message == unknown.message


async def _capture(service: AuthService, username: str, password: str) -> InvalidCredentialsError:
	try:
		await service.authenticate(username, password)
	except InvalidCredentialsError as exc:
		return exc
	raise AssertionError("authenticate did not raise InvalidCredentialsError")
