import pytest
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects import postgresql

from src.infrastructure.gateways.character_gateway import CharacterGateway
from src.domain.models import Character
from src.application.ports import Page
from src.application.character.schemas import CharacterFilterDTO


@pytest.mark.unit
class TestCharacterGateway:
	@pytest.fixture
	def mock_session(self):
		mock = AsyncMock(spec=AsyncSession)
		mock.execute = AsyncMock()
		mock.add = Mock()
		mock.flush = AsyncMock()
		mock.refresh = AsyncMock()
		return mock

	@pytest.fixture
	def character_gateway(self, mock_session):
		return CharacterGateway(session=mock_session)

	@pytest.fixture
	def sample_character_model(self):
		mock_model = Mock()
		mock_model.id = uuid4()
		mock_model.name = "Test Character"
		mock_model.system_prompt = "You are a test character"
		mock_model.is_public = True
		mock_model.owner_id = uuid4()
		mock_model.scenes = []
		return mock_model

	@pytest.fixture
	def sample_character_filter_dto(self):
		return CharacterFilterDTO(ids=[uuid4()], names=["Test Character"], owner_ids=[uuid4()])

	@pytest.fixture
	def sample_domain_character(self):
		return Character(
			id=uuid4(),
			name="Test Character",
			system_prompt="You are a test character",
			is_public=True,
			owner_id=uuid4(),
		)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_get_one_success(self, character_gateway, mock_session, sample_character_model):
		# Arrange
		character_uuid = uuid4()
		mock_result = Mock()
		mock_result.scalar_one.return_value = sample_character_model
		mock_session.execute.return_value = mock_result

		# Act
		result = await character_gateway.get_one(character_uuid)

		# Assert
		assert result.id == sample_character_model.id
		assert result.name == sample_character_model.name
		assert result.system_prompt == sample_character_model.system_prompt
		assert result.is_public == sample_character_model.is_public
		assert result.owner_id == sample_character_model.owner_id

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_get_one_not_found(self, character_gateway, mock_session):
		# Arrange
		character_uuid = uuid4()
		mock_result = Mock()
		mock_result.scalar_one.side_effect = Exception("Character not found")
		mock_session.execute.return_value = mock_result

		# Act & Assert
		with pytest.raises(Exception, match="Character not found"):
			await character_gateway.get_one(character_uuid)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_get_for_scene_returns_characters(self, character_gateway, mock_session, sample_character_model):
		# Arrange
		scene_id = uuid4()
		mock_result = Mock()
		mock_scalars = Mock()
		mock_scalars.all.return_value = [sample_character_model]
		mock_result.scalars.return_value = mock_scalars
		mock_session.execute.return_value = mock_result

		# Act
		result = await character_gateway.get_for_scene(scene_id)

		# Assert
		assert isinstance(result, list)
		assert len(result) == 1
		assert result[0].name == sample_character_model.name
		assert result[0].system_prompt == sample_character_model.system_prompt

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_create_success(self, character_gateway, mock_session, sample_domain_character):
		# Arrange
		character_id = uuid4()
		mock_model = Mock()
		mock_model.id = character_id

		# Act
		mock_session.add.return_value = None
		mock_session.flush.return_value = None
		mock_session.refresh.return_value = None

		# it tests the general flow
		await character_gateway.create(sample_domain_character)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_delete_success(self, character_gateway, mock_session):
		# Arrange
		character_uuid = uuid4()
		mock_session.execute.return_value = None

		# Act
		await character_gateway.delete(character_uuid)

		# Assert
		mock_session.execute.assert_called_once()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_delete_not_found(self, character_gateway, mock_session):
		# Arrange
		character_uuid = uuid4()
		mock_session.execute.side_effect = Exception("Delete failed")

		# Act & Assert
		with pytest.raises(Exception, match="Delete failed"):
			await character_gateway.delete(character_uuid)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_update_success(self, character_gateway, mock_session, sample_domain_character):
		# Arrange
		character_uuid = uuid4()
		mock_session.execute.return_value = None

		# Act
		await character_gateway.update(character_uuid, sample_domain_character)

		# Assert
		mock_session.execute.assert_called_once()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_update_not_found(self, character_gateway, mock_session, sample_domain_character):
		# Arrange
		character_uuid = uuid4()
		mock_session.execute.side_effect = Exception("Update failed")

		# Act & Assert
		with pytest.raises(Exception, match="Update failed"):
			await character_gateway.update(character_uuid, sample_domain_character)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_search_success(
		self, character_gateway, mock_session, sample_character_model, sample_character_filter_dto
	):
		# Arrange
		mock_count_result = Mock()
		mock_count_result.scalar.return_value = 1
		mock_result = Mock()
		mock_scalars = Mock()
		mock_scalars.all.return_value = [sample_character_model]
		mock_result.scalars.return_value = mock_scalars

		mock_session.execute.side_effect = [mock_count_result, mock_result]

		# Act
		result = await character_gateway.search(sample_character_filter_dto)

		# Assert
		assert isinstance(result, Page)
		assert result.count == 1
		assert len(result.items) == 1
		assert result.items[0].name == sample_character_model.name

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_search_with_id_filter(self, character_gateway, mock_session, sample_character_model):
		# Arrange
		character_id = uuid4()
		filter_dto = CharacterFilterDTO(ids=[character_id])

		mock_count_result = Mock()
		mock_count_result.scalar.return_value = 1
		mock_result = Mock()
		mock_scalars = Mock()
		mock_scalars.all.return_value = [sample_character_model]
		mock_result.scalars.return_value = mock_scalars

		mock_session.execute.side_effect = [mock_count_result, mock_result]

		# Act
		result = await character_gateway.search(filter_dto)

		# Assert
		assert isinstance(result, Page)
		assert result.count == 1

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_search_with_name_filter(self, character_gateway, mock_session, sample_character_model):
		# Arrange
		filter_dto = CharacterFilterDTO(names=["Test Character"])

		mock_count_result = Mock()
		mock_count_result.scalar.return_value = 1
		mock_result = Mock()
		mock_scalars = Mock()
		mock_scalars.all.return_value = [sample_character_model]
		mock_result.scalars.return_value = mock_scalars

		mock_session.execute.side_effect = [mock_count_result, mock_result]

		# Act
		result = await character_gateway.search(filter_dto)

		# Assert
		assert isinstance(result, Page)
		assert result.count == 1

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_search_with_owner_filter(self, character_gateway, mock_session, sample_character_model):
		# Arrange
		owner_id = uuid4()
		filter_dto = CharacterFilterDTO(owner_ids=[owner_id])

		mock_count_result = Mock()
		mock_count_result.scalar.return_value = 1
		mock_result = Mock()
		mock_scalars = Mock()
		mock_scalars.all.return_value = [sample_character_model]
		mock_result.scalars.return_value = mock_scalars

		mock_session.execute.side_effect = [mock_count_result, mock_result]

		# Act
		result = await character_gateway.search(filter_dto)

		# Assert
		assert isinstance(result, Page)
		assert result.count == 1

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_search_bookmarked_by_uses_exists_not_join(
		self, character_gateway, mock_session, sample_character_model
	):
		# Regression: bookmarked_by filters via a correlated EXISTS, never a JOIN.
		# A JOIN produces one row per bookmarking user and duplicates the character.
		u1, u2 = uuid4(), uuid4()
		filter_dto = CharacterFilterDTO(bookmarked_by=[u1, u2])

		mock_count_result = Mock()
		mock_count_result.scalar.return_value = 1
		mock_result = Mock()
		mock_scalars = Mock()
		mock_scalars.all.return_value = [sample_character_model]
		mock_result.scalars.return_value = mock_scalars
		mock_session.execute.side_effect = [mock_count_result, mock_result]

		await character_gateway.search(filter_dto)

		compiled = self._compile_main_query(mock_session)
		assert "EXISTS" in compiled
		assert "JOIN" not in compiled
		assert str(u1) in compiled
		assert str(u2) in compiled

	def _compile_main_query(self, mock_session) -> str:
		main_stmt = mock_session.execute.call_args_list[-1].args[0]
		return str(main_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_search_no_results(self, character_gateway, mock_session, sample_character_filter_dto):
		# Arrange
		mock_count_result = Mock()
		mock_count_result.scalar.return_value = 0
		mock_result = Mock()
		mock_scalars = Mock()
		mock_scalars.all.return_value = []
		mock_result.scalars.return_value = mock_scalars

		mock_session.execute.side_effect = [mock_count_result, mock_result]

		# Act
		result = await character_gateway.search(sample_character_filter_dto)

		# Assert
		assert isinstance(result, Page)
		assert result.count == 0
		assert len(result.items) == 0

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_search_empty_filters(self, character_gateway, mock_session, sample_character_model):
		# Arrange
		filter_dto = CharacterFilterDTO()

		mock_count_result = Mock()
		mock_count_result.scalar.return_value = 1
		mock_result = Mock()
		mock_scalars = Mock()
		mock_scalars.all.return_value = [sample_character_model]
		mock_result.scalars.return_value = mock_scalars

		mock_session.execute.side_effect = [mock_count_result, mock_result]

		# Act
		result = await character_gateway.search(filter_dto)

		# Assert
		assert isinstance(result, Page)
		assert result.count == 1

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_to_domain_character_conversion(self, character_gateway, sample_character_model):
		# Act
		result = character_gateway._to_domain_character(sample_character_model)

		# Assert
		assert result.id == sample_character_model.id
		assert result.name == sample_character_model.name
		assert result.system_prompt == sample_character_model.system_prompt
		assert result.is_public == sample_character_model.is_public
		assert result.owner_id == sample_character_model.owner_id

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_session_error_handling(self, character_gateway, mock_session):
		# Arrange
		character_uuid = uuid4()
		mock_session.execute.side_effect = Exception("Database error")

		# Act & Assert
		with pytest.raises(Exception, match="Database error"):
			await character_gateway.get_one(character_uuid)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_set_like_executes_insert(self, character_gateway, mock_session):
		await character_gateway.set_like(uuid4(), uuid4())
		mock_session.execute.assert_awaited_once()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_unset_like_executes_delete(self, character_gateway, mock_session):
		await character_gateway.unset_like(uuid4(), uuid4())
		mock_session.execute.assert_awaited_once()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_is_liked_true(self, character_gateway, mock_session):
		mock_session.scalar.return_value = True
		assert await character_gateway.is_liked(uuid4(), uuid4()) is True
		mock_session.scalar.assert_awaited_once()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_is_liked_false(self, character_gateway, mock_session):
		mock_session.scalar.return_value = False
		assert await character_gateway.is_liked(uuid4(), uuid4()) is False

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_count_likes_returns_int(self, character_gateway, mock_session):
		mock_session.scalar.return_value = 3
		assert await character_gateway.count_likes(uuid4()) == 3

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_count_likes_coerces_none_to_zero(self, character_gateway, mock_session):
		mock_session.scalar.return_value = None
		assert await character_gateway.count_likes(uuid4()) == 0

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_set_bookmark_executes_insert(self, character_gateway, mock_session):
		await character_gateway.set_bookmark(uuid4(), uuid4())
		mock_session.execute.assert_awaited_once()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_unset_bookmark_executes_delete(self, character_gateway, mock_session):
		await character_gateway.unset_bookmark(uuid4(), uuid4())
		mock_session.execute.assert_awaited_once()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_is_bookmarked_false(self, character_gateway, mock_session):
		mock_session.scalar.return_value = False
		assert await character_gateway.is_bookmarked(uuid4(), uuid4()) is False
