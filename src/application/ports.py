import abc
import asyncio
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Optional, List, BinaryIO
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from fastapi import UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models import ChatRoles
from src.application.character.schemas import CharacterFilterDTO
from src.application.chats.schemas import ChatFilterDTO
from src.application.chats.settings import ChatSettings
from src.application.message.schemas import MessagesFilterDto
from src.application.scene.schemas import SceneFilterDTO
from src.domain.models import User, Scene, Character, Message, Chat, MediaAsset, MediaEntityType
from src.application.media.schemas import MediaAssetDTO, MediaFilterDTO, MediaUploadDTO
from src.application.user.schemas import UserDTO, UserAuthRecord


class Page[T](BaseModel):
	model_config = ConfigDict(frozen=True)

	items: List[T]
	count: int
	offset: int
	limit: int


class LikeState(BaseModel):
	model_config = ConfigDict(frozen=True)

	liked: bool
	likes_count: int


class BookmarkState(BaseModel):
	model_config = ConfigDict(frozen=True)

	bookmarked: bool


class LLMModelType(StrEnum):
	testing_mock = "testing_mock"
	gemini_flash_preview = "gemini-3-flash-preview"
	gemini_pro = "gemini-2.5-pro"
	claude_sonnet = "claude-sonnet-4-20250514"
	claude_haiku = "claude-haiku-4-20250514"
	qwen_plus = "qwen-plus"
	qwen_turbo = "qwen-turbo"
	qwen_max = "qwen-max"
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


class IPasswordHasher(abc.ABC):
	@abc.abstractmethod
	def hash_password(self, password: str) -> str: ...

	@abc.abstractmethod
	def verify_password(self, password: str, password_hash: str) -> bool: ...


class IAuthService(abc.ABC):
	@abc.abstractmethod
	async def authenticate(self, username: str, password: str) -> User: ...


class IUnitOfWork(ABC):
	@abstractmethod
	async def __aenter__(self) -> AsyncSession: ...

	@abstractmethod
	async def __aexit__(self, exc_type, exc_val, exc_tb) -> None: ...


class IAuthorizationService(abc.ABC):
	@abc.abstractmethod
	def visible_to(self, *, is_public: bool, owner_id: UUID | None, actor_id: UUID | None) -> bool: ...

	@abc.abstractmethod
	def require_visible(self, *, is_public: bool, owner_id: UUID | None, actor_id: UUID | None, noun: str) -> None: ...

	@abc.abstractmethod
	def require_owned(self, *, owner_id: UUID | None, actor_id: UUID, noun: str) -> None: ...


class IVisibilityGateway(abc.ABC):
	@abc.abstractmethod
	def public_or_owned(
		self,
		is_public_col: ColumnElement[bool],
		owner_col: ColumnElement[UUID],
		actor_id: UUID | None,
	) -> ColumnElement[bool]: ...


class IUserService(abc.ABC):
	@abc.abstractmethod
	async def find_users_by_dto(self, user_filters_dto: UserDTO) -> Page[User]: ...

	@abc.abstractmethod
	async def create_user(self, user: User) -> User: ...

	@abc.abstractmethod
	async def delete_user(self, user_id: UUID, actor_id: UUID) -> None: ...


class IUserGateway(abc.ABC):
	@abc.abstractmethod
	async def find_users_by_filters(self, filters: UserDTO, offset: int = 0, limit: int = 10) -> Page[User]: ...

	@abc.abstractmethod
	async def create_user(self, user: User) -> User: ...

	@abc.abstractmethod
	async def delete_user(self, user_id: UUID) -> None: ...

	@abc.abstractmethod
	async def get_user_by_id(self, user_id: UUID) -> Optional[User]: ...

	@abc.abstractmethod
	async def get_user_auth(self, username: str) -> Optional[UserAuthRecord]: ...


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
	async def send_message(self, chat_dto: UserMessageDTO, actor_id: UUID) -> Message: ...


class IPromptService(abc.ABC):
	@abc.abstractmethod
	def build_system_prompt(
		self, scene: Scene | None, characters: list[Character], user_character: Character | None = None
	) -> str: ...


