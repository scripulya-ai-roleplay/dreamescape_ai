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
from src.application.user.schemas import UserDTO


class Page[T](BaseModel):
	model_config = ConfigDict(frozen=True)

	items: List[T]
	count: int
	offset: int
	limit: int


class LikeState(BaseModel):
	"""Like state of an entity for the requesting user plus its total like count."""

	model_config = ConfigDict(frozen=True)

	liked: bool
	likes_count: int


class BookmarkState(BaseModel):
	"""Whether the requesting user has bookmarked an entity."""

	model_config = ConfigDict(frozen=True)

	bookmarked: bool


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


class IAuthorizationService(abc.ABC):
	"""Decides access to owned resources. The single seam a future RBAC or
	permissions service replaces — application code depends on this interface,
	never on the rule itself."""

	@abc.abstractmethod
	def visible_to(self, *, is_public: bool, owner_id: UUID | None, actor_id: UUID | None) -> bool:
		"""Whether a public/owner resource is readable by ``actor_id`` (None = anonymous)."""
		...

	@abc.abstractmethod
	def require_visible(self, *, is_public: bool, owner_id: UUID | None, actor_id: UUID | None, noun: str) -> None:
		"""Enforce read visibility. Raises 401 for an anonymous private request, 403 for any other non-owner."""
		...

	@abc.abstractmethod
	def require_owned(self, *, owner_id: UUID | None, actor_id: UUID, noun: str) -> None:
		"""Enforce ownership for a mutation or an always-private resource. Raises 403 unless owner."""
		...


class IVisibilityGateway(abc.ABC):
	"""Builds the SQL row-visibility predicate for a public/owner table. Swapping
	this (e.g. for a join against a permissions table) changes DB-level filtering
	without touching the gateways that consume it."""

	@abc.abstractmethod
	def public_or_owned(
		self,
		is_public_col: ColumnElement[bool],
		owner_col: ColumnElement[UUID],
		actor_id: UUID | None,
	) -> ColumnElement[bool]:
		"""Predicate matching public rows plus the actor's own private rows.

		``actor_id=None`` (anonymous) matches public rows only."""
		...


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
	async def send_message(self, chat_dto: UserMessageDTO, actor_id: UUID) -> Message:
		"""Generate a model reply in the chat named by ``chat_dto.chat_id``.

		Authorization is enforced here, not by the caller: the chat must belong to
		``actor_id`` (403 otherwise)."""
		...


class IPromptService(abc.ABC):
	@abc.abstractmethod
	def build_system_prompt(
		self, scene: Scene | None, characters: list[Character], user_character: Character | None = None
	) -> str: ...


