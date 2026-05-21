from enum import StrEnum
from typing import TypeVar, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UserRole(StrEnum):
	ADMIN = "admin"
	API = "api"
	DEVELOPER = "developer"


T = TypeVar("T")


class User(BaseModel):
	model_config = ConfigDict(frozen=True)

	id: Optional[UUID] = None
	username: Optional[str] = Field(default=None, min_length=1, max_length=100)
	test_username: Optional[str] = None
	google_id: Optional[str] = None
	role: UserRole
	crystal_balance: int = 1000
	characters: Optional[List["Character"]] = None
	scenes: Optional[List["Scene"]] = None
	chats: Optional[List["Chat"]] = None


class Character(BaseModel):
	model_config = ConfigDict(frozen=True)

	id: Optional[UUID] = None
	owner_id: Optional[UUID] = None
	name: str
	system_prompt: str
	is_public: bool = False


class Scene(BaseModel):
	model_config = ConfigDict(frozen=True)

	id: Optional[UUID] = None
	description: str | None = None
	owner_id: UUID  # Required - scenes must have an owner
	title: str
	background_prompt: str


class Chat(BaseModel):
	model_config = ConfigDict(frozen=True)

	id: Optional[UUID] = None
	user_id: Optional[UUID] = None
	character_id: Optional[UUID] = None
	scene_id: Optional[UUID] = None