class ICharacterService(abc.ABC):
	@abc.abstractmethod
	async def create_character(self, character: Character) -> UUID: ...

	@abc.abstractmethod
	async def get_one(self, character_uuid: UUID, actor_id: UUID | None) -> Character: ...

	@abc.abstractmethod
	async def search(self, dto: CharacterFilterDTO, actor_id: UUID | None) -> Page[Character]: ...

	@abc.abstractmethod
	async def get_for_scene(self, scene_id: UUID, actor_id: UUID) -> list[Character]: ...

	@abc.abstractmethod
	async def delete(self, scene_uuid: UUID, actor_id: UUID): ...

	@abc.abstractmethod
	async def update(self, target_scene_uuid: UUID, new_scene_data: Character, actor_id: UUID): ...

	@abc.abstractmethod
	async def like(self, character_uuid: UUID, user_id: UUID) -> LikeState: ...

	@abc.abstractmethod
	async def unlike(self, character_uuid: UUID, user_id: UUID) -> LikeState: ...

	@abc.abstractmethod
	async def get_like_state(self, character_uuid: UUID, user_id: UUID) -> LikeState: ...

	@abc.abstractmethod
	async def bookmark(self, character_uuid: UUID, user_id: UUID) -> BookmarkState: ...

	@abc.abstractmethod
	async def unbookmark(self, character_uuid: UUID, user_id: UUID) -> BookmarkState: ...

	@abc.abstractmethod
	async def get_bookmark_state(self, character_uuid: UUID, user_id: UUID) -> BookmarkState: ...


class ISceneService(abc.ABC):
	@abc.abstractmethod
	async def create_scene(self, scene: Scene) -> UUID: ...

	@abc.abstractmethod
	async def get_one(self, scene_uuid: UUID, actor_id: UUID | None) -> Scene: ...

	@abc.abstractmethod
	async def search(self, dto: SceneFilterDTO, actor_id: UUID | None) -> Page[Scene]: ...

	@abc.abstractmethod
	async def delete(self, scene_uuid: UUID, actor_id: UUID): ...

	@abc.abstractmethod
	async def update(self, target_scene_uuid: UUID, new_scene_data: Scene, actor_id: UUID): ...

	@abc.abstractmethod
	async def like(self, scene_uuid: UUID, user_id: UUID) -> LikeState: ...

	@abc.abstractmethod
	async def unlike(self, scene_uuid: UUID, user_id: UUID) -> LikeState: ...

	@abc.abstractmethod
	async def get_like_state(self, scene_uuid: UUID, user_id: UUID) -> LikeState: ...

	@abc.abstractmethod
	async def bookmark(self, scene_uuid: UUID, user_id: UUID) -> BookmarkState: ...

	@abc.abstractmethod
	async def unbookmark(self, scene_uuid: UUID, user_id: UUID) -> BookmarkState: ...

	@abc.abstractmethod
	async def get_bookmark_state(self, scene_uuid: UUID, user_id: UUID) -> BookmarkState: ...

	@abc.abstractmethod
	async def attach_characters(self, scene_uuid: UUID, character_ids: list[UUID]) -> None: ...


class ISceneGateway(abc.ABC):
	@abc.abstractmethod
	async def create(self, scene: Scene) -> UUID: ...

	@abc.abstractmethod
	async def get_one(self, uuid: UUID) -> Scene: ...

	@abc.abstractmethod
	async def search(self, dto: SceneFilterDTO, actor_id: UUID | None = None) -> Page[Scene]: ...

	@abc.abstractmethod
	async def delete(self, uuid: UUID): ...

	@abc.abstractmethod
	async def update(self, target_scene_uuid: UUID, new_scene_data: Scene): ...

	@abc.abstractmethod
	async def set_like(self, scene_id: UUID, user_id: UUID) -> None: ...

	@abc.abstractmethod
	async def unset_like(self, scene_id: UUID, user_id: UUID) -> None: ...

	@abc.abstractmethod
	async def is_liked(self, scene_id: UUID, user_id: UUID) -> bool: ...

	@abc.abstractmethod
	async def count_likes(self, scene_id: UUID) -> int: ...

	@abc.abstractmethod
	async def set_bookmark(self, scene_id: UUID, user_id: UUID) -> None: ...

	@abc.abstractmethod
	async def unset_bookmark(self, scene_id: UUID, user_id: UUID) -> None: ...

	@abc.abstractmethod
	async def is_bookmarked(self, scene_id: UUID, user_id: UUID) -> bool: ...

	@abc.abstractmethod
	async def attach_characters(self, scene_id: UUID, character_ids: list[UUID]) -> None: ...


