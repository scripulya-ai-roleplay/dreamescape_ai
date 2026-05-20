from uuid import UUID

from pydantic import BaseModel


class SceneFilterDTO(BaseModel):
	ids: list[UUID] | None = None
	title: list[str] | None = None
	owner: list[UUID] | None = None

	# this is not a list of lists, because
	# I'm interested to know what scenes a
	# character is involved in
	characters: list[UUID] | None = None

	offset: int = 0
	limit: int = 50
