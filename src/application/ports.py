import abc
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models import User
from src.application.user.schemas import UserDTO


class Page[T](BaseModel):
    """Pagination wrapper for list results"""
    model_config = ConfigDict(frozen=True)

    items: List[T]
    count: int
    offset: int
    limit: int


class LLMModelType(StrEnum):
    testing_mock = "testing_mock"
    gemini_flash_preview = "gemini-3-flash-preview"


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
    async def find_users_by_filters(self, filters: UserDTO, limit: int = 10, offset: int = 0) -> Page[User]: ...

    @abc.abstractmethod
    async def create_user(self, user: User) -> User: ...

    @abc.abstractmethod
    async def delete_user(self, user_id: UUID) -> None: ...

    @abc.abstractmethod
    async def get_user_by_id(self, user_id: UUID) -> Optional[User]: ...


class UserMessageDTO(BaseModel):
    message: str
    llm_model: LLMModelType


class ILLMChatGateway(abc.ABC):
    @abc.abstractmethod
    async def generate_response(self, user_message: str) -> dict: ...


class IChatsService(abc.ABC):
    @abc.abstractmethod
    async def send_message(self, chat_dto: UserMessageDTO) -> dict: ...


class LLMResponse(BaseModel):
    text: str


class IGatewayFactory(ABC):
    @abstractmethod
    def create_gateway(self, gateway_type: str) -> ILLMChatGateway:
        pass


class ApiResponse[T](BaseModel):
    """Wrapper for API responses with correlation_id"""
    model_config = ConfigDict(frozen=True)

    result: T
    correlation_id: Optional[str] = None
