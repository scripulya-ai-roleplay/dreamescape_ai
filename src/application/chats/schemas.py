from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.application.ports.llm import LLMModelType


class ChatFilterDTO(BaseModel):
	ids: None | list[UUID] = None
	titles: None | list[str] = None
	user_ids: None | list[UUID] = None
	scene_ids: None | list[UUID] = None

	limit: int = Field(default=50, ge=0)
	offset: int = Field(default=0, ge=0)


class ModelContextUsage(BaseModel):
	model_config = ConfigDict(frozen=True)

	llm_model: LLMModelType
	context_window_tokens: int
	usable_tokens: int
	remaining_tokens: int
	fits: bool
	estimated: bool


class ContextUsage(BaseModel):
	model_config = ConfigDict(frozen=True)

	cards_tokens: int
	history_tokens: int
	history_messages_count: int
	total_tokens: int
	estimated: bool
	models: list[ModelContextUsage]
