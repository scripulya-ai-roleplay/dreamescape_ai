import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import HTTPException

from src.application.user.user_service import UserService
from src.application.auth.authz import AuthorizationService
from src.domain.models import User, UserRole
from src.application.ports.common import Page
from src.application.user.schemas import UserDTO


@pytest.mark.unit
class TestUserService:
	"""Unit tests for UserService"""

	@pytest.fixture
	def mock_user_gateway(self):
		"""Mock user gateway for testing"""
		return AsyncMock()

	@pytest.fixture
	def mock_uow(self):
		"""Mock Unit of Work for testing"""
		mock = AsyncMock()
		# Support async context manager protocol
		mock.__aenter__ = AsyncMock(return_value=mock)
		mock.__aexit__ = AsyncMock(return_value=None)
		return mock

	@pytest.fixture
	def user_service(self, mock_user_gateway, mock_uow):
		"""UserService instance with mocked dependencies"""
		return UserService(mock_user_gateway, mock_uow, authz=AuthorizationService())

	@pytest.fixture
	def sample_user(self):
		"""Sample user for testing"""
		return User(id=uuid4(), username="test_user", role=UserRole.API, crystal_balance=1000)

	@pytest.fixture
	def sample_user_dto(self):
		"""Sample UserDTO for filtering"""
		return UserDTO(usernames=["test_user"], roles=[UserRole.API])

	@pytest.mark.asyncio
	async def test_find_users_by_dto_success(self, user_service, mock_user_gateway, sample_user, sample_user_dto):
		"""Test successful user search with filters"""
		# Arrange
		expected_page = Page(items=[sample_user], count=1, offset=0, limit=10)
		mock_user_gateway.find_users_by_filters.return_value = expected_page

		# Act
		result = await user_service.find_users_by_dto(sample_user_dto)

		# Assert
		assert result == expected_page
		mock_user_gateway.find_users_by_filters.assert_called_once_with(sample_user_dto, 0, 10)

	@pytest.mark.asyncio
	async def test_find_users_by_dto_gateway_error(self, user_service, mock_user_gateway, sample_user_dto):
		"""Test user search when gateway raises error"""
		# Arrange
		mock_user_gateway.find_users_by_filters.side_effect = Exception("Database error")

		# Act & Assert
		with pytest.raises(Exception, match="Database error"):
			await user_service.find_users_by_dto(sample_user_dto)

		mock_user_gateway.find_users_by_filters.assert_called_once_with(sample_user_dto, 0, 10)

	@pytest.mark.asyncio
	async def test_create_user_success_with_username(self, user_service, mock_user_gateway, sample_user):
		"""Test successful user creation with username"""
		# Arrange
		user_without_id = User(username="new_user", role=UserRole.API, crystal_balance=1000)
		mock_user_gateway.find_users_by_filters.return_value = Page(items=[], count=0, offset=0, limit=1)
		mock_user_gateway.create_user.return_value = sample_user

		# Act
		result = await user_service.create_user(user_without_id)

		# Assert
		assert result == sample_user
		mock_user_gateway.create_user.assert_called_once_with(user_without_id)

	@pytest.mark.asyncio
	async def test_create_user_success_with_google_id(self, user_service, mock_user_gateway, sample_user):
		"""Test successful user creation with google_id"""
		# Arrange
		user_with_google_id = User(google_id="google123", role=UserRole.API, crystal_balance=1000)
		mock_user_gateway.find_users_by_filters.return_value = Page(items=[], count=0, offset=0, limit=1)
		mock_user_gateway.create_user.return_value = sample_user

		# Act
		result = await user_service.create_user(user_with_google_id)

		# Assert
		assert result == sample_user
		mock_user_gateway.find_users_by_filters.assert_called_once_with(
			UserDTO(google_ids=["google123"]), limit=1, offset=0
		)

	@pytest.mark.asyncio
	async def test_create_user_invalid_data(self, user_service, mock_user_gateway):
		"""Test user creation with invalid data (no username or google_id)"""
		# Arrange
		invalid_user = User(role=UserRole.API, crystal_balance=1000)

		# Act & Assert
		with pytest.raises(ValueError, match="User must have either google_id or username"):
			await user_service.create_user(invalid_user)

		mock_user_gateway.create_user.assert_not_called()

	@pytest.mark.asyncio
	async def test_create_user_duplicate_google_id(self, user_service, mock_user_gateway, sample_user):
		"""Test user creation with existing google_id"""
		# Arrange
		duplicate_user = User(google_id="google123", role=UserRole.API, crystal_balance=1000)
		mock_user_gateway.find_users_by_filters.return_value = Page(items=[sample_user], count=1, offset=0, limit=1)

		# Act & Assert
		with pytest.raises(ValueError, match="User with google_id google123 already exists"):
			await user_service.create_user(duplicate_user)

		mock_user_gateway.create_user.assert_not_called()

	@pytest.mark.asyncio
	async def test_create_user_gateway_error(self, user_service, mock_user_gateway):
		"""Test user creation when gateway raises error"""
		# Arrange
		user_with_username = User(username="test_user", role=UserRole.API, crystal_balance=1000)
		mock_user_gateway.find_users_by_filters.return_value = Page(items=[], count=0, offset=0, limit=1)
		mock_user_gateway.create_user.side_effect = Exception("Database error")

		# Act & Assert
		with pytest.raises(Exception, match="Database error"):
			await user_service.create_user(user_with_username)

	@pytest.mark.asyncio
	async def test_delete_user_success(self, user_service, mock_user_gateway, sample_user):
		"""Test successful user deletion by the account owner"""
		# Arrange
		user_id = sample_user.id
		mock_user_gateway.get_user_by_id.return_value = sample_user
		mock_user_gateway.delete_user.return_value = None

		# Act
		await user_service.delete_user(user_id, sample_user.id)

		# Assert
		mock_user_gateway.get_user_by_id.assert_called_once_with(user_id)
		mock_user_gateway.delete_user.assert_called_once_with(user_id)

	@pytest.mark.asyncio
	async def test_delete_user_not_found(self, user_service, mock_user_gateway):
		"""Test deletion of non-existent user"""
		# Arrange
		user_id = uuid4()
		mock_user_gateway.get_user_by_id.return_value = None

		# Act & Assert
		with pytest.raises(ValueError, match=f"User with ID {user_id} not found"):
			await user_service.delete_user(user_id, uuid4())

		mock_user_gateway.get_user_by_id.assert_called_once_with(user_id)
		mock_user_gateway.delete_user.assert_not_called()

	@pytest.mark.asyncio
	async def test_delete_user_forbidden_not_owner(self, user_service, mock_user_gateway, sample_user):
		"""A caller may not delete an account they do not own (403, no deletion)."""
		# Arrange
		mock_user_gateway.get_user_by_id.return_value = sample_user

		# Act & Assert
		with pytest.raises(HTTPException) as exc_info:
			await user_service.delete_user(sample_user.id, uuid4())

		assert exc_info.value.status_code == 403
		mock_user_gateway.delete_user.assert_not_called()

	@pytest.mark.asyncio
	async def test_delete_user_gateway_error(self, user_service, mock_user_gateway, sample_user):
		"""Test user deletion when gateway raises error"""
		# Arrange
		user_id = sample_user.id
		mock_user_gateway.get_user_by_id.return_value = sample_user
		mock_user_gateway.delete_user.side_effect = Exception("Database error")

		# Act & Assert
		with pytest.raises(Exception, match="Database error"):
			await user_service.delete_user(user_id, sample_user.id)

		mock_user_gateway.delete_user.assert_called_once_with(user_id)
