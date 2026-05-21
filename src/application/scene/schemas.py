from uuid import UUID

from pydantic import BaseModel, Field


class SceneFilterDTO(BaseModel):
	ids: list[UUID] | None = None
	title: list[str] | None = None
	owner: list[UUID] | None = None

	# this is not a list of lists, because
	# I'm interested to know what scenes a
	# character is involved in
	characters: list[UUID] | None = None

	offset: int = Field(default=0, ge=0)
	limit: int = Field(default=50, ge=0)
