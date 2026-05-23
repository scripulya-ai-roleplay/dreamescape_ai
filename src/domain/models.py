from enum import StrEnum
from typing import TypeVar, List
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UserRole(StrEnum):
	ADMIN = "admin"
	API = "api"
	DEVELOPER = "developer"


class ChatRoles(StrEnum):
	USER = "user"
	MODEL = "model"


T = TypeVar("T")


class User(BaseModel):
	model_config = ConfigDict(frozen=True)

	id: None | UUID = None
	username: None | str = Field(default=None, min_length=1, max_length=100)
	test_username: None | str = None
	google_id: None | str = None
	role: UserRole
	crystal_balance: int = 1000
	characters: None | List["Character"] = None
	scenes: None | List["Scene"] = None
	chats: None | List["Chat"] = None


class Character(BaseModel):
	model_config = ConfigDict(frozen=True)

	id: None | UUID = None
	owner_id: None | UUID = None
	name: str = Field(min_length=1, max_length=254)
	system_prompt: str
	is_public: bool = False


class Scene(BaseModel):
	model_config = ConfigDict(frozen=True)

	id: None | UUID = None
	description: str | None = None
	owner_id: UUID  # Required - scenes must have an owner
	title: str
	background_prompt: str
	initial_message_text: str


class Chat(BaseModel):
	model_config = ConfigDict(frozen=True)

	id: None | UUID = None
	title: str
	user_id: UUID
	scene_id: UUID


class Message(BaseModel):
	model_config = ConfigDict(frozen=True)

	# chat id is optional, because it is being generated automatically inside DB
	# message length is not verified because an empty message can mean that user
	# choose a 'continue' behaviour
	id: None | UUID = None
	message: str
	chat_id: UUID
	role: ChatRoles
