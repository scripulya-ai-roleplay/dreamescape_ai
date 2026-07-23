import abc
from typing import Optional
from uuid import UUID

from starlette.responses import StreamingResponse

from src.application.message.schemas import MessagesFilterDto
from src.application.ports.common import Page
from src.application.ports.llm import LLMResult
from src.domain.models import Message


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


class IGenerationHeartbeat(abc.ABC):
	@abc.abstractmethod
	async def register_inflight(self, request_id: str, chat_id: UUID) -> None: ...

	@abc.abstractmethod
	async def sweep_dead(self) -> list[tuple[str, UUID]]: ...


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
	async def record_failed_generation(self, chat_id: UUID, reason: str) -> Message: ...

	@abc.abstractmethod
	async def latest_model_message(self, chat_id: UUID) -> Optional[Message]: ...
