import logging
from dataclasses import dataclass
from uuid import UUID

from src.application.character.schemas import CharacterFilterDTO
from src.application.ports.authorization import IAuthorizationService
from src.application.ports.characters import ICharacterGateway, ICharacterService
from src.application.ports.common import BookmarkState, IUnitOfWork, LikeState, Page
from src.domain.models import Character
from src.infrastructure.logging.logger import Logger


@dataclass
class CharacterService(ICharacterService):
	uow: IUnitOfWork
	gateway: ICharacterGateway
	authz: IAuthorizationService
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

	async def get_one(self, character_uuid: UUID, actor_id: UUID | None) -> Character:
		self.logger.info(f"Getting character: {character_uuid}")

		character = await self.gateway.get_one(character_uuid)
		self.authz.require_visible(
			is_public=character.is_public, owner_id=character.owner_id, actor_id=actor_id, noun="character"
		)

		self.logger.info(f"Successfully retrieved character: {character_uuid}")
		return character

	async def search(self, dto: CharacterFilterDTO, actor_id: UUID | None) -> Page[Character]:
		self.logger.info(f"Searching characters with filters: {dto}")
		return await self.gateway.search(dto, actor_id=actor_id)

	async def get_for_scene(self, scene_id: UUID, actor_id: UUID) -> list[Character]:
		self.logger.info(f"Getting characters for scene: {scene_id}")

		try:
			characters = await self.gateway.get_for_scene(scene_id)
			visible = [
				c
				for c in characters
				if self.authz.visible_to(is_public=c.is_public, owner_id=c.owner_id, actor_id=actor_id)
			]
			self.logger.info(f"Found {len(visible)} character(s) for scene {scene_id}")
			return visible
		except Exception as e:
			self.logger.error(f"Failed to get characters for scene {scene_id}: {e}")
			raise

	async def delete(self, character_uuid: UUID, actor_id: UUID):
		self.logger.info(f"Deleting character: {character_uuid}")

		character = await self.gateway.get_one(character_uuid)
		self.authz.require_owned(owner_id=character.owner_id, actor_id=actor_id, noun="character")

		async with self.uow:
			await self.gateway.delete(character_uuid)
		self.logger.info(f"Successfully deleted character: {character_uuid}")

	async def update(self, target_character_uuid: UUID, new_character_data: Character, actor_id: UUID):
		self.logger.info(f"Updating character: {target_character_uuid}")

		character = await self.gateway.get_one(target_character_uuid)
		self.authz.require_owned(owner_id=character.owner_id, actor_id=actor_id, noun="character")

		async with self.uow:
			await self.gateway.update(target_character_uuid, new_character_data)
		self.logger.info(f"Successfully updated character: {target_character_uuid}")

	async def like(self, character_uuid: UUID, user_id: UUID) -> LikeState:
		self.logger.info(f"User {user_id} liking character {character_uuid}")

		async with self.uow:
			await self.get_one(character_uuid, user_id)
			await self.gateway.set_like(character_uuid, user_id)
			count = await self.gateway.count_likes(character_uuid)
		return LikeState(liked=True, likes_count=count)

	async def unlike(self, character_uuid: UUID, user_id: UUID) -> LikeState:
		self.logger.info(f"User {user_id} unliking character {character_uuid}")

		async with self.uow:
			await self.get_one(character_uuid, user_id)
			await self.gateway.unset_like(character_uuid, user_id)
			count = await self.gateway.count_likes(character_uuid)
		return LikeState(liked=False, likes_count=count)

	async def get_like_state(self, character_uuid: UUID, user_id: UUID) -> LikeState:
		await self.get_one(character_uuid, user_id)
		liked = await self.gateway.is_liked(character_uuid, user_id)
		count = await self.gateway.count_likes(character_uuid)
		return LikeState(liked=liked, likes_count=count)

	async def bookmark(self, character_uuid: UUID, user_id: UUID) -> BookmarkState:
		self.logger.info(f"User {user_id} bookmarking character {character_uuid}")

		async with self.uow:
			await self.get_one(character_uuid, user_id)
			await self.gateway.set_bookmark(character_uuid, user_id)
		return BookmarkState(bookmarked=True)

	async def unbookmark(self, character_uuid: UUID, user_id: UUID) -> BookmarkState:
		self.logger.info(f"User {user_id} unbookmarking character {character_uuid}")

		async with self.uow:
			await self.get_one(character_uuid, user_id)
			await self.gateway.unset_bookmark(character_uuid, user_id)
		return BookmarkState(bookmarked=False)

	async def get_bookmark_state(self, character_uuid: UUID, user_id: UUID) -> BookmarkState:
		await self.get_one(character_uuid, user_id)
		bookmarked = await self.gateway.is_bookmarked(character_uuid, user_id)
		return BookmarkState(bookmarked=bookmarked)
