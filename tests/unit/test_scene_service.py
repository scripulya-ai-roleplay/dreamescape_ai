import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from sqlalchemy.exc import NoResultFound

from src.application.scene.service import SceneService
from src.domain.models import Scene
from src.application.ports import Page, LikeState, BookmarkState
from src.application.scene.schemas import SceneFilterDTO


@pytest.mark.unit
class TestSceneService:
	"""Unit tests for SceneService"""

	@pytest.fixture
	def mock_scene_gateway(self):
		"""Mock scene gateway for testing"""
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
	def scene_service(self, mock_scene_gateway, mock_uow):
		"""SceneService instance with mocked dependencies"""
		return SceneService(mock_uow, mock_scene_gateway)

	@pytest.fixture
	def sample_scene(self):
		"""Sample scene for testing"""
		return Scene(
			id=uuid4(),
			title="Test Scene",
			description="Test scene description",
			background_prompt="Test background prompt",
			owner_id=uuid4(),
			initial_message_text="Welcome to the test scene!",
		)

	@pytest.fixture
	def sample_scene_filter_dto(self):
		"""Sample SceneFilterDTO for filtering"""
		return SceneFilterDTO(ids=[uuid4()], title=["Test Scene"], owner=[uuid4()], characters=[uuid4()])

	@pytest.mark.asyncio
	async def test_create_scene_success(self, scene_service, mock_scene_gateway, sample_scene):
		"""Test successful scene creation"""
		# Arrange
		expected_id = uuid4()
		mock_scene_gateway.create.return_value = expected_id

		# Act
		result = await scene_service.create_scene(sample_scene)

		# Assert
		assert result == expected_id
		mock_scene_gateway.create.assert_called_once_with(sample_scene)

	@pytest.mark.asyncio
	async def test_create_scene_gateway_error(self, scene_service, mock_scene_gateway, sample_scene):
		"""Test scene creation when gateway raises error"""
		# Arrange
		mock_scene_gateway.create.side_effect = Exception("Database error")

		# Act & Assert
		with pytest.raises(Exception, match="Database error"):
			await scene_service.create_scene(sample_scene)

		mock_scene_gateway.create.assert_called_once_with(sample_scene)

	@pytest.mark.asyncio
	async def test_get_one_success(self, scene_service, mock_scene_gateway, sample_scene):
		"""Test successful scene retrieval"""
		# Arrange
		scene_id = uuid4()
		mock_scene_gateway.get_one.return_value = sample_scene

		# Act
		result = await scene_service.get_one(scene_id)

		# Assert
		assert result == sample_scene
		mock_scene_gateway.get_one.assert_called_once_with(scene_id)

	@pytest.mark.asyncio
	async def test_get_one_gateway_error(self, scene_service, mock_scene_gateway):
		"""Test scene retrieval when gateway raises error"""
		# Arrange
		scene_id = uuid4()
		mock_scene_gateway.get_one.side_effect = Exception("Database error")

		# Act & Assert
		with pytest.raises(Exception, match="Database error"):
			await scene_service.get_one(scene_id)

		mock_scene_gateway.get_one.assert_called_once_with(scene_id)

	@pytest.mark.asyncio
	async def test_search_success(self, scene_service, mock_scene_gateway, sample_scene, sample_scene_filter_dto):
		"""Test successful scene search"""
		# Arrange
		expected_page = Page(items=[sample_scene], count=1, offset=0, limit=1)
		mock_scene_gateway.search.return_value = expected_page

		# Act
		result = await scene_service.search(sample_scene_filter_dto)

		# Assert
		assert result == expected_page
		mock_scene_gateway.search.assert_called_once_with(sample_scene_filter_dto)

	@pytest.mark.asyncio
	async def test_search_gateway_error(self, scene_service, mock_scene_gateway, sample_scene_filter_dto):
		"""Test scene search when gateway raises error"""
		# Arrange
		mock_scene_gateway.search.side_effect = Exception("Database error")

		# Act & Assert
		with pytest.raises(Exception, match="Database error"):
			await scene_service.search(sample_scene_filter_dto)

		mock_scene_gateway.search.assert_called_once_with(sample_scene_filter_dto)

	@pytest.mark.asyncio
	async def test_delete_success(self, scene_service, mock_scene_gateway, sample_scene):
		"""Test successful scene deletion"""
		# Arrange
		scene_id = uuid4()
		mock_scene_gateway.get_one.return_value = sample_scene
		mock_scene_gateway.delete.return_value = None

		# Act
		await scene_service.delete(scene_id)

		# Assert
		mock_scene_gateway.get_one.assert_called_once_with(scene_id)
		mock_scene_gateway.delete.assert_called_once_with(scene_id)

	@pytest.mark.asyncio
	async def test_delete_not_found(self, scene_service, mock_scene_gateway):
		"""Test deletion of non-existent scene"""
		# Arrange
		scene_id = uuid4()
		mock_scene_gateway.get_one.side_effect = ValueError(f"Scene with ID {scene_id} not found")

		# Act & Assert
		with pytest.raises(ValueError, match=f"Scene with ID {scene_id} not found"):
			await scene_service.delete(scene_id)

		mock_scene_gateway.get_one.assert_called_once_with(scene_id)
		mock_scene_gateway.delete.assert_not_called()

	@pytest.mark.asyncio
	async def test_delete_gateway_error(self, scene_service, mock_scene_gateway, sample_scene):
		"""Test scene deletion when gateway raises error"""
		# Arrange
		scene_id = uuid4()
		mock_scene_gateway.get_one.return_value = sample_scene
		mock_scene_gateway.delete.side_effect = Exception("Database error")

		# Act & Assert
		with pytest.raises(Exception, match="Database error"):
			await scene_service.delete(scene_id)

		mock_scene_gateway.delete.assert_called_once_with(scene_id)

	@pytest.mark.asyncio
	async def test_update_success(self, scene_service, mock_scene_gateway, sample_scene):
		"""Test successful scene update"""
		# Arrange
		scene_id = uuid4()
		mock_scene_gateway.get_one.return_value = sample_scene
		mock_scene_gateway.update.return_value = None

		# Act
		await scene_service.update(scene_id, sample_scene)

		# Assert
		mock_scene_gateway.get_one.assert_called_once_with(scene_id)
		mock_scene_gateway.update.assert_called_once_with(scene_id, sample_scene)

	@pytest.mark.asyncio
	async def test_update_not_found(self, scene_service, mock_scene_gateway, sample_scene):
		"""Test update of non-existent scene"""
		# Arrange
		scene_id = uuid4()
		mock_scene_gateway.get_one.side_effect = ValueError(f"Scene with ID {scene_id} not found")

		# Act & Assert
		with pytest.raises(ValueError, match=f"Scene with ID {scene_id} not found"):
			await scene_service.update(scene_id, sample_scene)

		mock_scene_gateway.get_one.assert_called_once_with(scene_id)
		mock_scene_gateway.update.assert_not_called()

	@pytest.mark.asyncio
	async def test_update_gateway_error(self, scene_service, mock_scene_gateway, sample_scene):
		"""Test scene update when gateway raises error"""
		# Arrange
		scene_id = uuid4()
		mock_scene_gateway.get_one.return_value = sample_scene
		mock_scene_gateway.update.side_effect = Exception("Database error")

		# Act & Assert
		with pytest.raises(Exception, match="Database error"):
			await scene_service.update(scene_id, sample_scene)

		mock_scene_gateway.update.assert_called_once_with(scene_id, sample_scene)

	@pytest.mark.asyncio
	async def test_like_sets_like_and_returns_state(self, scene_service, mock_scene_gateway, mock_uow):
		# Arrange
		scene_uuid = uuid4()
		user_id = uuid4()
		mock_scene_gateway.count_likes.return_value = 5

		# Act
		result = await scene_service.like(scene_uuid, user_id)

		# Assert
		assert result == LikeState(liked=True, likes_count=5)
		mock_scene_gateway.set_like.assert_called_once_with(scene_uuid, user_id)
		mock_scene_gateway.count_likes.assert_called_once_with(scene_uuid)
		mock_uow.__aenter__.assert_awaited()

	@pytest.mark.asyncio
	async def test_unlike_unsets_like_and_returns_state(self, scene_service, mock_scene_gateway):
		# Arrange
		scene_uuid = uuid4()
		user_id = uuid4()
		mock_scene_gateway.count_likes.return_value = 4

		# Act
		result = await scene_service.unlike(scene_uuid, user_id)

		# Assert
		assert result == LikeState(liked=False, likes_count=4)
		mock_scene_gateway.unset_like.assert_called_once_with(scene_uuid, user_id)

	@pytest.mark.asyncio
	async def test_get_like_state_reflects_gateway(self, scene_service, mock_scene_gateway):
		# Arrange
		scene_uuid = uuid4()
		user_id = uuid4()
		mock_scene_gateway.is_liked.return_value = True
		mock_scene_gateway.count_likes.return_value = 7

		# Act
		result = await scene_service.get_like_state(scene_uuid, user_id)

		# Assert
		assert result == LikeState(liked=True, likes_count=7)
		mock_scene_gateway.is_liked.assert_called_once_with(scene_uuid, user_id)

	@pytest.mark.asyncio
	async def test_bookmark_sets_bookmark_and_returns_state(self, scene_service, mock_scene_gateway):
		# Arrange
		scene_uuid = uuid4()
		user_id = uuid4()

		# Act
		result = await scene_service.bookmark(scene_uuid, user_id)

		# Assert
		assert result == BookmarkState(bookmarked=True)
		mock_scene_gateway.set_bookmark.assert_called_once_with(scene_uuid, user_id)

	@pytest.mark.asyncio
	async def test_unbookmark_unsets_bookmark_and_returns_state(self, scene_service, mock_scene_gateway):
		# Arrange
		scene_uuid = uuid4()
		user_id = uuid4()

		# Act
		result = await scene_service.unbookmark(scene_uuid, user_id)

		# Assert
		assert result == BookmarkState(bookmarked=False)
		mock_scene_gateway.unset_bookmark.assert_called_once_with(scene_uuid, user_id)

	@pytest.mark.asyncio
	async def test_get_bookmark_state_reflects_gateway(self, scene_service, mock_scene_gateway):
		# Arrange
		scene_uuid = uuid4()
		user_id = uuid4()
		mock_scene_gateway.is_bookmarked.return_value = True

		# Act
		result = await scene_service.get_bookmark_state(scene_uuid, user_id)

		# Assert
		assert result == BookmarkState(bookmarked=True)
		mock_scene_gateway.is_bookmarked.assert_called_once_with(scene_uuid, user_id)

	@pytest.mark.asyncio
	async def test_like_missing_scene_raises_without_mutating(self, scene_service, mock_scene_gateway):
		# A missing target must surface as NoResultFound (→ 404) before any write.
		scene_uuid = uuid4()
		user_id = uuid4()
		mock_scene_gateway.get_one.side_effect = NoResultFound("scene not found")

		with pytest.raises(NoResultFound):
			await scene_service.like(scene_uuid, user_id)

		mock_scene_gateway.set_like.assert_not_called()
		mock_scene_gateway.count_likes.assert_not_called()

	@pytest.mark.asyncio
	async def test_get_like_state_missing_scene_raises(self, scene_service, mock_scene_gateway):
		# The read path must also 404 rather than silently report likes_count: 0.
		scene_uuid = uuid4()
		user_id = uuid4()
		mock_scene_gateway.get_one.side_effect = NoResultFound("scene not found")

		with pytest.raises(NoResultFound):
			await scene_service.get_like_state(scene_uuid, user_id)

		mock_scene_gateway.is_liked.assert_not_called()
		mock_scene_gateway.count_likes.assert_not_called()

	@pytest.mark.asyncio
	async def test_bookmark_missing_scene_raises_without_mutating(self, scene_service, mock_scene_gateway):
		scene_uuid = uuid4()
		user_id = uuid4()
		mock_scene_gateway.get_one.side_effect = NoResultFound("scene not found")

		with pytest.raises(NoResultFound):
			await scene_service.bookmark(scene_uuid, user_id)

		mock_scene_gateway.set_bookmark.assert_not_called()

	@pytest.mark.asyncio
	async def test_attach_characters_calls_get_one_then_attach(self, scene_service, mock_scene_gateway):
		# Arrange
		scene_uuid = uuid4()
		character_ids = [uuid4(), uuid4()]

		# Act
		await scene_service.attach_characters(scene_uuid, character_ids)

		# Assert
		mock_scene_gateway.get_one.assert_called_once_with(scene_uuid)
		mock_scene_gateway.attach_characters.assert_called_once_with(scene_uuid, character_ids)

	@pytest.mark.asyncio
	async def test_attach_characters_missing_scene_raises_without_mutating(self, scene_service, mock_scene_gateway):
		scene_uuid = uuid4()
		mock_scene_gateway.get_one.side_effect = NoResultFound("scene not found")

		with pytest.raises(NoResultFound):
			await scene_service.attach_characters(scene_uuid, [uuid4()])

		mock_scene_gateway.attach_characters.assert_not_called()
