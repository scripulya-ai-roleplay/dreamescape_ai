from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import NoResultFound

from src.application.auth.authz import AuthorizationService
from src.application.character.schemas import CharacterFilterDTO
from src.application.character.service import CharacterService
from src.application.ports.common import BookmarkState, LikeState, Page
from src.domain.models import Character


@pytest.mark.unit
class TestCharacterService:
	@pytest.fixture
	def authz(self):
		return AuthorizationService()

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
	def character_service(self, mock_character_gateway, mock_uow, authz):
		return CharacterService(gateway=mock_character_gateway, uow=mock_uow, authz=authz)

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
	async def test_get_one_public_anonymous_ok(self, character_service, mock_character_gateway, sample_character):
		# A public character is readable without authentication (actor_id=None).
		character_uuid = uuid4()
		mock_character_gateway.get_one.return_value = sample_character

		result = await character_service.get_one(character_uuid, None)

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
			await character_service.get_one(character_uuid, None)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_get_one_private_anonymous_raises_401(self, character_service, mock_character_gateway):
		# A private character must not be readable anonymously.
		mock_character_gateway.get_one.return_value = Character(
			id=uuid4(), name="Secret", system_prompt="p", is_public=False, owner_id=uuid4()
		)

		with pytest.raises(HTTPException) as exc:
			await character_service.get_one(uuid4(), None)
		assert exc.value.status_code == 401

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_get_one_private_other_user_raises_403(self, character_service, mock_character_gateway):
		owner_id = uuid4()
		mock_character_gateway.get_one.return_value = Character(
			id=uuid4(), name="Secret", system_prompt="p", is_public=False, owner_id=owner_id
		)

		with pytest.raises(HTTPException) as exc:
			await character_service.get_one(uuid4(), uuid4())  # a different user
		assert exc.value.status_code == 403

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_get_one_private_owner_ok(self, character_service, mock_character_gateway):
		owner_id = uuid4()
		character = Character(id=uuid4(), name="Secret", system_prompt="p", is_public=False, owner_id=owner_id)
		mock_character_gateway.get_one.return_value = character

		result = await character_service.get_one(character.id, owner_id)

		assert result == character

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_search_success(
		self, character_service, mock_character_gateway, sample_character, sample_character_filter_dto
	):
		# Arrange
		actor_id = uuid4()
		page_result = Page[Character](items=[sample_character], count=1, offset=0, limit=1)
		mock_character_gateway.search.return_value = page_result

		# Act
		result = await character_service.search(sample_character_filter_dto, actor_id)

		# Assert
		assert result == page_result
		mock_character_gateway.search.assert_called_once_with(sample_character_filter_dto, actor_id=actor_id)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_search_gateway_error(self, character_service, mock_character_gateway, sample_character_filter_dto):
		# Arrange
		mock_character_gateway.search.side_effect = Exception("Search error")

		# Act & Assert
		with pytest.raises(Exception, match="Search error"):
			await character_service.search(sample_character_filter_dto, uuid4())

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_get_for_scene_filters_to_public_or_owned(self, character_service, mock_character_gateway):
		# Arrange: public, actor-owned private, and another user's private characters.
		actor_id = uuid4()
		other_id = uuid4()
		public_char = Character(id=uuid4(), name="Public", system_prompt="p", is_public=True, owner_id=other_id)
		owned_private = Character(id=uuid4(), name="Mine", system_prompt="p", is_public=False, owner_id=actor_id)
		others_private = Character(id=uuid4(), name="Secret", system_prompt="p", is_public=False, owner_id=other_id)
		mock_character_gateway.get_for_scene.return_value = [public_char, owned_private, others_private]

		# Act
		scene_id = uuid4()
		result = await character_service.get_for_scene(scene_id, actor_id)

		# Assert: public + own are visible; another user's private character is hidden.
		assert result == [public_char, owned_private]
		mock_character_gateway.get_for_scene.assert_called_once_with(scene_id)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_delete_success(self, character_service, mock_character_gateway, sample_character):
		# Arrange
		character_uuid = uuid4()
		mock_character_gateway.get_one.return_value = sample_character

		# Act
		await character_service.delete(character_uuid, sample_character.owner_id)

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
			await character_service.delete(character_uuid, uuid4())

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_delete_not_owner_raises_403_without_deleting(
		self, character_service, mock_character_gateway, sample_character
	):
		mock_character_gateway.get_one.return_value = sample_character

		with pytest.raises(HTTPException) as exc:
			await character_service.delete(uuid4(), uuid4())  # not the owner
		assert exc.value.status_code == 403

		mock_character_gateway.delete.assert_not_called()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_delete_gateway_error(self, character_service, mock_character_gateway, sample_character):
		# Arrange
		character_uuid = uuid4()
		mock_character_gateway.get_one.return_value = sample_character
		mock_character_gateway.delete.side_effect = Exception("Delete error")

		# Act & Assert
		with pytest.raises(Exception, match="Delete error"):
			await character_service.delete(character_uuid, sample_character.owner_id)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_update_success(self, character_service, mock_character_gateway, sample_character):
		# Arrange
		character_uuid = uuid4()
		mock_character_gateway.get_one.return_value = sample_character

		# Act
		await character_service.update(character_uuid, sample_character, sample_character.owner_id)

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
			await character_service.update(character_uuid, sample_character, uuid4())

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_update_not_owner_raises_403_without_updating(
		self, character_service, mock_character_gateway, sample_character
	):
		mock_character_gateway.get_one.return_value = sample_character

		with pytest.raises(HTTPException) as exc:
			await character_service.update(uuid4(), sample_character, uuid4())  # not the owner
		assert exc.value.status_code == 403

		mock_character_gateway.update.assert_not_called()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_update_gateway_error(self, character_service, mock_character_gateway, sample_character):
		# Arrange
		character_uuid = uuid4()
		mock_character_gateway.get_one.return_value = sample_character
		mock_character_gateway.update.side_effect = Exception("Update error")

		# Act & Assert
		with pytest.raises(Exception, match="Update error"):
			await character_service.update(character_uuid, sample_character, sample_character.owner_id)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_like_sets_like_and_returns_state(self, character_service, mock_character_gateway, mock_uow):
		# Arrange
		character_uuid = uuid4()
		user_id = uuid4()
		mock_character_gateway.count_likes.return_value = 5

		# Act
		result = await character_service.like(character_uuid, user_id)

		# Assert
		assert result == LikeState(liked=True, likes_count=5)
		mock_character_gateway.set_like.assert_called_once_with(character_uuid, user_id)
		mock_character_gateway.count_likes.assert_called_once_with(character_uuid)
		mock_uow.__aenter__.assert_awaited()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_unlike_unsets_like_and_returns_state(self, character_service, mock_character_gateway):
		# Arrange
		character_uuid = uuid4()
		user_id = uuid4()
		mock_character_gateway.count_likes.return_value = 4

		# Act
		result = await character_service.unlike(character_uuid, user_id)

		# Assert
		assert result == LikeState(liked=False, likes_count=4)
		mock_character_gateway.unset_like.assert_called_once_with(character_uuid, user_id)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_get_like_state_reflects_gateway(self, character_service, mock_character_gateway):
		# Arrange
		character_uuid = uuid4()
		user_id = uuid4()
		mock_character_gateway.is_liked.return_value = True
		mock_character_gateway.count_likes.return_value = 7

		# Act
		result = await character_service.get_like_state(character_uuid, user_id)

		# Assert
		assert result == LikeState(liked=True, likes_count=7)
		mock_character_gateway.is_liked.assert_called_once_with(character_uuid, user_id)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_bookmark_sets_bookmark_and_returns_state(self, character_service, mock_character_gateway):
		# Arrange
		character_uuid = uuid4()
		user_id = uuid4()

		# Act
		result = await character_service.bookmark(character_uuid, user_id)

		# Assert
		assert result == BookmarkState(bookmarked=True)
		mock_character_gateway.set_bookmark.assert_called_once_with(character_uuid, user_id)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_unbookmark_unsets_bookmark_and_returns_state(self, character_service, mock_character_gateway):
		# Arrange
		character_uuid = uuid4()
		user_id = uuid4()

		# Act
		result = await character_service.unbookmark(character_uuid, user_id)

		# Assert
		assert result == BookmarkState(bookmarked=False)
		mock_character_gateway.unset_bookmark.assert_called_once_with(character_uuid, user_id)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_get_bookmark_state_reflects_gateway(self, character_service, mock_character_gateway):
		# Arrange
		character_uuid = uuid4()
		user_id = uuid4()
		mock_character_gateway.is_bookmarked.return_value = True

		# Act
		result = await character_service.get_bookmark_state(character_uuid, user_id)

		# Assert
		assert result == BookmarkState(bookmarked=True)
		mock_character_gateway.is_bookmarked.assert_called_once_with(character_uuid, user_id)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_like_private_not_owner_raises_403_without_mutating(self, character_service, mock_character_gateway):
		# A private character owned by someone else is not likable: the visibility
		# gate (routed through get_one) 403s before any like row is written.
		mock_character_gateway.get_one.return_value = Character(
			id=uuid4(), name="Secret", system_prompt="p", is_public=False, owner_id=uuid4()
		)

		with pytest.raises(HTTPException) as exc:
			await character_service.like(uuid4(), uuid4())  # not the owner
		assert exc.value.status_code == 403

		mock_character_gateway.set_like.assert_not_called()
		mock_character_gateway.count_likes.assert_not_called()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_bookmark_private_not_owner_raises_403_without_mutating(
		self, character_service, mock_character_gateway
	):
		mock_character_gateway.get_one.return_value = Character(
			id=uuid4(), name="Secret", system_prompt="p", is_public=False, owner_id=uuid4()
		)

		with pytest.raises(HTTPException) as exc:
			await character_service.bookmark(uuid4(), uuid4())  # not the owner
		assert exc.value.status_code == 403

		mock_character_gateway.set_bookmark.assert_not_called()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_like_missing_character_raises_without_mutating(self, character_service, mock_character_gateway):
		# A missing target must surface as NoResultFound (→ 404) before any write.
		character_uuid = uuid4()
		user_id = uuid4()
		mock_character_gateway.get_one.side_effect = NoResultFound("character not found")

		with pytest.raises(NoResultFound):
			await character_service.like(character_uuid, user_id)

		mock_character_gateway.set_like.assert_not_called()
		mock_character_gateway.count_likes.assert_not_called()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_get_like_state_missing_character_raises(self, character_service, mock_character_gateway):
		# The read path must also 404 rather than silently report likes_count: 0.
		character_uuid = uuid4()
		user_id = uuid4()
		mock_character_gateway.get_one.side_effect = NoResultFound("character not found")

		with pytest.raises(NoResultFound):
			await character_service.get_like_state(character_uuid, user_id)

		mock_character_gateway.is_liked.assert_not_called()
		mock_character_gateway.count_likes.assert_not_called()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_bookmark_missing_character_raises_without_mutating(self, character_service, mock_character_gateway):
		character_uuid = uuid4()
		user_id = uuid4()
		mock_character_gateway.get_one.side_effect = NoResultFound("character not found")

		with pytest.raises(NoResultFound):
			await character_service.bookmark(character_uuid, user_id)

		mock_character_gateway.set_bookmark.assert_not_called()
