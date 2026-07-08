import abc
import asyncio
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Optional, List, BinaryIO
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from fastapi import UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models import ChatRoles
from src.application.character.schemas import CharacterFilterDTO
from src.application.chats.schemas import ChatFilterDTO
from src.application.chats.settings import ChatSettings
from src.application.message.schemas import MessagesFilterDto
from src.application.scene.schemas import SceneFilterDTO
from src.domain.models import User, Scene, Character, Message, Chat, MediaAsset, MediaEntityType
from src.application.media.schemas import MediaAssetDTO, MediaFilterDTO
from src.application.user.schemas import UserDTO


class Page[T](BaseModel):
	model_config = ConfigDict(frozen=True)

	items: List[T]
	count: int
	offset: int
	limit: int


class LLMModelType(StrEnum):
	testing_mock = "testing_mock"
	# Google
	gemini_flash_preview = "gemini-3-flash-preview"
	gemini_pro = "gemini-2.5-pro"
	# Anthropic
	claude_sonnet = "claude-sonnet-4-20250514"
	claude_haiku = "claude-haiku-4-20250514"
	# Qwen
	qwen_plus = "qwen-plus"
	qwen_turbo = "qwen-turbo"
	qwen_max = "qwen-max"
	# Z.ai (GLM, OpenAI-compatible)
	glm_5_2 = "glm-5.2"
	glm_4_6 = "glm-4.6"
	glm_4_5 = "glm-4.5"


class LLMResponse(BaseModel):
	text: str
	model: LLMModelType
	usage: Optional[dict] = None
	provider: str


class IJWTService(abc.ABC):
	@abc.abstractmethod
	def create_token(self, user: User) -> str: ...

	@abc.abstractmethod
	def verify_token(self, token: str) -> User: ...


class IUnitOfWork(ABC):
	@abstractmethod
	async def __aenter__(self) -> AsyncSession: ...

	@abstractmethod
	async def __aexit__(self, exc_type, exc_val, exc_tb) -> None: ...


class IUserService(abc.ABC):
	@abc.abstractmethod
	async def find_users_by_dto(self, user_filters_dto: UserDTO) -> Page[User]: ...

	@abc.abstractmethod
	async def create_user(self, user: User) -> User: ...

	@abc.abstractmethod
	async def delete_user(self, user_id: UUID) -> None: ...


class IUserGateway(abc.ABC):
	@abc.abstractmethod
	async def find_users_by_filters(self, filters: UserDTO, offset: int = 0, limit: int = 10) -> Page[User]: ...

	@abc.abstractmethod
	async def create_user(self, user: User) -> User: ...

	@abc.abstractmethod
	async def delete_user(self, user_id: UUID) -> None: ...

	@abc.abstractmethod
	async def get_user_by_id(self, user_id: UUID) -> Optional[User]: ...


class UserMessageDTO(BaseModel):
	chat_id: UUID
	message: str
	llm_model: LLMModelType | None = LLMModelType.testing_mock
	role: ChatRoles


class LLMRequest(BaseModel):
	message: UserMessageDTO
	history: list[UserMessageDTO] = []
	chat_settings: ChatSettings | None = None
	system_prompt: str = ""


class LLMErrorResponse(BaseModel):
	error_code: str  # machine-readable snake_case, e.g. "model_is_inaccessible"
	status: int  # HTTP-style status, e.g. 503
	reason: str  # short human-readable reason phrase
	message: str  # detailed message
	provider: str | None = None
	details: dict = {}


class LLMResult(BaseModel):
	chat_id: UUID
	message: UserMessageDTO | None = None  # the model's reply (role=MODEL) on success
	error: LLMErrorResponse | None = None  # set on failure


class ILLMChatGateway(abc.ABC):
	@abc.abstractmethod
	async def submit(
		self,
		message: UserMessageDTO,
		history: list[UserMessageDTO],
		chat_settings: ChatSettings | None = None,
		system_prompt: str = "",
	) -> Optional[LLMResponse]: ...


class IScripulyaAgentClient(abc.ABC):
	@abc.abstractmethod
	async def publish(self, req: LLMRequest) -> None: ...


class IChatsService(abc.ABC):
	@abc.abstractmethod
	async def send_message(self, chat_dto: UserMessageDTO) -> Message: ...


class IPromptService(abc.ABC):
	@abc.abstractmethod
	def build_system_prompt(self, scene: Scene | None, characters: list[Character]) -> str: ...


class ICharacterService(abc.ABC):
	@abc.abstractmethod
	async def create_character(self, character: Character) -> UUID: ...

	@abc.abstractmethod
	async def get_one(self, character_uuid: UUID) -> Character: ...

	@abc.abstractmethod
	async def search(self, dto: CharacterFilterDTO) -> Page[Character]: ...

	@abc.abstractmethod
	async def delete(self, scene_uuid: UUID): ...

	@abc.abstractmethod
	async def update(self, target_scene_uuid: UUID, new_scene_data: Character): ...


