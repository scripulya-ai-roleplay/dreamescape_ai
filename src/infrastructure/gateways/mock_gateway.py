from dataclasses import dataclass
from logging import Logger

from src.application.chats.settings import ChatSettings
from src.application.ports import ILLMChatGateway, LLMModelType, LLMResponse, UserMessageDTO


@dataclass
class MockGateway(ILLMChatGateway):
	"""Offline stand-in gateway used when llm_model == testing_mock (no broker needed)."""

	logger: Logger

	async def submit(
		self,
		message: UserMessageDTO,
		history: list[UserMessageDTO],
		chat_settings: ChatSettings | None = None,  # noqa: ARG002 - offline gateway ignores settings
	) -> LLMResponse:
		"""Offline/synchronous gateway: returns the canned reply immediately.

		The caller completes the placeholder message inline and notifies SSE within
		the same request — no broker round trip.
		"""
		self.logger.info(f"Mock gateway received: {message.message}")
		return LLMResponse(
			text=f"Mock response for: {message.message}",
			model=message.llm_model or LLMModelType.testing_mock,
			usage={"tokens": 10},
			provider="mock",
		)
