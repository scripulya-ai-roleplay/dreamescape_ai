import logging
from dataclasses import dataclass
from uuid import UUID

from src.application.ports import (
	ISceneService,
	IUnitOfWork,
	ISceneGateway,
	Page,
	LikeState,
	BookmarkState,
)
from src.application.scene.schemas import SceneFilterDTO
from src.domain.models import Scene

logger = logging.getLogger(__name__)


@dataclass
class SceneService(ISceneService):
	uow: IUnitOfWork
	gateway: ISceneGateway

	async def create_scene(self, scene: Scene) -> UUID:
		logger.info(f"Creating scene: {scene.title}")

		async with self.uow:
			try:
				scene_id = await self.gateway.create(scene)
				logger.info(f"Successfully created scene with ID: {scene_id}")
				return scene_id
			except Exception as e:
				logger.error(f"Failed to create scene: {e}")
				raise

	async def get_one(self, scene_uuid: UUID) -> Scene:
		logger.info(f"Getting scene: {scene_uuid}")

		try:
			scene = await self.gateway.get_one(scene_uuid)
			logger.info(f"Successfully retrieved scene: {scene_uuid}")
			return scene
		except Exception as e:
			logger.error(f"Failed to get scene {scene_uuid}: {e}")
			raise

	async def search(self, dto: SceneFilterDTO) -> Page[Scene]:
		logger.info(f"Searching scenes with filters: {dto}")

		try:
			result = await self.gateway.search(dto)
			logger.info(f"Found {result.count} scenes")
			return result
		except Exception as e:
			logger.error(f"Failed to search scenes: {e}")
			raise

	async def delete(self, scene_uuid: UUID):
		logger.info(f"Deleting scene: {scene_uuid}")

		async with self.uow:
			try:
				# Check if scene exists before deleting
				await self.gateway.get_one(scene_uuid)
				await self.gateway.delete(scene_uuid)
				logger.info(f"Successfully deleted scene: {scene_uuid}")
			except ValueError:
				# Re-raise validation errors as-is
				raise
			except Exception as e:
				logger.error(f"Failed to delete scene {scene_uuid}: {e}")
				raise

	async def update(self, target_scene_uuid: UUID, new_scene_data: Scene):
		logger.info(f"Updating scene: {target_scene_uuid}")

		async with self.uow:
			try:
				# Check if scene exists before updating
				await self.gateway.get_one(target_scene_uuid)
				await self.gateway.update(target_scene_uuid, new_scene_data)
				logger.info(f"Successfully updated scene: {target_scene_uuid}")
			except ValueError:
				# Re-raise validation errors as-is
				raise
			except Exception as e:
				logger.error(f"Failed to update scene {target_scene_uuid}: {e}")
				raise

	async def like(self, scene_uuid: UUID, user_id: UUID) -> LikeState:
		logger.info(f"User {user_id} liking scene {scene_uuid}")

		async with self.uow:
			await self.gateway.set_like(scene_uuid, user_id)
			# Read the count inside the same tx so it reflects this like.
			count = await self.gateway.count_likes(scene_uuid)
		return LikeState(liked=True, likes_count=count)

	async def unlike(self, scene_uuid: UUID, user_id: UUID) -> LikeState:
		logger.info(f"User {user_id} unliking scene {scene_uuid}")

		async with self.uow:
			await self.gateway.unset_like(scene_uuid, user_id)
			count = await self.gateway.count_likes(scene_uuid)
		return LikeState(liked=False, likes_count=count)

	async def get_like_state(self, scene_uuid: UUID, user_id: UUID) -> LikeState:
		liked = await self.gateway.is_liked(scene_uuid, user_id)
		count = await self.gateway.count_likes(scene_uuid)
		return LikeState(liked=liked, likes_count=count)

	async def bookmark(self, scene_uuid: UUID, user_id: UUID) -> BookmarkState:
		logger.info(f"User {user_id} bookmarking scene {scene_uuid}")

		async with self.uow:
			await self.gateway.set_bookmark(scene_uuid, user_id)
		return BookmarkState(bookmarked=True)

	async def unbookmark(self, scene_uuid: UUID, user_id: UUID) -> BookmarkState:
		logger.info(f"User {user_id} unbookmarking scene {scene_uuid}")

		async with self.uow:
			await self.gateway.unset_bookmark(scene_uuid, user_id)
		return BookmarkState(bookmarked=False)

	async def get_bookmark_state(self, scene_uuid: UUID, user_id: UUID) -> BookmarkState:
		bookmarked = await self.gateway.is_bookmarked(scene_uuid, user_id)
		return BookmarkState(bookmarked=bookmarked)