class ISceneService(abc.ABC):
	@abc.abstractmethod
	async def create_scene(self, scene: Scene) -> UUID: ...

	@abc.abstractmethod
	async def get_one(self, scene_uuid: UUID) -> Scene: ...

	@abc.abstractmethod
	async def search(self, dto: SceneFilterDTO) -> Page[Scene]: ...

	@abc.abstractmethod
	async def delete(self, scene_uuid: UUID): ...

	@abc.abstractmethod
	async def update(self, target_scene_uuid: UUID, new_scene_data: Scene): ...


class ISceneGateway(abc.ABC):
	@abc.abstractmethod
	async def create(self, scene: Scene) -> UUID: ...

	@abc.abstractmethod
	async def get_one(self, uuid: UUID) -> Scene: ...

	@abc.abstractmethod
	async def search(self, dto: SceneFilterDTO) -> Page[Scene]: ...

	@abc.abstractmethod
	async def delete(self, uuid: UUID): ...

	@abc.abstractmethod
	async def update(self, target_scene_uuid: UUID, new_scene_data: Scene): ...


class ICharacterGateway(abc.ABC):
	@abc.abstractmethod
	async def create(self, character: Character) -> UUID: ...

	@abc.abstractmethod
	async def get_one(self, character_uuid: UUID) -> Character: ...

	@abc.abstractmethod
	async def get_for_scene(self, scene_id: UUID) -> list[Character]: ...

	@abc.abstractmethod
	async def search(self, dto: CharacterFilterDTO) -> Page[Character]: ...

	@abc.abstractmethod
	async def delete(self, scene_uuid: UUID): ...

	@abc.abstractmethod
	async def update(self, target_scene_uuid: UUID, new_scene_data: Character): ...


class IChatGateway(abc.ABC):
	@abc.abstractmethod
	async def create(self, chat: Chat) -> UUID: ...

	@abc.abstractmethod
	async def get_one(self, chat_uuid: UUID) -> Chat: ...

	@abc.abstractmethod
	async def search(self, dto: ChatFilterDTO) -> Page[Chat]: ...

	@abc.abstractmethod
	async def delete(self, chat_uuid: UUID) -> UUID: ...

	@abc.abstractmethod
	async def update(self, target_chat_uuid: UUID, chat_name: str) -> UUID: ...


class IChatService(abc.ABC):
	@abc.abstractmethod
	async def start_chat(self, chat: Chat) -> UUID: ...

	@abc.abstractmethod
	async def get_one(self, chat_uuid: UUID) -> Chat: ...

	@abc.abstractmethod
	async def search(self, dto: ChatFilterDTO) -> Page[Chat]: ...

	@abc.abstractmethod
	async def delete(self, chat_uuid: UUID) -> UUID: ...

	@abc.abstractmethod
	async def update(self, target_chat_uuid: UUID, chat_name: str) -> UUID: ...


class IChatSettingsGateway(abc.ABC):
	@abc.abstractmethod
	async def get_for_chat(self, chat_id: UUID) -> Optional[ChatSettings]:
		"""Return the stored ChatSettings for chat_id, or None if none are set."""
		...

	@abc.abstractmethod
	async def upsert(self, chat_id: UUID, settings: ChatSettings) -> ChatSettings:
		"""Insert or replace the ChatSettings row for chat_id."""
		...


class IChatSettingsService(abc.ABC):
	@abc.abstractmethod
	async def get_for_chat(self, chat_id: UUID) -> Optional[ChatSettings]: ...

	@abc.abstractmethod
	async def upsert(self, chat_id: UUID, settings: ChatSettings) -> ChatSettings: ...


class IMessageGateway(abc.ABC):
	@abc.abstractmethod
	async def create(self, message: Message) -> Message: ...

	@abc.abstractmethod
	async def search(self, dto: MessagesFilterDto) -> Page[Message]: ...

	@abc.abstractmethod
	async def get_one(self, message_uuid: UUID) -> Message: ...

	@abc.abstractmethod
	async def update(self, message_uuid: UUID, updated_text: str) -> UUID: ...

	@abc.abstractmethod
	async def delete(self, message_uuid: UUID) -> UUID: ...

	@abc.abstractmethod
	async def latest_model_message(self, chat_id: UUID) -> Optional[Message]:
		"""Return the most recent model message for chat_id (any status), or None."""
		...


class IChatEventGateway(abc.ABC):
	@abc.abstractmethod
	def subscribe(self, chat_id: UUID) -> asyncio.Queue:
		"""Register a listener queue for chat_id events; returns the queue to await."""
		...

	@abc.abstractmethod
	def unsubscribe(self, chat_id: UUID, queue: asyncio.Queue) -> None:
		"""Drop a previously registered listener queue."""
		...

	@abc.abstractmethod
	def publish_message(self, chat_id: UUID, message: Message) -> None:
		"""Fan out a model-message lifecycle event to all listeners for chat_id."""
		...


