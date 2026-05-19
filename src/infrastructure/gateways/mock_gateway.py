from dataclasses import dataclass
from logging import Logger
from src.application.ports import ILLMChatGateway


@dataclass
class MockGateway(ILLMChatGateway):
    logger: Logger

    async def generate_response(self, user_message: str) -> dict:
        self.logger.info(f"Mock gateway received: {user_message}")
        return {
            "text": f"Mock response for: {user_message}",
            "model": "testing_mock",
            "usage": {"tokens": 10}
        }