class ICharacterGateway(abc.ABC):
	@abc.abstractmethod
	async def create(self, character: Character) -> UUID: ...

	@abc.abstractmethod
	async def get_one(self, character_uuid: UUID) -> Character: ...

	@abc.abstractmethod
	async def get_for_scene(self, scene_id: UUID) -> list[Character]: ...

	@abc.abstractmethod
	async def search(self, dto: CharacterFilterDTO, actor_id: UUID | None = None) -> Page[Character]: ...

	@abc.abstractmethod
	async def delete(self, scene_uuid: UUID): ...

	@abc.abstractmethod
	async def update(self, target_scene_uuid: UUID, new_character_data: Character): ...

	@abc.abstractmethod
	async def set_like(self, character_id: UUID, user_id: UUID) -> None: ...

	@abc.abstractmethod
	async def unset_like(self, character_id: UUID, user_id: UUID) -> None: ...

	@abc.abstractmethod
	async def is_liked(self, character_id: UUID, user_id: UUID) -> bool: ...

	@abc.abstractmethod
	async def count_likes(self, character_id: UUID) -> int: ...

	@abc.abstractmethod
	async def set_bookmark(self, character_id: UUID, user_id: UUID) -> None: ...

	@abc.abstractmethod
	async def unset_bookmark(self, character_id: UUID, user_id: UUID) -> None: ...

	@abc.abstractmethod
	async def is_bookmarked(self, character_id: UUID, user_id: UUID) -> bool: ...


class IChatGateway(abc.ABC):
	@abc.abstractmethod
	async def create(self, chat: Chat) -> UUID: ...

	@abc.abstractmethod
	async def get_one(self, chat_uuid: UUID) -> Chat: ...

	@abc.abstractmethod
	async def search(self, dto: ChatFilterDTO, actor_id: UUID | None = None) -> Page[Chat]: ...

	@abc.abstractmethod
	async def delete(self, chat_uuid: UUID) -> UUID: ...

	@abc.abstractmethod
	async def update(self, target_chat_uuid: UUID, chat_name: str) -> UUID: ...

	@abc.abstractmethod
	async def set_persona(self, chat_uuid: UUID, user_character_id: UUID) -> UUID: ...


class IChatService(abc.ABC):
	@abc.abstractmethod
	async def start_chat(self, chat: Chat) -> UUID: ...

	@abc.abstractmethod
	async def get_one(self, chat_uuid: UUID, actor_id: UUID) -> Chat: ...

	@abc.abstractmethod
	async def search(self, dto: ChatFilterDTO, actor_id: UUID) -> Page[Chat]: ...

	@abc.abstractmethod
	async def delete(self, chat_uuid: UUID, actor_id: UUID) -> UUID: ...

	@abc.abstractmethod
	async def update(self, target_chat_uuid: UUID, chat_name: str, actor_id: UUID) -> UUID: ...

	@abc.abstractmethod
	async def set_persona(self, chat_uuid: UUID, user_character_id: UUID, actor_id: UUID) -> UUID: ...


class IChatSettingsGateway(abc.ABC):
	@abc.abstractmethod
	async def get_for_chat(self, chat_id: UUID) -> Optional[ChatSettings]: ...

	@abc.abstractmethod
	async def upsert(self, chat_id: UUID, settings: ChatSettings) -> ChatSettings: ...


class IChatSettingsService(abc.ABC):
	@abc.abstractmethod
	async def get_for_chat(self, chat_id: UUID) -> Optional[ChatSettings]: ...

	@abc.abstractmethod
	async def upsert(self, chat_id: UUID, settings: ChatSettings) -> ChatSettings: ...


class IMessageGateway(abc.ABC):
	@abc.abstractmethod
	async def create(self, message: Message) -> Message: ...

	@abc.abstractmethod
	async def search(self, dto: MessagesFilterDto, actor_id: UUID | None = None) -> Page[Message]: ...

	@abc.abstractmethod
	async def get_one(self, message_uuid: UUID) -> Message: ...

	@abc.abstractmethod
	async def get_chat_owner_for_message(self, message_uuid: UUID) -> UUID | None: ...

	@abc.abstractmethod
	async def update(self, message_uuid: UUID, updated_text: str) -> UUID: ...

	@abc.abstractmethod
	async def delete(self, message_uuid: UUID) -> UUID: ...

	@abc.abstractmethod
	async def latest_model_message(self, chat_id: UUID) -> Optional[Message]: ...


