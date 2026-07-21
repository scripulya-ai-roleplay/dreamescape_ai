from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.domain.models import UserRole


class UserDTO(BaseModel):
	model_config = ConfigDict(frozen=True, extra="forbid")

	user_ids: list[UUID] | None = None
	usernames: list[str] | None = None
	google_ids: list[str] | None = None
	roles: list[UserRole] | None = None

	limit: int | None = Field(default=10, ge=0)
	offset: int | None = Field(default=0, ge=0)


class UserAuthRecord(BaseModel):
	model_config = ConfigDict(frozen=True)

	id: UUID
	username: str
	role: UserRole
	password_hash: str | None
