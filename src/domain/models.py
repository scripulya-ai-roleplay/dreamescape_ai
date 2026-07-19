from datetime import datetime
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


class MessageStatus(StrEnum):
	"""Lifecycle of a message. Model messages are persisted as PENDING while the
	LLM is generating, then flipped to COMPLETED/FAILED when scripulya_agent replies.
	User messages are always COMPLETED."""

	PENDING = "pending"
	COMPLETED = "completed"
	FAILED = "failed"


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
	is_public: bool = False
	chats_count: int = 0
	messages_count: int = 0


class Chat(BaseModel):
	model_config = ConfigDict(frozen=True)

	id: None | UUID = None
	title: str
	user_id: UUID
	scene_id: UUID
	user_character_id: None | UUID = None


class Message(BaseModel):
	model_config = ConfigDict(frozen=True)
	id: None | UUID = None
	message: str
	chat_id: UUID
	role: ChatRoles
	status: MessageStatus = MessageStatus.COMPLETED
	date_created: None | datetime = None
	date_edited: None | datetime = None


class MediaEntityType(StrEnum):
	CHARACTER = "character"
	SCENE = "scene"
	USER = "user"


class MediaAsset(BaseModel):
	model_config = ConfigDict(frozen=True)

	id: None | UUID = None
	object_key: None | str = None
	bucket: None | str = None
	file_url: None | str = None
	content_type: str
	size_bytes: int = 0
	entity_type: MediaEntityType
	entity_id: UUID
	is_public: bool = False
	owner_id: None | UUID = None
	created_at: None | datetime = None
