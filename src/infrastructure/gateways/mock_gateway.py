from dataclasses import dataclass
from logging import Logger
from src.application.ports import ILLMChatGateway, LLMResponse, LLMModelType, UserMessageDTO


@dataclass
class MockGateway(ILLMChatGateway):
	logger: Logger

	async def generate_response(self, user_message: str, history: list[UserMessageDTO] | None = None) -> LLMResponse:
		self.logger.info(f"Mock gateway received: {user_message}")
		return LLMResponse(
			text=f"Mock response for: {user_message}",
			model=LLMModelType.testing_mock,
			usage={"tokens": 10},
			provider="mock",
		)
