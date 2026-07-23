import pytest
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.gateways.scenes_gateway import SceneGateway
from src.infrastructure.gateways.visibility import VisibilityGateway
from src.domain.models import Scene
from src.application.ports.common import Page
from src.application.scene.schemas import SceneFilterDTO, SceneSortBy, SortOrder
from sqlalchemy.dialects import postgresql


@pytest.mark.unit
class TestSceneGateway:
	"""Unit tests for SceneGateway"""

	@pytest.fixture
	def mock_session(self):
		"""Mock AsyncSession for testing"""
		mock = AsyncMock(spec=AsyncSession)
		mock.add = Mock()
		mock.commit = AsyncMock()
		mock.execute = AsyncMock()
		mock.refresh = AsyncMock()
		return mock

	@pytest.fixture
	def scene_gateway(self, mock_session):
		"""SceneGateway instance with mocked session"""
		return SceneGateway(mock_session, visibility=VisibilityGateway())

	@pytest.fixture
	def sample_scene_model(self):
		"""Sample SceneModel for testing"""
		scene_model = Mock()
		scene_model.id = uuid4()
		scene_model.title = "Test Scene"
		scene_model.description = "Test scene description"
		scene_model.background_prompt = "Test background prompt"
		scene_model.owner_id = uuid4()
		scene_model.characters = []
		scene_model.initial_message_text = "Welcome to the test scene!"
		scene_model.is_public = True
		return scene_model

	@pytest.fixture
	def sample_scene_filter_dto(self):
		"""Sample SceneFilterDTO for filtering"""
		return SceneFilterDTO(ids=[uuid4()], title=["Test Scene"], owner=[uuid4()], characters=[uuid4()])

	@pytest.fixture
	def sample_domain_scene(self):
		"""Sample domain Scene for testing"""
		return Scene(
			id=uuid4(),
			title="Test Scene",
			description="Test scene description",
			background_prompt="Test background prompt",
			owner_id=uuid4(),
			initial_message_text="Welcome to the test scene!",
			is_public=True,
		)

	@pytest.mark.asyncio
	async def test_get_one_success(self, scene_gateway, mock_session, sample_scene_model):
		"""Test successful scene retrieval by ID"""
		# Arrange
		scene_id = uuid4()
		mock_result = Mock()
		mock_result.scalar_one.return_value = sample_scene_model
		mock_session.execute.return_value = mock_result

		# Act
		result = await scene_gateway.get_one(scene_id)

		# Assert
		assert isinstance(result, Scene)
		assert result.id == sample_scene_model.id
		assert result.title == sample_scene_model.title
		assert result.description == sample_scene_model.description
		assert result.is_public == sample_scene_model.is_public
		mock_session.execute.assert_called_once()

	@pytest.mark.asyncio
	async def test_get_one_not_found(self, scene_gateway, mock_session):
		"""Test scene retrieval when scene doesn't exist"""
		# Arrange
		scene_id = uuid4()
		mock_result = Mock()
		from sqlalchemy.exc import NoResultFound

		mock_result.scalar_one.side_effect = NoResultFound()
		mock_session.execute.return_value = mock_result

		# Act & Assert
		with pytest.raises(NoResultFound):
			await scene_gateway.get_one(scene_id)

	@pytest.mark.asyncio
	async def test_create_success(self, scene_gateway, mock_session, sample_domain_scene):
		"""Test successful scene creation"""
		# Arrange
		expected_id = uuid4()
		mock_session.refresh.side_effect = lambda model: setattr(model, "id", expected_id)

		# Act
		result = await scene_gateway.create(sample_domain_scene)

		# Assert
		assert result == expected_id
		mock_session.add.assert_called_once()
		mock_session.refresh.assert_called_once()

	@pytest.mark.asyncio
	async def test_delete_success(self, scene_gateway, mock_session):
		"""Test successful scene deletion"""
		# Arrange
		scene_id = uuid4()
		mock_result = Mock()
		mock_result.rowcount = 1
		mock_session.execute.return_value = mock_result

		# Act
		await scene_gateway.delete(scene_id)

		# Assert
		mock_session.execute.assert_called_once()

	@pytest.mark.asyncio
	async def test_delete_not_found(self, scene_gateway, mock_session):
		"""Test scene deletion when scene doesn't exist"""
		# Arrange
		scene_id = uuid4()
		mock_result = Mock()
		mock_result.rowcount = 0
		mock_session.execute.return_value = mock_result

		# Act (no exception expected - gateway doesn't validate)
		await scene_gateway.delete(scene_id)

		# Assert
		mock_session.execute.assert_called_once()

	@pytest.mark.asyncio
	async def test_update_success(self, scene_gateway, mock_session, sample_domain_scene):
		"""Test successful scene update"""
		# Arrange
		scene_id = uuid4()
		mock_result = Mock()
		mock_result.rowcount = 1
		mock_session.execute.return_value = mock_result

		# Act
		await scene_gateway.update(scene_id, sample_domain_scene)

		# Assert
		mock_session.execute.assert_called_once()

	@pytest.mark.asyncio
	async def test_update_not_found(self, scene_gateway, mock_session, sample_domain_scene):
		"""Test scene update when scene doesn't exist"""
		# Arrange
		scene_id = uuid4()
		mock_result = Mock()
		mock_result.rowcount = 0
		mock_session.execute.return_value = mock_result

		# Act (no exception expected - gateway doesn't validate)
		await scene_gateway.update(scene_id, sample_domain_scene)

		# Assert
		mock_session.execute.assert_called_once()

	@pytest.mark.asyncio
	async def test_search_success(self, scene_gateway, mock_session, sample_scene_model, sample_scene_filter_dto):
		"""Test successful scene search with filters"""
		# Arrange
		mock_result = Mock()
		mock_result.all.return_value = [(sample_scene_model, 1, 1)]
		mock_session.execute.return_value = mock_result

		# Mock count query
		mock_count_result = Mock()
		mock_count_result.scalar.return_value = 1
		mock_session.execute.side_effect = [mock_count_result, mock_result]

		# Act
		result = await scene_gateway.search(sample_scene_filter_dto)

		# Assert
		assert isinstance(result, Page)
		assert result.count == 1
		assert result.offset == 0
		assert len(result.items) == 1
		assert result.items[0].title == sample_scene_model.title
		assert result.items[0].chats_count == 1
		assert result.items[0].messages_count == 1
		assert mock_session.execute.call_count == 2

	@pytest.mark.asyncio
	async def test_search_with_id_filter(self, scene_gateway, mock_session, sample_scene_model):
		"""Test scene search with ID filter"""
		# Arrange
		scene_id = uuid4()
		filters = SceneFilterDTO(ids=[scene_id], title=[], owner=[], characters=[])

		mock_result = Mock()
		mock_result.all.return_value = [(sample_scene_model, 1, 1)]
		mock_session.execute.return_value = mock_result

		mock_count_result = Mock()
		mock_count_result.scalar.return_value = 1
		mock_session.execute.side_effect = [mock_count_result, mock_result]

		# Act
		result = await scene_gateway.search(filters)

		# Assert
		assert result.count == 1
		assert len(result.items) == 1

	@pytest.mark.asyncio
	async def test_search_with_title_filter(self, scene_gateway, mock_session, sample_scene_model):
		"""Test scene search with title filter"""
		# Arrange
		filters = SceneFilterDTO(ids=[], title=["Test Scene"], owner=[], characters=[])

		mock_result = Mock()
		mock_result.all.return_value = [(sample_scene_model, 1, 1)]
		mock_session.execute.return_value = mock_result

		mock_count_result = Mock()
		mock_count_result.scalar.return_value = 1
		mock_session.execute.side_effect = [mock_count_result, mock_result]

		# Act
		result = await scene_gateway.search(filters)

		# Assert
		assert result.count == 1
		assert len(result.items) == 1

	@pytest.mark.asyncio
	async def test_search_with_owner_filter(self, scene_gateway, mock_session, sample_scene_model):
		"""Test scene search with owner filter"""
		# Arrange
		owner_id = uuid4()
		filters = SceneFilterDTO(ids=[], title=[], owner=[owner_id], characters=[])

		mock_result = Mock()
		mock_result.all.return_value = [(sample_scene_model, 1, 1)]
		mock_session.execute.return_value = mock_result

		mock_count_result = Mock()
		mock_count_result.scalar.return_value = 1
		mock_session.execute.side_effect = [mock_count_result, mock_result]

		# Act
		result = await scene_gateway.search(filters)

		# Assert
		assert result.count == 1
		assert len(result.items) == 1

	@pytest.mark.asyncio
	async def test_search_with_character_filter(self, scene_gateway, mock_session, sample_scene_model):
		"""Test scene search with character filter"""
		# Arrange
		character_id = uuid4()
		filters = SceneFilterDTO(ids=[], title=[], owner=[], characters=[character_id])

		mock_result = Mock()
		mock_result.all.return_value = [(sample_scene_model, 1, 1)]
		mock_session.execute.return_value = mock_result

		mock_count_result = Mock()
		mock_count_result.scalar.return_value = 1
		mock_session.execute.side_effect = [mock_count_result, mock_result]

		# Act
		result = await scene_gateway.search(filters)

		# Assert
		assert result.count == 1
		assert len(result.items) == 1

	@pytest.mark.asyncio
	async def test_search_no_results(self, scene_gateway, mock_session, sample_scene_filter_dto):
		"""Test scene search with no results"""
		# Arrange
		mock_result = Mock()
		mock_result.all.return_value = []
		mock_session.execute.return_value = mock_result

		mock_count_result = Mock()
		mock_count_result.scalar.return_value = 0
		mock_session.execute.side_effect = [mock_count_result, mock_result]

		# Act
		result = await scene_gateway.search(sample_scene_filter_dto)

		# Assert
		assert result.count == 0
		assert len(result.items) == 0

	@pytest.mark.asyncio
	async def test_search_empty_filters(self, scene_gateway, mock_session, sample_scene_model):
		"""Test scene search with empty filters"""
		# Arrange
		filters = SceneFilterDTO(ids=[], title=[], owner=[], characters=[])

		mock_result = Mock()
		mock_result.all.return_value = [(sample_scene_model, 1, 1)]
		mock_session.execute.return_value = mock_result

		mock_count_result = Mock()
		mock_count_result.scalar.return_value = 1
		mock_session.execute.side_effect = [mock_count_result, mock_result]

		# Act
		result = await scene_gateway.search(filters)

		# Assert
		assert result.count == 1
		assert len(result.items) == 1

	def _compile_main_query(self, mock_session) -> str:
		"""Compile the main (non-count) SELECT issued by search() to SQL text.

		search() executes the count query first, then the row query, so the last
		execute call holds the statement we want to inspect.
		"""
		main_stmt = mock_session.execute.call_args_list[-1].args[0]
		return str(main_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))

	@pytest.mark.asyncio
	async def test_search_title_search_builds_ilike(self, scene_gateway, mock_session, sample_scene_model):
		"""title_search compiles to a case-insensitive ILIKE substring filter."""
		# Arrange
		filters = SceneFilterDTO(title_search="dragon")

		mock_result = Mock()
		mock_result.all.return_value = [(sample_scene_model, 1, 1)]
		mock_count_result = Mock()
		mock_count_result.scalar.return_value = 1
		mock_session.execute.side_effect = [mock_count_result, mock_result]

		# Act
		await scene_gateway.search(filters)

		# Assert
		compiled = self._compile_main_query(mock_session)
		assert "ILIKE" in compiled
		assert "%dragon%" in compiled

	@pytest.mark.asyncio
	async def test_search_sort_by_messages_count_desc(self, scene_gateway, mock_session, sample_scene_model):
		"""sort_by=messages_count orders by a correlated count(messages) subquery, desc."""
		# Arrange
		filters = SceneFilterDTO(sort_by=SceneSortBy.messages_count, sort_order=SortOrder.desc)

		mock_result = Mock()
		mock_result.all.return_value = [(sample_scene_model, 1, 1)]
		mock_count_result = Mock()
		mock_count_result.scalar.return_value = 1
		mock_session.execute.side_effect = [mock_count_result, mock_result]

		# Act
		await scene_gateway.search(filters)

		# Assert
		compiled = self._compile_main_query(mock_session)
		assert "ORDER BY" in compiled
		assert "DESC" in compiled
		assert "count(" in compiled.lower()
		assert "messages" in compiled

	@pytest.mark.asyncio
	async def test_search_sort_by_chats_count_asc(self, scene_gateway, mock_session, sample_scene_model):
		"""sort_by=chats_count orders by a correlated count(chats) subquery, asc."""
		# Arrange
		filters = SceneFilterDTO(sort_by=SceneSortBy.chats_count, sort_order=SortOrder.asc)

		mock_result = Mock()
		mock_result.all.return_value = [(sample_scene_model, 1, 1)]
		mock_count_result = Mock()
		mock_count_result.scalar.return_value = 1
		mock_session.execute.side_effect = [mock_count_result, mock_result]

		# Act
		await scene_gateway.search(filters)

		# Assert
		compiled = self._compile_main_query(mock_session)
		assert "ORDER BY" in compiled
		assert "ASC" in compiled
		assert "chats" in compiled

	@pytest.mark.asyncio
	async def test_search_sort_adds_id_tiebreaker(self, scene_gateway, mock_session, sample_scene_model):
		"""A sort emits scene.id as a deterministic secondary key so tied rows
		(common for count sorts where many scenes share a value, often 0) stay in a
		stable order across offset/limit pages."""
		# Arrange
		filters = SceneFilterDTO(sort_by=SceneSortBy.chats_count, sort_order=SortOrder.desc)

		mock_result = Mock()
		mock_result.all.return_value = [(sample_scene_model, 1, 1)]
		mock_count_result = Mock()
		mock_count_result.scalar.return_value = 1
		mock_session.execute.side_effect = [mock_count_result, mock_result]

		# Act
		await scene_gateway.search(filters)

		# Assert
		compiled = self._compile_main_query(mock_session)
		assert "ORDER BY" in compiled
		order_by_clause = compiled[compiled.index("ORDER BY") :]
		assert "scenes.id" in order_by_clause
		assert order_by_clause.index("scenes.id") > order_by_clause.index("count(")

	@pytest.mark.asyncio
	async def test_search_without_sort_has_no_order_by(self, scene_gateway, mock_session, sample_scene_model):
		"""No sort_by means no ORDER BY is emitted (rows in DB order)."""
		# Arrange
		filters = SceneFilterDTO()

		mock_result = Mock()
		mock_result.all.return_value = [(sample_scene_model, 1, 1)]
		mock_count_result = Mock()
		mock_count_result.scalar.return_value = 1
		mock_session.execute.side_effect = [mock_count_result, mock_result]

		# Act
		await scene_gateway.search(filters)

		# Assert
		compiled = self._compile_main_query(mock_session)
		assert "ORDER BY" not in compiled

	def test_to_domain_scene_conversion(self, scene_gateway, sample_scene_model):
		"""Test conversion from SceneModel to domain Scene"""
		# Act
		result = scene_gateway._to_domain_scene(sample_scene_model)

		# Assert
		assert isinstance(result, Scene)
		assert result.id == sample_scene_model.id
		assert result.title == sample_scene_model.title
		assert result.description == sample_scene_model.description
		assert result.background_prompt == sample_scene_model.background_prompt
		assert result.owner_id == sample_scene_model.owner_id
		assert result.is_public == sample_scene_model.is_public

	@pytest.mark.asyncio
	async def test_session_error_handling(self, scene_gateway, mock_session):
		"""Test error handling when session raises exception"""
		# Arrange
		scene_id = uuid4()
		mock_session.execute.side_effect = Exception("Database connection error")

		# Act & Assert
		with pytest.raises(Exception, match="Database connection error"):
			await scene_gateway.get_one(scene_id)

	@pytest.mark.asyncio
	async def test_set_like_executes_insert(self, scene_gateway, mock_session):
		await scene_gateway.set_like(uuid4(), uuid4())
		mock_session.execute.assert_awaited_once()

	@pytest.mark.asyncio
	async def test_unset_like_executes_delete(self, scene_gateway, mock_session):
		await scene_gateway.unset_like(uuid4(), uuid4())
		mock_session.execute.assert_awaited_once()

	@pytest.mark.asyncio
	async def test_is_liked_true(self, scene_gateway, mock_session):
		mock_session.scalar.return_value = True
		assert await scene_gateway.is_liked(uuid4(), uuid4()) is True
		mock_session.scalar.assert_awaited_once()

	@pytest.mark.asyncio
	async def test_is_liked_false(self, scene_gateway, mock_session):
		mock_session.scalar.return_value = False
		assert await scene_gateway.is_liked(uuid4(), uuid4()) is False

	@pytest.mark.asyncio
	async def test_count_likes_returns_int(self, scene_gateway, mock_session):
		mock_session.scalar.return_value = 3
		assert await scene_gateway.count_likes(uuid4()) == 3

	@pytest.mark.asyncio
	async def test_count_likes_coerces_none_to_zero(self, scene_gateway, mock_session):
		mock_session.scalar.return_value = None
		assert await scene_gateway.count_likes(uuid4()) == 0

	@pytest.mark.asyncio
	async def test_set_bookmark_executes_insert(self, scene_gateway, mock_session):
		await scene_gateway.set_bookmark(uuid4(), uuid4())
		mock_session.execute.assert_awaited_once()

	@pytest.mark.asyncio
	async def test_unset_bookmark_executes_delete(self, scene_gateway, mock_session):
		await scene_gateway.unset_bookmark(uuid4(), uuid4())
		mock_session.execute.assert_awaited_once()

	@pytest.mark.asyncio
	async def test_is_bookmarked_false(self, scene_gateway, mock_session):
		mock_session.scalar.return_value = False
		assert await scene_gateway.is_bookmarked(uuid4(), uuid4()) is False

	@pytest.mark.asyncio
	async def test_attach_characters_inserts_on_conflict_do_nothing(self, scene_gateway, mock_session):
		# Idempotent bulk insert into character_scene; re-adding a character is a no-op.
		scene_id, char_id = uuid4(), uuid4()
		await scene_gateway.attach_characters(scene_id, [char_id])

		stmt = mock_session.execute.call_args_list[-1].args[0]
		compiled = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
		assert "INSERT INTO character_scene" in compiled
		assert "ON CONFLICT DO NOTHING" in compiled
		assert str(char_id) in compiled