class IServerEventsService(abc.ABC):
	@abc.abstractmethod
	async def open_stream(self, chat_id: UUID, user_id: UUID) -> StreamingResponse: ...


class IMessageService(abc.ABC):
	@abc.abstractmethod
	async def send_message(self, message: Message) -> Message: ...

	@abc.abstractmethod
	async def search(self, dto: MessagesFilterDto) -> Page[Message]: ...

	@abc.abstractmethod
	async def get_one(self, message_uuid: UUID) -> Message: ...

	@abc.abstractmethod
	async def update(self, message_uuid: UUID, updated_text: str) -> UUID: ...

	@abc.abstractmethod
	async def delete(self, message_uuid: UUID) -> UUID: ...

	@abc.abstractmethod
	async def append_model_message(self, result: LLMResult) -> Message:
		"""Persist the model reply carried by an LLMResult as a fresh message row
		(COMPLETED + text on success, FAILED + the error message on error). Every
		consumed result produces exactly one row and is returned (never None)."""
		...

	@abc.abstractmethod
	async def latest_model_message(self, chat_id: UUID) -> Optional[Message]: ...


class IObjectStorageGateway(abc.ABC):
	"""Abstraction over the object store (MinIO/S3) backing media assets.

	Two hosts are involved: the *data* endpoint (backend -> store, for uploads and
	bucket provisioning) and the *public* endpoint (embedded in the URLs handed to
	clients). Presigned URLs are signed over the public endpoint so clients can
	fetch them directly; the data endpoint is only reachable inside the deploy.
	"""

	@abc.abstractmethod
	async def ensure_buckets(self) -> None:
		"""Idempotently create the public/private buckets and set the public read policy."""
		...

	@abc.abstractmethod
	async def upload(
		self,
		object_key: str,
		data: BinaryIO,
		length: int,
		content_type: str,
		is_public: bool,
	) -> tuple[str, int]:
		"""Store ``length`` bytes from ``data`` under ``object_key`` in the public
		or private bucket (per ``is_public``). Returns ``(bucket, size_bytes)``."""
		...

	@abc.abstractmethod
	async def presigned_get_url(self, bucket: str, object_key: str) -> str:
		"""A short-lived presigned GET URL for an object (signed over the public endpoint)."""
		...

	@abc.abstractmethod
	def public_url(self, bucket: str, object_key: str) -> str:
		"""A stable, anonymous URL for an object in the public bucket."""
		...

	@abc.abstractmethod
	async def delete_object(self, bucket: str, object_key: str) -> None:
		"""Remove an object from the store."""
		...


class IMediaGateway(abc.ABC):
	@abc.abstractmethod
	async def create(self, asset: MediaAsset) -> MediaAsset: ...

	@abc.abstractmethod
	async def get_one(self, media_id: UUID) -> MediaAsset: ...

	@abc.abstractmethod
	async def get_for_entity(self, entity_type: MediaEntityType, entity_id: UUID) -> list[MediaAsset]: ...

	@abc.abstractmethod
	async def search(self, dto: MediaFilterDTO, actor_id: Optional[UUID] = None) -> Page[MediaAsset]:
		"""Page through media assets matching ``dto``.

		When ``actor_id`` is given, only public assets and the actor's own private
		assets are returned (``is_public OR owner_id = actor``); when ``None``,
		only public assets. Applied in SQL so pagination counts stay correct.
		"""
		...

	@abc.abstractmethod
	async def delete(self, media_id: UUID) -> None: ...


class IMediaService(abc.ABC):
	@abc.abstractmethod
	async def upload(
		self,
		file: UploadFile,
		entity_type: MediaEntityType,
		entity_id: UUID,
		is_public: bool,
		owner_id: UUID,
	) -> MediaAssetDTO: ...

	@abc.abstractmethod
	async def get_one(self, media_id: UUID, actor_id: Optional[UUID]) -> MediaAssetDTO:
		"""Return a media asset as a DTO with a consumable ``url``.

		``actor_id`` is the requesting user (``None`` for an anonymous request).
		Public assets are returned to anyone; private assets require
		``actor_id == owner_id`` (401 if anonymous, 403 otherwise).
		"""
		...

	@abc.abstractmethod
	async def search(self, dto: MediaFilterDTO, actor_id: Optional[UUID]) -> Page[MediaAssetDTO]:
		"""List assets matching ``dto``. Private assets belonging to other users
		are excluded; ``actor_id`` is the requesting user (``None`` = anonymous)."""
		...

	@abc.abstractmethod
	async def delete(self, media_id: UUID, actor_id: UUID) -> None:
		"""Delete a media asset. Only the owner (``actor_id == owner_id``) may delete (403)."""
		...


class IGatewayFactory(ABC):
	@abstractmethod
	def create_gateway(self, gateway_type: str) -> ILLMChatGateway:
		pass


class ApiResponse[T](BaseModel):
	model_config = ConfigDict(frozen=True)

	result: T
	correlation_id: Optional[str] = None
