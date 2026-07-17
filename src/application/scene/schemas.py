from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class SceneSortBy(StrEnum):
	"""Field to order scene search results by."""

	title = "title"
	# aggregate counts over a scene's chats / messages
	chats_count = "chats_count"
	messages_count = "messages_count"


class SortOrder(StrEnum):
	asc = "asc"
	desc = "desc"


class SceneFilterDTO(BaseModel):
	ids: list[UUID] | None = None
	# exact-match filter (SQL IN)
	title: list[str] | None = None
	# case-insensitive substring search on title (SQL ILIKE)
	title_search: str | None = None
	owner: list[UUID] | None = None

	# this is not a list of lists, because
	# I'm interested to know what scenes a
	# character is involved in
	characters: list[UUID] | None = None

	# sorting (only applied when sort_by is set)
	sort_by: SceneSortBy | None = None
	sort_order: SortOrder = SortOrder.asc

	offset: int = Field(default=0, ge=0)
	limit: int = Field(default=50, ge=0)


class AttachCharactersDTO(BaseModel):
	"""Character ids to add to a scene's roster after it exists (e.g. mid-chat)."""

	character_ids: list[UUID] = Field(min_length=1)
