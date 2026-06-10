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
from src.domain.models import User, Scene, Character, Message, Chat
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


class ILLMChatGateway(abc.ABC):
	@abc.abstractmethod
	async def generate_response(
		self, user_message: str, history: list[UserMessageDTO] | None = None
	) -> LLMResponse: ...


class IChatsService(abc.ABC):
	@abc.abstractmethod
	async def send_message(self, chat_dto: UserMessageDTO) -> dict: ...


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


class IGatewayFactory(ABC):
	@abstractmethod
	def create_gateway(self, gateway_type: str) -> ILLMChatGateway:
		pass


class ApiResponse[T](BaseModel):
	model_config = ConfigDict(frozen=True)

	result: T
	correlation_id: Optional[str] = None