class ICharacterService(abc.ABC):
	@abc.abstractmethod
	async def create_character(self, character: Character) -> UUID: ...

	@abc.abstractmethod
	async def get_one(self, character_uuid: UUID, actor_id: UUID | None) -> Character:
		"""Fetch one character. Public characters are returned to anyone (``actor_id``
		may be ``None`` for an anonymous request); a private character requires
		``actor_id == owner_id`` (401 if anonymous, 403 otherwise)."""
		...

	@abc.abstractmethod
	async def search(self, dto: CharacterFilterDTO, actor_id: UUID | None) -> Page[Character]:
		"""Page characters. Anonymous (``actor_id=None``) sees public only; an
		authenticated actor sees public plus their own private characters."""
		...

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
	async def get_one(self, scene_uuid: UUID, actor_id: UUID | None) -> Scene:
		"""Fetch one scene. Public scenes are returned to anyone (``actor_id`` may
		be ``None`` for an anonymous request); a private scene requires
		``actor_id == owner_id`` (401 if anonymous, 403 otherwise)."""
		...

	@abc.abstractmethod
	async def search(self, dto: SceneFilterDTO, actor_id: UUID | None) -> Page[Scene]:
		"""Page scenes. Anonymous (``actor_id=None``) sees public only; an
		authenticated actor sees public plus their own private scenes."""
		...

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
	async def search(self, dto: SceneFilterDTO, actor_id: UUID | None = None) -> Page[Scene]:
		"""Page scenes. ``actor_id=None`` returns public scenes only; an
		authenticated actor also sees their own private ones (applied in SQL)."""
		...

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
	async def search(self, dto: CharacterFilterDTO, actor_id: UUID | None = None) -> Page[Character]:
		"""Page characters. ``actor_id=None`` returns public characters only; an
		authenticated actor also sees their own private ones (applied in SQL)."""
		...

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
	async def search(self, dto: ChatFilterDTO, actor_id: UUID | None = None) -> Page[Chat]:
		"""Page chats. Chats have no public visibility, so only the actor's own
		chats are returned; ``actor_id=None`` matches nothing (fail-closed)."""
		...

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
	async def get_one(self, chat_uuid: UUID, actor_id: UUID) -> Chat:
		"""Fetch one chat. Chats are always private: requires
		``actor_id == chat.user_id`` (403 otherwise; 404 if missing)."""
		...

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
	async def search(self, dto: MessagesFilterDto, actor_id: UUID | None = None) -> Page[Message]:
		"""Page messages. Messages inherit visibility from their chat, so only
		messages whose chat belongs to ``actor_id`` are returned; ``actor_id=None``
		matches nothing (fail-closed). Applied in SQL so pagination counts match."""
		...

	@abc.abstractmethod
	async def get_one(self, message_uuid: UUID) -> Message: ...

	@abc.abstractmethod
	async def get_chat_owner_for_message(self, message_uuid: UUID) -> UUID | None:
		"""Return the ``user_id`` of the chat a message belongs to, or ``None`` if
		the message does not exist. Used to authorize message access (a user may
		only touch messages in their own chats)."""
		...

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
	async def search(self, dto: MessagesFilterDto, actor_id: UUID) -> Page[Message]:
		"""Page messages. Only messages in chats owned by ``actor_id`` are returned."""
		...

	@abc.abstractmethod
	async def get_one(self, message_uuid: UUID, actor_id: UUID) -> Message:
		"""Fetch one message. Requires the message's chat to belong to ``actor_id``
		(403 otherwise; 404 if missing)."""
		...

	@abc.abstractmethod
	async def update(self, message_uuid: UUID, updated_text: str, actor_id: UUID) -> UUID: ...

	@abc.abstractmethod
	async def delete(self, message_uuid: UUID, actor_id: UUID) -> UUID: ...

	@abc.abstractmethod
	async def append_model_message(self, result: LLMResult) -> Message:
		"""Persist the model reply carried by an LLMResult as a fresh message row
		(COMPLETED + text on success, FAILED + the error message on error). Every
		consumed result produces exactly one row and is returned (never None)."""
		...

	@abc.abstractmethod
	async def latest_model_message(self, chat_id: UUID) -> Optional[Message]: ...


class UploadedImage(BaseModel):
	"""A fully-read, validated uploaded image.

	Produced by IImageReader after enforcing the size cap and verifying the real
	content type (magic-number sniff). ``ext`` is the storage extension derived
	from the (validated) ``content_type``.
	"""

	model_config = ConfigDict(frozen=True)

	content_type: str
	ext: str
	data: bytes
	size: int


class IImageReader(abc.ABC):
	"""Reads and validates an uploaded image file.

	Keeps byte-level upload parsing (streaming, size cap, content-type sniff) out
	of the media service. On failure raises UnsupportedImageTypeException (415) or
	ImageTooLargeException (413), which the global exception handler maps to HTTP
	responses.
	"""

	@abc.abstractmethod
	async def read(self, file: UploadFile) -> UploadedImage:
		"""Read the whole upload into memory (enforcing the size cap) and verify its
		real content type agrees with the declared one."""
		...


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
	async def get_entity_owner(self, entity_type: MediaEntityType, entity_id: UUID) -> Optional[UUID]:
		"""Return the user id that owns ``(entity_type, entity_id)``.

		For characters/scenes this is the row's ``owner_id``; for users it is the
		user's own id. ``None`` is returned when no such entity exists (or the
		entity kind is unknown). Used to authorize media uploads: the uploader
		must own the target entity.
		"""
		...

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
	async def upload(self, dto: MediaUploadDTO) -> MediaAssetDTO:
		"""Upload the file in ``dto`` to object storage and persist a media row.

		``dto.owner_id`` is the authenticated uploader (sourced from the auth token
		by the caller). Authorization (the uploader owns the target entity),
		content-type sniffing, and orphan-object rollback are handled inside.
		"""
		...

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
