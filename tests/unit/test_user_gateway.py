import pytest
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.gateways.user_gateway import UserGateway
from src.domain.models import User, UserRole
from src.application.ports import Page
from src.application.user.schemas import UserDTO
from src.infrastructure.database.models import User as UserModel


@pytest.mark.unit
class TestUserGateway:
	"""Unit tests for UserGateway"""

	@pytest.fixture
	def mock_session(self):
		"""Mock AsyncSession for testing"""
		return AsyncMock(spec=AsyncSession)

	@pytest.fixture
	def user_gateway(self, mock_session):
		"""UserGateway instance with mocked dependencies"""
		return UserGateway(mock_session)

	@pytest.fixture
	def sample_user_model(self):
		"""Sample UserModel for testing"""
		user_model = Mock(spec=UserModel)
		user_model.id = uuid4()
		user_model.username = "test_user"
		user_model.google_id = "google123"
		user_model.role = UserRole.API
		user_model.crystal_balance = 1000
		user_model.characters = []
		user_model.scenes = []
		user_model.chats = []
		return user_model

	@pytest.fixture
	def sample_user_dto(self):
		"""Sample UserDTO for filtering"""
		return UserDTO(usernames=["test_user"], roles=[UserRole.API])

	@pytest.fixture
	def sample_domain_user(self):
		"""Sample domain User for testing"""
		return User(id=uuid4(), username="test_user", google_id="google123", role=UserRole.API, crystal_balance=1000)

	@pytest.mark.asyncio
	async def test_find_users_by_filters_success(self, user_gateway, mock_session, sample_user_model, sample_user_dto):
		"""Test successful user search with filters"""
		# Arrange
		mock_result = Mock()
		mock_result.scalars.return_value.all.return_value = [sample_user_model]
		mock_session.execute.return_value = mock_result

		# Mock count query
		mock_count_result = Mock()
		mock_count_result.scalar.return_value = 1
		mock_session.execute.side_effect = [mock_count_result, mock_result]

		# Act
		result = await user_gateway.find_users_by_filters(sample_user_dto, limit=10, offset=0)

		# Assert
		assert isinstance(result, Page)
		assert result.count == 1
		assert result.offset == 0
		assert result.limit == 10
		assert len(result.items) == 1
		assert result.items[0].username == "test_user"
		assert mock_session.execute.call_count == 2

	@pytest.mark.asyncio
	async def test_find_users_by_filters_with_id_filter(self, user_gateway, mock_session, sample_user_model):
		"""Test user search with ID filter"""
		# Arrange
		user_id = uuid4()
		filters = UserDTO(user_ids=[user_id])

		mock_result = Mock()
		mock_result.scalars.return_value.all.return_value = [sample_user_model]
		mock_session.execute.return_value = mock_result

		mock_count_result = Mock()
		mock_count_result.scalar.return_value = 1
		mock_session.execute.side_effect = [mock_count_result, mock_result]

		# Act
		result = await user_gateway.find_users_by_filters(filters)

		# Assert
		assert result.count == 1
		assert len(result.items) == 1

	@pytest.mark.asyncio
	async def test_find_users_by_filters_with_google_id_filter(self, user_gateway, mock_session, sample_user_model):
		"""Test user search with Google ID filter"""
		# Arrange
		filters = UserDTO(google_ids=["google123"])

		mock_result = Mock()
		mock_result.scalars.return_value.all.return_value = [sample_user_model]
		mock_session.execute.return_value = mock_result

		mock_count_result = Mock()
		mock_count_result.scalar.return_value = 1
		mock_session.execute.side_effect = [mock_count_result, mock_result]

		# Act
		result = await user_gateway.find_users_by_filters(filters)

		# Assert
		assert result.count == 1
		assert len(result.items) == 1

	@pytest.mark.asyncio
	async def test_find_users_by_filters_with_role_filter(self, user_gateway, mock_session, sample_user_model):
		"""The roles filter builds a real SQL predicate (it used to be a no-op `pass`)."""
		# Arrange
		filters = UserDTO(roles=[UserRole.ADMIN, UserRole.API])

		mock_result = Mock()
		mock_result.scalars.return_value.all.return_value = [sample_user_model]
		mock_count_result = Mock()
		mock_count_result.scalar.return_value = 1
		mock_session.execute.side_effect = [mock_count_result, mock_result]

		# Act
		await user_gateway.find_users_by_filters(filters)

		# Assert: the data query (2nd execute call) carries a role IN (...) predicate
		data_query = mock_session.execute.call_args_list[1].args[0]
		compiled = str(data_query.compile(compile_kwargs={"literal_binds": True}))
		assert "role" in compiled

	@pytest.mark.asyncio
	async def test_find_users_by_filters_no_results(self, user_gateway, mock_session, sample_user_dto):
		"""Test user search with no results"""
		# Arrange
		mock_result = Mock()
		mock_result.scalars.return_value.all.return_value = []
		mock_session.execute.return_value = mock_result

		mock_count_result = Mock()
		mock_count_result.scalar.return_value = 0
		mock_session.execute.side_effect = [mock_count_result, mock_result]

		# Act
		result = await user_gateway.find_users_by_filters(sample_user_dto)

		# Assert
		assert result.count == 0
		assert len(result.items) == 0

	@pytest.mark.asyncio
	async def test_find_users_by_filters_pagination(
		self, user_gateway, mock_session, sample_user_model, sample_user_dto
	):
		"""Test user search with pagination"""
		# Arrange
		mock_result = Mock()
		mock_result.scalars.return_value.all.return_value = [sample_user_model]
		mock_session.execute.return_value = mock_result

		mock_count_result = Mock()
		mock_count_result.scalar.return_value = 25
		mock_session.execute.side_effect = [mock_count_result, mock_result]

		# Act
		result = await user_gateway.find_users_by_filters(sample_user_dto, limit=5, offset=10)

		# Assert
		assert result.count == 25
		assert result.offset == 10
		assert result.limit == 5

	@pytest.mark.asyncio
	async def test_create_user_success(self, user_gateway, mock_session, sample_domain_user, sample_user_model):
		"""Test successful user creation"""
		# Arrange
		mock_session.refresh = AsyncMock()
		mock_session.refresh.side_effect = lambda model: setattr(model, "id", uuid4())

		# Act
		result = await user_gateway.create_user(sample_domain_user)

		# Assert
		assert isinstance(result, User)
		mock_session.add.assert_called_once()
		mock_session.flush.assert_called_once()
		mock_session.refresh.assert_called_once()

	@pytest.mark.asyncio
	async def test_create_user_minimal_data(self, user_gateway, mock_session):
		"""Test user creation with minimal required data"""
		# Arrange
		minimal_user = User(role=UserRole.API, crystal_balance=500)
		mock_session.refresh = AsyncMock()

		# Act
		result = await user_gateway.create_user(minimal_user)

		# Assert
		assert isinstance(result, User)
		mock_session.add.assert_called_once()
		mock_session.flush.assert_called_once()

	@pytest.mark.asyncio
	async def test_delete_user_success(self, user_gateway, mock_session):
		"""Test successful user deletion"""
		# Arrange
		user_id = uuid4()
		mock_result = Mock()
		mock_result.rowcount = 1
		mock_session.execute.return_value = mock_result

		# Act
		await user_gateway.delete_user(user_id)

		# Assert
		mock_session.execute.assert_called_once()
		# The gateway must not commit; the UOW owns the transaction boundary.
		mock_session.commit.assert_not_called()

	@pytest.mark.asyncio
	async def test_delete_user_not_found(self, user_gateway, mock_session):
		"""Test deletion of non-existent user"""
		# Arrange
		user_id = uuid4()
		mock_result = Mock()
		mock_result.rowcount = 0
		mock_session.execute.return_value = mock_result

		# Act & Assert
		with pytest.raises(ValueError, match=f"User with ID {user_id} not found"):
			await user_gateway.delete_user(user_id)

		mock_session.execute.assert_called_once()
		mock_session.commit.assert_not_called()

	@pytest.mark.asyncio
	async def test_get_user_by_id_success(self, user_gateway, mock_session, sample_user_model):
		"""Test successful user retrieval by ID"""
		# Arrange
		user_id = uuid4()
		mock_result = Mock()
		mock_result.scalar_one_or_none.return_value = sample_user_model
		mock_session.execute.return_value = mock_result

		# Act
		result = await user_gateway.get_user_by_id(user_id)

		# Assert
		assert isinstance(result, User)
		assert result.username == "test_user"
		mock_session.execute.assert_called_once()

	@pytest.mark.asyncio
	async def test_get_user_by_id_not_found(self, user_gateway, mock_session):
		"""Test user retrieval when user doesn't exist"""
		# Arrange
		user_id = uuid4()
		mock_result = Mock()
		mock_result.scalar_one_or_none.return_value = None
		mock_session.execute.return_value = mock_result

		# Act
		result = await user_gateway.get_user_by_id(user_id)

		# Assert
		assert result is None
		mock_session.execute.assert_called_once()

	def test_to_domain_user_conversion(self, user_gateway, sample_user_model):
		"""Test conversion from database model to domain model"""
		# Arrange - Create mock character, scene, and chat models
		char_model = Mock()
		char_model.id = uuid4()
		char_model.owner_id = sample_user_model.id
		char_model.name = "Test Character"
		char_model.system_prompt = "Test prompt"
		char_model.is_public = False

		scene_model = Mock()
		scene_model.id = uuid4()
		scene_model.owner_id = sample_user_model.id
		scene_model.title = "Test Scene"
		scene_model.background_prompt = "Test background"
		scene_model.initial_message_text = "initial message"

		chat_model = Mock()
		chat_model.id = uuid4()
		chat_model.name = "Test Chat"  # Database uses 'name' field
		chat_model.user_id = sample_user_model.id
		chat_model.scene_id = scene_model.id

		sample_user_model.characters = [char_model]
		sample_user_model.scenes = [scene_model]
		sample_user_model.chats = [chat_model]

		# Act
		result = user_gateway._to_domain_user(sample_user_model)

		# Assert
		assert isinstance(result, User)
		assert result.id == sample_user_model.id
		assert result.username == "test_user"
		assert result.google_id == "google123"
		assert result.role == UserRole.API
		assert result.crystal_balance == 1000
		assert len(result.characters) == 1
		assert len(result.scenes) == 1
		assert len(result.chats) == 1
		assert result.characters[0].name == "Test Character"
		assert result.scenes[0].title == "Test Scene"

	def test_to_domain_user_reads_role_from_model(self, user_gateway):
		"""The persisted role is read straight off the model row, not fabricated."""
		# Arrange
		user_model = Mock(spec=UserModel)
		user_model.id = uuid4()
		user_model.username = None
		user_model.google_id = None
		user_model.role = UserRole.ADMIN
		user_model.crystal_balance = 1000
		user_model.characters = []
		user_model.scenes = []
		user_model.chats = []

		# Act
		result = user_gateway._to_domain_user(user_model)

		# Assert
		assert result.role == UserRole.ADMIN

	def test_to_domain_user_empty_collections(self, user_gateway):
		"""Test conversion with empty character, scene, and chat collections"""
		# Arrange
		user_model = Mock(spec=UserModel)
		user_model.id = uuid4()
		user_model.username = None
		user_model.google_id = None
		user_model.role = UserRole.API
		user_model.crystal_balance = 1000
		user_model.characters = []
		user_model.scenes = []
		user_model.chats = []

		# Act
		result = user_gateway._to_domain_user(user_model)

		# Assert
		assert len(result.characters) == 0
		assert len(result.scenes) == 0
		assert len(result.chats) == 0
		assert result.role == UserRole.API

	@pytest.mark.asyncio
	async def test_find_users_empty_filters(self, user_gateway, mock_session, sample_user_model):
		"""Test user search with empty filters (should return all users)"""
		# Arrange
		empty_filters = UserDTO()

		mock_result = Mock()
		mock_result.scalars.return_value.all.return_value = [sample_user_model]
		mock_session.execute.return_value = mock_result

		mock_count_result = Mock()
		mock_count_result.scalar.return_value = 1
		mock_session.execute.side_effect = [mock_count_result, mock_result]

		# Act
		result = await user_gateway.find_users_by_filters(empty_filters)

		# Assert
		assert result.count == 1
		assert len(result.items) == 1

	@pytest.mark.asyncio
	async def test_session_error_handling(self, user_gateway, mock_session):
		"""Test that database errors are propagated correctly"""
		# Arrange
		mock_session.execute.side_effect = Exception("Database connection error")

		# Act & Assert
		with pytest.raises(Exception, match="Database connection error"):
			await user_gateway.find_users_by_filters(UserDTO())
