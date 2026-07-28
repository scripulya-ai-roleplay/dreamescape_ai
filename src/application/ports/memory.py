import abc
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.application.chats.prompt_sections import PromptSections
from src.application.chats.settings import MemorySettings
from src.domain.models import ConversationSummary, Message


@dataclass(frozen=True)
class MemoryChunk:
	message_id: UUID
	role: str
	content: str
	distance: float
	embedding: list[float] | None = None


@dataclass(frozen=True)
class EnrichResult:
	sections: PromptSections
	tail: list[Message]


class ISummaryGateway(abc.ABC):
	@abc.abstractmethod
	async def latest(self, chat_id: UUID) -> ConversationSummary | None: ...

	@abc.abstractmethod
	async def insert(self, summary: ConversationSummary) -> ConversationSummary: ...


class IVectorMemoryGateway(abc.ABC):
	@abc.abstractmethod
	async def store(self, chat_id: UUID, message_id: UUID, role: str, content: str) -> None: ...

	@abc.abstractmethod
	async def retrieve(
		self,
		chat_id: UUID,
		query: str,
		k: int = 5,
		max_distance: float = 0.5,
		exclude_message_ids: set[UUID] | None = None,
		dedup_embedding: list[float] | None = None,
		dedup_max_distance: float = 0.08,
	) -> list[MemoryChunk]: ...


class IGraphMemoryGateway(abc.ABC):
	@abc.abstractmethod
	async def store(self, chat_id: UUID, user_msg: str, model_reply: str, reference_time: datetime) -> None: ...

	@abc.abstractmethod
	async def retrieve(self, chat_id: UUID, query: str) -> list[str]: ...

	@abc.abstractmethod
	async def delete_group(self, chat_id: UUID) -> None: ...


class IMemoryService(abc.ABC):
	@abc.abstractmethod
	async def enrich(
		self, chat_id: UUID, user_msg: str, memory_settings: MemorySettings | None = None
	) -> EnrichResult: ...

	@abc.abstractmethod
	async def ingest(self, chat_id: UUID, model_reply_message_id: UUID) -> None: ...


class IMemoryControlService(abc.ABC):
	@abc.abstractmethod
	async def current_summary(self, chat_id: UUID, actor_id: UUID) -> ConversationSummary | None: ...

	@abc.abstractmethod
	async def set_summary(self, chat_id: UUID, content: str, actor_id: UUID) -> ConversationSummary: ...

	@abc.abstractmethod
	async def context_usage(self, chat_id: UUID, actor_id: UUID) -> dict: ...
