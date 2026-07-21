from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.domain.models import UserRole


class LoginRequest(BaseModel):
	username: str = Field(min_length=1, max_length=100)
	password: str = Field(min_length=1, max_length=1024)


class Token(BaseModel):
	access_token: str
	token_type: str = "bearer"


# Separate from the domain User on purpose: User is serialized in /users/search,
# so the password hash must not ride on it. This carries only what auth needs.
class UserAuthRecord(BaseModel):
	model_config = ConfigDict(frozen=True)

	id: UUID
	username: str
	role: UserRole
	password_hash: str | None
