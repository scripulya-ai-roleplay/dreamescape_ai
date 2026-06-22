import abc
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models import ChatRoles
from src.application.character.schemas import CharacterFilterDTO
from src.application.chats.schemas import ChatFilterDTO
from src.application.message.schemas import MessagesFilterDto
from src.application.scene.schemas import SceneFilterDTO
from src.domain.models import User, Scene, Character, Message, Chat, MessageStatus
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


class SendMessageResult(BaseModel):
	"""Returned by POST /messages: the persisted user message plus the model
	message that will hold the LLM reply. The model message starts PENDING and
	is delivered later via the chat SSE stream (or is already COMPLETED for the
	offline testing_mock gateway)."""

	user_message: Message
	model_message: Message


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


# --- scripulya_agent wire contract (RabbitMQ) -------------------------------
# These mirror scripulya_agent's application/ports.py DTOs so the two services
# share an identical on-the-wire schema. UserMessageDTO above is reused as the
# per-turn shape (its fields match scripulya_agent's UserMessageDTO exactly).


class LLMRequest(BaseModel):
	"""Published to llm.agent.request: the current message plus prior history."""

	message: UserMessageDTO
	history: list[UserMessageDTO] = []


class LLMErrorResponse(BaseModel):
	"""Structured failure returned by scripulya_agent (LLMResult.error)."""

	error_code: str  # machine-readable snake_case, e.g. "model_is_inaccessible"
	status: int  # HTTP-style status, e.g. 503
	reason: str  # short human-readable reason phrase
	message: str  # detailed message
	provider: str | None = None
	details: dict = {}


class LLMResult(BaseModel):
	"""Consumed from llm.agent.result; correlated by chat_id.

	Exactly one of `message` / `error` is set.
	"""

	chat_id: UUID
	message: UserMessageDTO | None = None  # the model's reply (role=MODEL) on success
	error: LLMErrorResponse | None = None  # set on failure


class ILLMChatGateway(abc.ABC):
	@abc.abstractmethod
	async def submit(
		self,
		message: UserMessageDTO,
		history: list[UserMessageDTO],
	) -> Optional[LLMResponse]:
		"""Hand the turn to the LLM provider.

		Returns the LLMResponse immediately for synchronous/offline gateways
		(e.g. testing_mock); returns None when the request was published and the
		reply will arrive asynchronously (scripulya_agent over RabbitMQ).
		"""
		...


class IChatsService(abc.ABC):
	@abc.abstractmethod
	async def send_message(self, chat_dto: UserMessageDTO) -> SendMessageResult: ...


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
	async def complete_pending(self, chat_id: UUID, content: str, status: MessageStatus) -> Optional[Message]:
		"""Resolve the most recent PENDING model message for chat_id: set its
		content and final status (COMPLETED/FAILED). Returns the updated Message,
		or None if no PENDING row exists (late/duplicate/orphan result)."""
		...

	@abc.abstractmethod
	async def latest_model_message(self, chat_id: UUID) -> Optional[Message]:
		"""Return the most recent model message for chat_id (any status), or None."""
		...


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
	async def complete_pending(self, result: LLMResult) -> Optional[Message]:
		"""Resolve the pending model message for result.chat_id from an LLMResult:
		COMPLETED + the reply text on success, FAILED + the error message on error.
		Returns the updated Message, or None if nothing was pending."""
		...

	@abc.abstractmethod
	async def latest_model_message(self, chat_id: UUID) -> Optional[Message]:
		"""Return the most recent model message for chat_id (any status), or None."""
		...


class IGatewayFactory(ABC):
	@abstractmethod
	def create_gateway(self, gateway_type: str) -> ILLMChatGateway:
		pass


class ApiResponse[T](BaseModel):
	model_config = ConfigDict(frozen=True)

	result: T
	correlation_id: Optional[str] = None
