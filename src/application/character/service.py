import logging
from dataclasses import dataclass
from uuid import UUID

from src.infrastructure.logging.logger import Logger
from src.application.character.schemas import CharacterFilterDTO
from src.application.ports import (
	ICharacterService,
	IUnitOfWork,
	ICharacterGateway,
	Page,
	LikeState,
	BookmarkState,
)
from src.domain.models import Character


@dataclass
class CharacterService(ICharacterService):
	uow: IUnitOfWork
	gateway: ICharacterGateway
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)

	async def create_character(self, character: Character) -> UUID:
		self.logger.info(f"Creating character: {character.name}")

		async with self.uow:
			try:
				character_id = await self.gateway.create(character)
				self.logger.info(f"Successfully created character with ID: {character_id}")
				return character_id
			except Exception as e:
				self.logger.error(f"Failed to create character: {e}")
				raise

	async def get_one(self, character_uuid: UUID) -> Character:
		self.logger.info(f"Getting character: {character_uuid}")

		try:
			character = await self.gateway.get_one(character_uuid)
			self.logger.info(f"Successfully retrieved character: {character_uuid}")
			return character
		except Exception as e:
			self.logger.error(f"Failed to get character {character_uuid}: {e}")
			raise

	async def search(self, dto: CharacterFilterDTO) -> Page[Character]:
		self.logger.info(f"Searching characters with filters: {dto}")

		try:
			result = await self.gateway.search(dto)
			self.logger.info(f"Found {result.count} characters")
			return result
		except Exception as e:
			self.logger.error(f"Failed to search characters: {e}")
			raise

	async def get_for_scene(self, scene_id: UUID) -> list[Character]:
		self.logger.info(f"Getting characters for scene: {scene_id}")

		try:
			characters = await self.gateway.get_for_scene(scene_id)
			self.logger.info(f"Found {len(characters)} character(s) for scene {scene_id}")
			return characters
		except Exception as e:
			self.logger.error(f"Failed to get characters for scene {scene_id}: {e}")
			raise

	async def delete(self, character_uuid: UUID):
		self.logger.info(f"Deleting character: {character_uuid}")

		async with self.uow:
			try:
				# Check if character exists before deleting
				await self.gateway.get_one(character_uuid)
				await self.gateway.delete(character_uuid)
				self.logger.info(f"Successfully deleted character: {character_uuid}")
			except ValueError:
				# Re-raise validation errors as-is
				raise
			except Exception as e:
				self.logger.error(f"Failed to delete character {character_uuid}: {e}")
				raise

	async def update(self, target_character_uuid: UUID, new_character_data: Character):
		self.logger.info(f"Updating character: {target_character_uuid}")

		async with self.uow:
			try:
				# Check if character exists before updating
				await self.gateway.get_one(target_character_uuid)
				await self.gateway.update(target_character_uuid, new_character_data)
				self.logger.info(f"Successfully updated character: {target_character_uuid}")
			except ValueError:
				# Re-raise validation errors as-is
				raise
			except Exception as e:
				self.logger.error(f"Failed to update character {target_character_uuid}: {e}")
				raise

	# Every like/bookmark verb resolves the character first. A missing target then
	# raises NoResultFound (→ 404 via the global handler) instead of a raw INSERT
	# tripping the FK (→ 409 leaking the constraint name) on the writes, or the
	# reads silently reporting likes_count: 0 / bookmarked: false. Matches how
	# delete/update already gate on get_one.

	async def like(self, character_uuid: UUID, user_id: UUID) -> LikeState:
		self.logger.info(f"User {user_id} liking character {character_uuid}")

		async with self.uow:
			await self.gateway.get_one(character_uuid)
			await self.gateway.set_like(character_uuid, user_id)
			# Read the count inside the same tx so it reflects this like.
			count = await self.gateway.count_likes(character_uuid)
		return LikeState(liked=True, likes_count=count)

	async def unlike(self, character_uuid: UUID, user_id: UUID) -> LikeState:
		self.logger.info(f"User {user_id} unliking character {character_uuid}")

		async with self.uow:
			await self.gateway.get_one(character_uuid)
			await self.gateway.unset_like(character_uuid, user_id)
			count = await self.gateway.count_likes(character_uuid)
		return LikeState(liked=False, likes_count=count)

	async def get_like_state(self, character_uuid: UUID, user_id: UUID) -> LikeState:
		await self.gateway.get_one(character_uuid)
		liked = await self.gateway.is_liked(character_uuid, user_id)
		count = await self.gateway.count_likes(character_uuid)
		return LikeState(liked=liked, likes_count=count)

	async def bookmark(self, character_uuid: UUID, user_id: UUID) -> BookmarkState:
		self.logger.info(f"User {user_id} bookmarking character {character_uuid}")

		async with self.uow:
			await self.gateway.get_one(character_uuid)
			await self.gateway.set_bookmark(character_uuid, user_id)
		return BookmarkState(bookmarked=True)

	async def unbookmark(self, character_uuid: UUID, user_id: UUID) -> BookmarkState:
		self.logger.info(f"User {user_id} unbookmarking character {character_uuid}")

		async with self.uow:
			await self.gateway.get_one(character_uuid)
			await self.gateway.unset_bookmark(character_uuid, user_id)
		return BookmarkState(bookmarked=False)

	async def get_bookmark_state(self, character_uuid: UUID, user_id: UUID) -> BookmarkState:
		await self.gateway.get_one(character_uuid)
		bookmarked = await self.gateway.is_bookmarked(character_uuid, user_id)
		return BookmarkState(bookmarked=bookmarked)
