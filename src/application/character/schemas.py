from uuid import UUID

from pydantic import BaseModel, Field


class CharacterFilterDTO(BaseModel):
	ids: list[UUID] | None = None
	owner_ids: list[UUID] | None = None
	names: list[str] | None = None
	bookmarked_by: list[UUID] | None = None

	limit: int = Field(default=50, ge=0)
	offset: int = Field(default=0, ge=0)
