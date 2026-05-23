from uuid import UUID

from pydantic import BaseModel, Field

from src.domain.models import ChatRoles


class MessagesFilterDto(BaseModel):
	ids: None | list[UUID] = None
	chats_ids: None | list[UUID] = None
	roles: None | list[ChatRoles] = None

	limit: int = Field(default=50, ge=0)
	offset: int = Field(default=0, ge=0)
