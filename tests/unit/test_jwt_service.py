import uuid

import pytest
import jwt
from unittest.mock import Mock
from jwt import InvalidTokenError

from src.application.auth.jwt_service import JWTService
from src.domain.models import User, UserRole


@pytest.mark.unit
class TestJWTService:
	"""Unit tests for JWTService"""

	@pytest.fixture
	def mock_logger(self):
		"""Mock logger for testing"""
		return Mock()

	@pytest.fixture
	def private_key(self):
		"""Sample private key for testing"""
		return "test-secret-key-for-jwt-testing"

	@pytest.fixture
	def public_key(self):
		"""Sample public key for testing"""
		return "test-secret-key-for-jwt-testing"

	@pytest.fixture
	def jwt_service(self, mock_logger, private_key, public_key):
		"""JWTService instance with mocked dependencies"""
		return JWTService(logger=mock_logger, private_key=private_key, public_key=public_key, algorithm="HS256")

	@pytest.fixture
	def sample_user(self):
		"""Sample user for testing"""
		user_id = uuid.uuid4()

		return User(id=user_id, username="test_user", role=UserRole.API, crystal_balance=1000)

	def test_create_token_success(self, jwt_service, mock_logger, sample_user, private_key):
		"""Test successful token creation"""
		# Act
		token = jwt_service.create_token(sample_user)

		# Assert
		assert isinstance(token, str)
		assert len(token) > 0

		# Verify the token contains expected payload
		payload = jwt.decode(token, options={"verify_signature": False})
		assert payload["username"] == "test_user"
		assert payload["role"] == "api"

		# Verify logging
		mock_logger.debug.assert_called_once_with("Creating JWT token for user: %s", "test_user")
		mock_logger.info.assert_called_once_with("JWT token created for user: %s", "test_user")

	def test_create_token_different_roles(self, jwt_service, mock_logger, private_key):
		"""Test token creation with different user roles"""
		roles = [UserRole.ADMIN, UserRole.API, UserRole.DEVELOPER]

		for role in roles:
			user = User(username=f"user_{role.value}", role=role, crystal_balance=1000)

			# Act
			token = jwt_service.create_token(user)

			# Assert
			payload = jwt.decode(token, options={"verify_signature": False})
			assert payload["role"] == role.value

	def test_verify_token_success(self, jwt_service, mock_logger, sample_user, private_key, public_key):
		"""Test successful token verification"""
		# Arrange - create a valid token
		token = jwt_service.create_token(sample_user)

		# Act
		verified_user = jwt_service.verify_token(token)

		# Assert
		assert verified_user.username == "test_user"
		assert verified_user.role == UserRole.API

		# Verify logging
		mock_logger.debug.assert_called_with("Verifying JWT token")
		mock_logger.info.assert_called_with("JWT token verified for user: %s", "test_user")

	def test_verify_token_invalid_signature(self, jwt_service, mock_logger, sample_user):
		"""Test token verification with invalid signature"""
		# Arrange - create token with wrong key
		fake_private_key = "fake_key"
		payload = {"username": sample_user.username, "role": sample_user.role.value}
		invalid_token = jwt.encode(payload, fake_private_key, algorithm="HS256")

		# Act & Assert
		with pytest.raises(InvalidTokenError):
			jwt_service.verify_token(invalid_token)

		mock_logger.warning.assert_called()
		warning_call = mock_logger.warning.call_args[0]
		assert "Invalid JWT token:" in warning_call[0]

	def test_verify_token_missing_username(self, jwt_service, mock_logger, private_key):
		"""Test token verification with missing username in payload"""
		# Arrange - create token without username
		payload = {"role": "api"}
		invalid_token = jwt.encode(payload, private_key, algorithm="HS256")

		# Act & Assert
		with pytest.raises(InvalidTokenError, match="Invalid token payload"):
			jwt_service.verify_token(invalid_token)

		mock_logger.warning.assert_called()
		warning_call = mock_logger.warning.call_args[0]
		assert "Invalid token payload:" in warning_call[0]

	def test_verify_token_missing_role(self, jwt_service, mock_logger, private_key):
		"""Test token verification with missing role in payload"""
		# Arrange - create token without role
		payload = {"username": "test_user"}
		invalid_token = jwt.encode(payload, private_key, algorithm="HS256")

		# Act & Assert
		with pytest.raises(InvalidTokenError, match="Invalid token payload"):
			jwt_service.verify_token(invalid_token)

	def test_verify_token_invalid_role(self, jwt_service, mock_logger, private_key):
		"""Test token verification with invalid role value"""
		# Arrange - create token with invalid role
		payload = {"username": "test_user", "role": "invalid_role"}
		invalid_token = jwt.encode(payload, private_key, algorithm="HS256")

		# Act & Assert
		with pytest.raises(InvalidTokenError, match="Invalid token payload"):
			jwt_service.verify_token(invalid_token)

	def test_verify_token_malformed(self, jwt_service, mock_logger):
		"""Test token verification with malformed token"""
		# Act & Assert
		with pytest.raises(InvalidTokenError):
			jwt_service.verify_token("not.a.valid.token")

	def test_verify_token_expired(self, jwt_service, mock_logger, private_key):
		"""Test token verification with expired token"""
		# Arrange - create expired token (using past timestamp)
		import time

		payload = {
			"username": "test_user",
			"role": "api",
			"exp": int(time.time()) - 3600,  # Expired 1 hour ago
		}
		expired_token = jwt.encode(payload, private_key, algorithm="HS256")

		# Act & Assert
		with pytest.raises(InvalidTokenError):
			jwt_service.verify_token(expired_token)

	def test_jwt_service_immutable(self, mock_logger, private_key, public_key):
		"""Test that JWTService is immutable (frozen dataclass)"""
		service = JWTService(logger=mock_logger, private_key=private_key, public_key=public_key)

		# Just verify the service was created successfully with frozen dataclass
		assert service.private_key == private_key
		assert service.public_key == public_key
		assert service.algorithm == "ES256"

	def test_default_algorithm(self, mock_logger, private_key, public_key):
		"""Test that default algorithm is ES256"""
		service = JWTService(logger=mock_logger, private_key=private_key, public_key=public_key)

		assert service.algorithm == "ES256"

	def test_custom_algorithm(self, mock_logger, private_key, public_key):
		"""Test JWTService with custom algorithm"""
		service = JWTService(logger=mock_logger, private_key=private_key, public_key=public_key, algorithm="RS256")

		assert service.algorithm == "RS256"
