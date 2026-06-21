from dataclasses import dataclass
from logging import Logger

from src.application.ports import ILLMChatGateway, LLMModelType, LLMResponse, UserMessageDTO


@dataclass
class MockGateway(ILLMChatGateway):
	"""Offline stand-in gateway used when llm_model == testing_mock (no broker needed)."""

	logger: Logger

	async def generate_response(
		self,
		message: UserMessageDTO,
		history: list[UserMessageDTO],
	) -> LLMResponse:
		self.logger.info(f"Mock gateway received: {message.message}")
		return LLMResponse(
			text=f"Mock response for: {message.message}",
			model=message.llm_model or LLMModelType.testing_mock,
			usage={"tokens": 10},
			provider="mock",
		)
