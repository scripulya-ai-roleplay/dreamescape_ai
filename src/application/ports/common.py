from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession


class Page[T](BaseModel):
	model_config = ConfigDict(frozen=True)

	items: list[T]
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


class IUnitOfWork(ABC):
	@abstractmethod
	async def __aenter__(self) -> AsyncSession: ...

	@abstractmethod
	async def __aexit__(self, exc_type, exc_val, exc_tb) -> None: ...


class ApiResponse[T](BaseModel):
	model_config = ConfigDict(frozen=True)

	result: T
	correlation_id: str | None = None
