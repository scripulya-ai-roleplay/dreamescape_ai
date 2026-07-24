import abc
from uuid import UUID

from src.application.character.schemas import CharacterFilterDTO
from src.application.ports.common import BookmarkState, LikeState, Page
from src.domain.models import Character


class ICharacterService(abc.ABC):
	@abc.abstractmethod
	async def create_character(self, character: Character) -> UUID: ...

	@abc.abstractmethod
	async def get_one(self, character_uuid: UUID, actor_id: UUID | None) -> Character: ...

	@abc.abstractmethod
	async def search(self, dto: CharacterFilterDTO, actor_id: UUID | None) -> Page[Character]: ...

	@abc.abstractmethod
	async def get_for_scene(self, scene_id: UUID, actor_id: UUID) -> list[Character]: ...

	@abc.abstractmethod
	async def delete(self, scene_uuid: UUID, actor_id: UUID): ...

	@abc.abstractmethod
	async def update(self, target_scene_uuid: UUID, new_scene_data: Character, actor_id: UUID): ...

	@abc.abstractmethod
	async def like(self, character_uuid: UUID, user_id: UUID) -> LikeState: ...

	@abc.abstractmethod
	async def unlike(self, character_uuid: UUID, user_id: UUID) -> LikeState: ...

	@abc.abstractmethod
	async def get_like_state(self, character_uuid: UUID, user_id: UUID) -> LikeState: ...

	@abc.abstractmethod
	async def bookmark(self, character_uuid: UUID, user_id: UUID) -> BookmarkState: ...

	@abc.abstractmethod
	async def unbookmark(self, character_uuid: UUID, user_id: UUID) -> BookmarkState: ...

	@abc.abstractmethod
	async def get_bookmark_state(self, character_uuid: UUID, user_id: UUID) -> BookmarkState: ...


class ICharacterGateway(abc.ABC):
	@abc.abstractmethod
	async def create(self, character: Character) -> UUID: ...

	@abc.abstractmethod
	async def get_one(self, character_uuid: UUID) -> Character: ...

	@abc.abstractmethod
	async def get_for_scene(self, scene_id: UUID) -> list[Character]: ...

	@abc.abstractmethod
	async def search(self, dto: CharacterFilterDTO, actor_id: UUID | None = None) -> Page[Character]: ...

	@abc.abstractmethod
	async def delete(self, scene_uuid: UUID): ...

	@abc.abstractmethod
	async def update(self, target_scene_uuid: UUID, new_character_data: Character): ...

	@abc.abstractmethod
	async def set_like(self, character_id: UUID, user_id: UUID) -> None: ...

	@abc.abstractmethod
	async def unset_like(self, character_id: UUID, user_id: UUID) -> None: ...

	@abc.abstractmethod
	async def is_liked(self, character_id: UUID, user_id: UUID) -> bool: ...

	@abc.abstractmethod
	async def count_likes(self, character_id: UUID) -> int: ...

	@abc.abstractmethod
	async def set_bookmark(self, character_id: UUID, user_id: UUID) -> None: ...

	@abc.abstractmethod
	async def unset_bookmark(self, character_id: UUID, user_id: UUID) -> None: ...

	@abc.abstractmethod
	async def is_bookmarked(self, character_id: UUID, user_id: UUID) -> bool: ...