class IChatEventGateway(abc.ABC):
	@abc.abstractmethod
	def subscribe(self, chat_id: UUID) -> asyncio.Queue: ...

	@abc.abstractmethod
	def unsubscribe(self, chat_id: UUID, queue: asyncio.Queue) -> None: ...

	@abc.abstractmethod
	def publish_message(self, chat_id: UUID, message: Message) -> None: ...


class IServerEventsService(abc.ABC):
	@abc.abstractmethod
	async def open_stream(self, chat_id: UUID, user_id: UUID) -> StreamingResponse: ...


class IMessageService(abc.ABC):
	@abc.abstractmethod
	async def send_message(self, message: Message) -> Message: ...

	@abc.abstractmethod
	async def search(self, dto: MessagesFilterDto, actor_id: UUID) -> Page[Message]: ...

	@abc.abstractmethod
	async def get_one(self, message_uuid: UUID, actor_id: UUID) -> Message: ...

	@abc.abstractmethod
	async def update(self, message_uuid: UUID, updated_text: str, actor_id: UUID) -> UUID: ...

	@abc.abstractmethod
	async def delete(self, message_uuid: UUID, actor_id: UUID) -> UUID: ...

	@abc.abstractmethod
	async def append_model_message(self, result: LLMResult) -> Message: ...

	@abc.abstractmethod
	async def latest_model_message(self, chat_id: UUID) -> Optional[Message]: ...


class UploadedImage(BaseModel):
	model_config = ConfigDict(frozen=True)

	content_type: str
	ext: str
	data: bytes
	size: int


class IImageReader(abc.ABC):
	@abc.abstractmethod
	async def read(self, file: UploadFile) -> UploadedImage: ...


class IObjectStorageGateway(abc.ABC):
	@abc.abstractmethod
	async def ensure_buckets(self) -> None: ...

	@abc.abstractmethod
	async def upload(
		self,
		object_key: str,
		data: BinaryIO,
		length: int,
		content_type: str,
		is_public: bool,
	) -> tuple[str, int]: ...

	@abc.abstractmethod
	async def presigned_get_url(self, bucket: str, object_key: str) -> str: ...

	@abc.abstractmethod
	def public_url(self, bucket: str, object_key: str) -> str: ...

	@abc.abstractmethod
	async def delete_object(self, bucket: str, object_key: str) -> None: ...


class IMediaGateway(abc.ABC):
	@abc.abstractmethod
	async def create(self, asset: MediaAsset) -> MediaAsset: ...

	@abc.abstractmethod
	async def get_one(self, media_id: UUID) -> MediaAsset: ...

	@abc.abstractmethod
	async def get_entity_owner(self, entity_type: MediaEntityType, entity_id: UUID) -> Optional[UUID]: ...

	@abc.abstractmethod
	async def get_for_entity(self, entity_type: MediaEntityType, entity_id: UUID) -> list[MediaAsset]: ...

	@abc.abstractmethod
	async def search(self, dto: MediaFilterDTO, actor_id: Optional[UUID] = None) -> Page[MediaAsset]: ...

	@abc.abstractmethod
	async def delete(self, media_id: UUID) -> None: ...


class IMediaService(abc.ABC):
	@abc.abstractmethod
	async def upload(self, dto: MediaUploadDTO) -> MediaAssetDTO: ...

	@abc.abstractmethod
	async def get_one(self, media_id: UUID, actor_id: Optional[UUID]) -> MediaAssetDTO: ...

	@abc.abstractmethod
	async def search(self, dto: MediaFilterDTO, actor_id: Optional[UUID]) -> Page[MediaAssetDTO]: ...

	@abc.abstractmethod
	async def delete(self, media_id: UUID, actor_id: UUID) -> None: ...


class IGatewayFactory(ABC):
	@abstractmethod
	def create_gateway(self, gateway_type: str) -> ILLMChatGateway:
		pass


class ApiResponse[T](BaseModel):
	model_config = ConfigDict(frozen=True)

	result: T
	correlation_id: Optional[str] = None
