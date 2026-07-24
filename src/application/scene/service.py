import logging
from dataclasses import dataclass
from uuid import UUID

from src.infrastructure.logging.logger import Logger
from src.application.ports.authorization import IAuthorizationService
from src.application.ports.scenes import ISceneService, ISceneGateway, IInitialMessageGateway
from src.application.ports.common import IUnitOfWork, Page, LikeState, BookmarkState
from src.application.scene.schemas import SceneFilterDTO
from src.domain.models import Scene


@dataclass
class SceneService(ISceneService):
	uow: IUnitOfWork
	gateway: ISceneGateway
	initial_message_gateway: IInitialMessageGateway
	authz: IAuthorizationService
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)

	async def create_scene(self, scene: Scene) -> UUID:
		self.logger.info(f"Creating scene: {scene.title}")

		if not scene.initial_messages:
			# A scene must offer at least one initial message — otherwise a chat
			# started from it could never satisfy the "choose before first message" gate.
			raise ValueError("Scene must have at least one initial message")

		async with self.uow:
			try:
				scene_id = await self.gateway.create(scene)
				await self.initial_message_gateway.bulk_create(scene_id, scene.initial_messages)
				self.logger.info(f"Successfully created scene with ID: {scene_id}")
				return scene_id
			except Exception as e:
				self.logger.error(f"Failed to create scene: {e}")
				raise

	async def get_one(self, scene_uuid: UUID, actor_id: UUID | None) -> Scene:
		self.logger.info(f"Getting scene: {scene_uuid}")

		scene = await self.gateway.get_one(scene_uuid)
		self.authz.require_visible(is_public=scene.is_public, owner_id=scene.owner_id, actor_id=actor_id, noun="scene")

		self.logger.info(f"Successfully retrieved scene: {scene_uuid}")
		return scene

	async def search(self, dto: SceneFilterDTO, actor_id: UUID | None) -> Page[Scene]:
		self.logger.info(f"Searching scenes with filters: {dto}")
		return await self.gateway.search(dto, actor_id=actor_id)

	async def delete(self, scene_uuid: UUID, actor_id: UUID):
		self.logger.info(f"Deleting scene: {scene_uuid}")

		scene = await self.gateway.get_one(scene_uuid)
		self.authz.require_owned(owner_id=scene.owner_id, actor_id=actor_id, noun="scene")

		async with self.uow:
			await self.gateway.delete(scene_uuid)
		self.logger.info(f"Successfully deleted scene: {scene_uuid}")

	async def update(self, target_scene_uuid: UUID, new_scene_data: Scene, actor_id: UUID):
		self.logger.info(f"Updating scene: {target_scene_uuid}")

		scene = await self.gateway.get_one(target_scene_uuid)
		self.authz.require_owned(owner_id=scene.owner_id, actor_id=actor_id, noun="scene")

		async with self.uow:
			await self.gateway.update(target_scene_uuid, new_scene_data)
		self.logger.info(f"Successfully updated scene: {target_scene_uuid}")

	async def like(self, scene_uuid: UUID, user_id: UUID) -> LikeState:
		self.logger.info(f"User {user_id} liking scene {scene_uuid}")

		async with self.uow:
			await self.get_one(scene_uuid, user_id)
			await self.gateway.set_like(scene_uuid, user_id)
			# Read the count inside the same tx so it reflects this like.
			count = await self.gateway.count_likes(scene_uuid)
		return LikeState(liked=True, likes_count=count)

	async def unlike(self, scene_uuid: UUID, user_id: UUID) -> LikeState:
		self.logger.info(f"User {user_id} unliking scene {scene_uuid}")

		async with self.uow:
			await self.get_one(scene_uuid, user_id)
			await self.gateway.unset_like(scene_uuid, user_id)
			count = await self.gateway.count_likes(scene_uuid)
		return LikeState(liked=False, likes_count=count)

	async def get_like_state(self, scene_uuid: UUID, user_id: UUID) -> LikeState:
		await self.get_one(scene_uuid, user_id)
		liked = await self.gateway.is_liked(scene_uuid, user_id)
		count = await self.gateway.count_likes(scene_uuid)
		return LikeState(liked=liked, likes_count=count)

	async def bookmark(self, scene_uuid: UUID, user_id: UUID) -> BookmarkState:
		self.logger.info(f"User {user_id} bookmarking scene {scene_uuid}")

		async with self.uow:
			await self.get_one(scene_uuid, user_id)
			await self.gateway.set_bookmark(scene_uuid, user_id)
		return BookmarkState(bookmarked=True)

	async def unbookmark(self, scene_uuid: UUID, user_id: UUID) -> BookmarkState:
		self.logger.info(f"User {user_id} unbookmarking scene {scene_uuid}")

		async with self.uow:
			await self.get_one(scene_uuid, user_id)
			await self.gateway.unset_bookmark(scene_uuid, user_id)
		return BookmarkState(bookmarked=False)

	async def get_bookmark_state(self, scene_uuid: UUID, user_id: UUID) -> BookmarkState:
		await self.get_one(scene_uuid, user_id)
		bookmarked = await self.gateway.is_bookmarked(scene_uuid, user_id)
		return BookmarkState(bookmarked=bookmarked)

	async def attach_characters(self, scene_uuid: UUID, character_ids: list[UUID]) -> None:
		self.logger.info(f"Attaching {len(character_ids)} character(s) to scene {scene_uuid}")

		async with self.uow:
			await self.gateway.get_one(scene_uuid)
			await self.gateway.attach_characters(scene_uuid, character_ids)
