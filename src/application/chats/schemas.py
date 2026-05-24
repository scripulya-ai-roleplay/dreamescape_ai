from uuid import UUID

from pydantic import BaseModel, Field


class ChatFilterDTO(BaseModel):
	ids: None | list[UUID] = None
	titles: None | list[str] = None
	user_ids: None | list[UUID] = None
	scene_ids: None | list[UUID] = None

	limit: int = Field(default=50, ge=0)
	offset: int = Field(default=0, ge=0)
