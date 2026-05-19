from typing import List
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.domain.models import UserRole


class UserDTO(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    user_id: UUID | None = None
    username: str | None = None
    test_username: str | None = None
    google_id: str | None = None
    role: UserRole | None = None

    limit: int | None = Field(default=10, ge=0)
    offset: int | None = Field(default=0, ge=0)
