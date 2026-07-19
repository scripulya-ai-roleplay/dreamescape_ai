from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class SceneSortBy(StrEnum):
	title = "title"
	chats_count = "chats_count"
	messages_count = "messages_count"


class SortOrder(StrEnum):
	asc = "asc"
	desc = "desc"


class SceneFilterDTO(BaseModel):
	ids: list[UUID] | None = None
	title: list[str] | None = None
	title_search: str | None = None
	owner: list[UUID] | None = None

	characters: list[UUID] | None = None

	sort_by: SceneSortBy | None = None
	sort_order: SortOrder = SortOrder.asc

	offset: int = Field(default=0, ge=0)
	limit: int = Field(default=50, ge=0)


class AttachCharactersDTO(BaseModel):
	character_ids: list[UUID] = Field(min_length=1)
