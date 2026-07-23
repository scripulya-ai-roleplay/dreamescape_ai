import abc
from uuid import UUID

from src.application.ports.common import Page, LikeState, BookmarkState
from src.application.scene.schemas import SceneFilterDTO
from src.domain.models import Scene


class ISceneService(abc.ABC):
	@abc.abstractmethod
	async def create_scene(self, scene: Scene) -> UUID: ...

	@abc.abstractmethod
	async def get_one(self, scene_uuid: UUID, actor_id: UUID | None) -> Scene: ...

	@abc.abstractmethod
	async def search(self, dto: SceneFilterDTO, actor_id: UUID | None) -> Page[Scene]: ...

	@abc.abstractmethod
	async def delete(self, scene_uuid: UUID, actor_id: UUID): ...

	@abc.abstractmethod
	async def update(self, target_scene_uuid: UUID, new_scene_data: Scene, actor_id: UUID): ...

	@abc.abstractmethod
	async def like(self, scene_uuid: UUID, user_id: UUID) -> LikeState: ...

	@abc.abstractmethod
	async def unlike(self, scene_uuid: UUID, user_id: UUID) -> LikeState: ...

	@abc.abstractmethod
	async def get_like_state(self, scene_uuid: UUID, user_id: UUID) -> LikeState: ...

	@abc.abstractmethod
	async def bookmark(self, scene_uuid: UUID, user_id: UUID) -> BookmarkState: ...

	@abc.abstractmethod
	async def unbookmark(self, scene_uuid: UUID, user_id: UUID) -> BookmarkState: ...

	@abc.abstractmethod
	async def get_bookmark_state(self, scene_uuid: UUID, user_id: UUID) -> BookmarkState: ...

	@abc.abstractmethod
	async def attach_characters(self, scene_uuid: UUID, character_ids: list[UUID]) -> None: ...


class ISceneGateway(abc.ABC):
	@abc.abstractmethod
	async def create(self, scene: Scene) -> UUID: ...

	@abc.abstractmethod
	async def get_one(self, uuid: UUID) -> Scene: ...

	@abc.abstractmethod
	async def search(self, dto: SceneFilterDTO, actor_id: UUID | None = None) -> Page[Scene]: ...

	@abc.abstractmethod
	async def delete(self, uuid: UUID): ...

	@abc.abstractmethod
	async def update(self, target_scene_uuid: UUID, new_scene_data: Scene): ...

	@abc.abstractmethod
	async def set_like(self, scene_id: UUID, user_id: UUID) -> None: ...

	@abc.abstractmethod
	async def unset_like(self, scene_id: UUID, user_id: UUID) -> None: ...

	@abc.abstractmethod
	async def is_liked(self, scene_id: UUID, user_id: UUID) -> bool: ...

	@abc.abstractmethod
	async def count_likes(self, scene_id: UUID) -> int: ...

	@abc.abstractmethod
	async def set_bookmark(self, scene_id: UUID, user_id: UUID) -> None: ...

	@abc.abstractmethod
	async def unset_bookmark(self, scene_id: UUID, user_id: UUID) -> None: ...

	@abc.abstractmethod
	async def is_bookmarked(self, scene_id: UUID, user_id: UUID) -> bool: ...

	@abc.abstractmethod
	async def attach_characters(self, scene_id: UUID, character_ids: list[UUID]) -> None: ...
