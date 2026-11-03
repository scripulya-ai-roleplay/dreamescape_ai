import abc
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.application.chats.settings import ChatSettings
from src.application.ports.common import Page
from src.application.ports.llm import LLMErrorResponse, LLMModelType
from src.application.summarization.schemas import (
	CreateSummariesDTO,
	SummariesFilterDTO,
	SummaryChapter,
	UpdateSummaryDTO,
)
from src.domain.models import ChatRoles, ChatSummary, MessageStatus, SummaryStatus


class SummaryRequest(BaseModel):
	summary_id: UUID
	chat_id: UUID
	llm_model: LLMModelType
	system_prompt: str
	content: str
	chat_settings: ChatSettings | None = None


class SummaryResult(BaseModel):
	summary_id: UUID
	chat_id: UUID
	text: str | None = None
	error: LLMErrorResponse | None = None


class SummarySourceMessage(BaseModel):
	model_config = ConfigDict(frozen=True)

	id: UUID
	role: ChatRoles
	content: str
	status: MessageStatus
	created_at: datetime
	is_archived: bool = False
	summary_id: UUID | None = None


class ISummaryRepository(abc.ABC):
	@abc.abstractmethod
	async def list_source_messages(self, chat_id: UUID) -> list[SummarySourceMessage]: ...

	@abc.abstractmethod
	async def list_summary_messages(self, summary_id: UUID) -> list[SummarySourceMessage]: ...

	@abc.abstractmethod
	async def create(self, summary: ChatSummary) -> ChatSummary: ...

	@abc.abstractmethod
	async def claim_messages(self, summary_id: UUID, message_ids: list[UUID]) -> int: ...

	@abc.abstractmethod
	async def get_one(self, summary_id: UUID) -> ChatSummary | None: ...

	@abc.abstractmethod
	async def search(self, dto: SummariesFilterDTO) -> Page[ChatSummary]: ...

	@abc.abstractmethod
	async def list_for_chat(self, chat_id: UUID, statuses: list[SummaryStatus]) -> list[ChatSummary]: ...

	@abc.abstractmethod
	async def dispatch_next_queued(self, chat_id: UUID) -> ChatSummary | None: ...

	@abc.abstractmethod
	async def complete(self, summary_id: UUID, content: str, summary_tokens: int) -> ChatSummary: ...

	@abc.abstractmethod
	async def fail(self, summary_id: UUID, error: str) -> ChatSummary: ...

	@abc.abstractmethod
	async def archive_messages(self, summary_id: UUID) -> int: ...

	@abc.abstractmethod
	async def release_messages(self, summary_id: UUID) -> int: ...

	@abc.abstractmethod
	async def update_content(self, summary_id: UUID, content: str, summary_tokens: int) -> ChatSummary: ...

	@abc.abstractmethod
	async def expire_pending(self, chat_id: UUID, older_than: datetime) -> list[UUID]: ...


class ISummarizationAgentGateway(abc.ABC):
	@abc.abstractmethod
	async def submit(self, request: SummaryRequest) -> SummaryResult | None: ...


class ITextCompleter(abc.ABC):
	@abc.abstractmethod
	async def complete(self, llm_model: LLMModelType, system_prompt: str, content: str) -> str: ...


class ISummarizationService(abc.ABC):
	@abc.abstractmethod
	async def list_chapters(self, chat_id: UUID, actor_id: UUID) -> list[SummaryChapter]: ...

	@abc.abstractmethod
	async def summarize(self, dto: CreateSummariesDTO, actor_id: UUID) -> list[ChatSummary]: ...

	@abc.abstractmethod
	async def search(self, dto: SummariesFilterDTO, actor_id: UUID) -> Page[ChatSummary]: ...

	@abc.abstractmethod
	async def get_one(self, summary_id: UUID, actor_id: UUID) -> ChatSummary: ...

	@abc.abstractmethod
	async def update(self, summary_id: UUID, dto: UpdateSummaryDTO, actor_id: UUID) -> ChatSummary: ...

	@abc.abstractmethod
	async def handle_result(self, result: SummaryResult) -> ChatSummary | None: ...

	@abc.abstractmethod
	async def prompt_summaries(self, chat_id: UUID) -> list[ChatSummary]: ...
