import logging
from dataclasses import dataclass

from src.application.ports import (
	IChatsService,
	UserMessageDTO,
	IGatewayFactory,
)

logger = logging.getLogger(__name__)


@dataclass
class LLMChatsService(IChatsService):
	gateway_factory: IGatewayFactory

	async def send_message(self, chat_dto: UserMessageDTO) -> dict:
		logger.info(f"Processing LLM chat message with model: {chat_dto.llm_model}")

		# Create appropriate gateway based on the LLM model
		gateway = self.gateway_factory.create_gateway(chat_dto.llm_model.value)

		# Generate response using the gateway
		response = await gateway.generate_response(chat_dto.message)

		logger.info("Successfully generated LLM response")
		return response
