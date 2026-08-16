import abc
from abc import ABC, abstractmethod
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel

from src.application.chats.settings import ChatSettings
from src.domain.models import Character, ChatRoles, Scene


class LLMModelType(StrEnum):
	testing_mock = "testing_mock"
	gemini_flash_preview = "gemini-3-flash-preview"
	gemini_pro = "gemini-3.1-pro-preview"
	claude_sonnet = "claude-sonnet-4-20250514"
	claude_haiku = "claude-haiku-4-20250514"
	qwen_plus = "qwen-plus"
	qwen_turbo = "qwen-turbo"
	qwen_max = "qwen-max"
	glm_5_2 = "glm-5.2"
	glm_4_6 = "glm-4.6"
	glm_4_5 = "glm-4.5"


LLM_MODEL_CONTEXT_WINDOWS: dict[LLMModelType, int] = {
	LLMModelType.gemini_flash_preview: 1_048_576,
	LLMModelType.gemini_pro: 1_048_576,
	LLMModelType.claude_sonnet: 200_000,
	LLMModelType.claude_haiku: 200_000,
	LLMModelType.qwen_plus: 1_000_000,
	LLMModelType.qwen_turbo: 1_000_000,
	LLMModelType.qwen_max: 32_768,
	LLMModelType.glm_5_2: 1_000_000,
	LLMModelType.glm_4_6: 200_000,
	LLMModelType.glm_4_5: 128_000,
}


class ITokenCounter(abc.ABC):
	@abc.abstractmethod
	def count(self, text: str) -> int: ...


class LLMResponse(BaseModel):
	text: str
	model: LLMModelType
	usage: dict | None = None
	provider: str
	reasoning: str | None = None


class UserMessageDTO(BaseModel):
	chat_id: UUID
	message: str
	llm_model: LLMModelType | None = LLMModelType.testing_mock
	role: ChatRoles
	reasoning: str | None = None


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
	) -> LLMResponse | None: ...


class IScripulyaAgentClient(abc.ABC):
	@abc.abstractmethod
	async def publish(self, req: LLMRequest) -> None: ...


class IPromptService(abc.ABC):
	@abc.abstractmethod
	def build_system_prompt(
		self,
		scene: Scene | None,
		characters: list[Character],
		user_character: Character | None = None,
		chat_settings: ChatSettings | None = None,
	) -> str: ...


class IGatewayFactory(ABC):
	@abstractmethod
	def create_gateway(self, gateway_type: str) -> ILLMChatGateway:
		pass
