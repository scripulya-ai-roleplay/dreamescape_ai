import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from src.application.character.service import CharacterService
from src.domain.models import Character
from src.application.ports import Page
from src.application.character.schemas import CharacterFilterDTO


@pytest.mark.unit
class TestCharacterService:
	@pytest.fixture
	def mock_character_gateway(self):
		mock = AsyncMock()
		return mock

	@pytest.fixture
	def mock_uow(self):
		mock = AsyncMock()
		mock.__aenter__ = AsyncMock(return_value=mock)
		mock.__aexit__ = AsyncMock(return_value=None)
		return mock

	@pytest.fixture
	def character_service(self, mock_character_gateway, mock_uow):
		return CharacterService(gateway=mock_character_gateway, uow=mock_uow)

	@pytest.fixture
	def sample_character(self):
		return Character(
			id=uuid4(),
			name="Test Character",
			system_prompt="You are a test character",
			is_public=True,
			owner_id=uuid4(),
		)

	@pytest.fixture
	def sample_character_filter_dto(self):
		return CharacterFilterDTO(ids=[uuid4()], names=["Test Character"], owner_ids=[uuid4()])

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_create_character_success(self, character_service, mock_character_gateway, sample_character):
		# Arrange
		character_id = uuid4()
		mock_character_gateway.create.return_value = character_id

		# Act
		result = await character_service.create_character(sample_character)

		# Assert
		assert result == character_id
		mock_character_gateway.create.assert_called_once_with(sample_character)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_create_character_gateway_error(self, character_service, mock_character_gateway, sample_character):
		# Arrange
		mock_character_gateway.create.side_effect = Exception("Gateway error")

		# Act & Assert
		with pytest.raises(Exception, match="Gateway error"):
			await character_service.create_character(sample_character)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_get_one_success(self, character_service, mock_character_gateway, sample_character):
		# Arrange
		character_uuid = uuid4()
		mock_character_gateway.get_one.return_value = sample_character

		# Act
		result = await character_service.get_one(character_uuid)

		# Assert
		assert result == sample_character
		mock_character_gateway.get_one.assert_called_once_with(character_uuid)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_get_one_gateway_error(self, character_service, mock_character_gateway):
		# Arrange
		character_uuid = uuid4()
		mock_character_gateway.get_one.side_effect = Exception("Character not found")

		# Act & Assert
		with pytest.raises(Exception, match="Character not found"):
			await character_service.get_one(character_uuid)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_search_success(
		self, character_service, mock_character_gateway, sample_character, sample_character_filter_dto
	):
		# Arrange
		page_result = Page[Character](items=[sample_character], count=1, offset=0, limit=1)
		mock_character_gateway.search.return_value = page_result

		# Act
		result = await character_service.search(sample_character_filter_dto)

		# Assert
		assert result == page_result
		mock_character_gateway.search.assert_called_once_with(sample_character_filter_dto)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_search_gateway_error(self, character_service, mock_character_gateway, sample_character_filter_dto):
		# Arrange
		mock_character_gateway.search.side_effect = Exception("Search error")

		# Act & Assert
		with pytest.raises(Exception, match="Search error"):
			await character_service.search(sample_character_filter_dto)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_delete_success(self, character_service, mock_character_gateway, sample_character):
		# Arrange
		character_uuid = uuid4()
		mock_character_gateway.get_one.return_value = sample_character

		# Act
		await character_service.delete(character_uuid)

		# Assert
		mock_character_gateway.get_one.assert_called_once_with(character_uuid)
		mock_character_gateway.delete.assert_called_once_with(character_uuid)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_delete_not_found(self, character_service, mock_character_gateway):
		# Arrange
		character_uuid = uuid4()
		mock_character_gateway.get_one.side_effect = ValueError("Character not found")

		# Act & Assert
		with pytest.raises(ValueError, match="Character not found"):
			await character_service.delete(character_uuid)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_delete_gateway_error(self, character_service, mock_character_gateway, sample_character):
		# Arrange
		character_uuid = uuid4()
		mock_character_gateway.get_one.return_value = sample_character
		mock_character_gateway.delete.side_effect = Exception("Delete error")

		# Act & Assert
		with pytest.raises(Exception, match="Delete error"):
			await character_service.delete(character_uuid)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_update_success(self, character_service, mock_character_gateway, sample_character):
		# Arrange
		character_uuid = uuid4()
		mock_character_gateway.get_one.return_value = sample_character

		# Act
		await character_service.update(character_uuid, sample_character)

		# Assert
		mock_character_gateway.get_one.assert_called_once_with(character_uuid)
		mock_character_gateway.update.assert_called_once_with(character_uuid, sample_character)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_update_not_found(self, character_service, mock_character_gateway, sample_character):
		# Arrange
		character_uuid = uuid4()
		mock_character_gateway.get_one.side_effect = ValueError("Character not found")

		# Act & Assert
		with pytest.raises(ValueError, match="Character not found"):
			await character_service.update(character_uuid, sample_character)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_update_gateway_error(self, character_service, mock_character_gateway, sample_character):
		# Arrange
		character_uuid = uuid4()
		mock_character_gateway.get_one.return_value = sample_character
		mock_character_gateway.update.side_effect = Exception("Update error")

		# Act & Assert
		with pytest.raises(Exception, match="Update error"):
			await character_service.update(character_uuid, sample_character)
