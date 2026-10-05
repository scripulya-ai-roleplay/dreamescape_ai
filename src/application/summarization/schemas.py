from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.application.ports.llm import LLMModelType


class SummaryChapter(BaseModel):
	model_config = ConfigDict(frozen=True)

	chapter_number: int
	messages_count: int
	from_message_id: UUID
	until_message_id: UUID
	tokens_count: int


class ChapterRange(BaseModel):
	model_config = ConfigDict(extra="forbid", frozen=True)

	from_message_id: UUID
	until_message_id: UUID


class CreateSummariesDTO(BaseModel):
	model_config = ConfigDict(extra="forbid")

	chat_id: UUID
	llm_model: LLMModelType
	chapters: list[ChapterRange] = Field(min_length=1)


class UpdateSummaryDTO(BaseModel):
	model_config = ConfigDict(extra="forbid")

	content: str = Field(min_length=1)


class SummariesFilterDTO(BaseModel):
	chat_id: UUID
	limit: int = Field(default=50, ge=0)
	offset: int = Field(default=0, ge=0)
