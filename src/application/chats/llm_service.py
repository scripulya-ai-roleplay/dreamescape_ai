import logging
from dataclasses import dataclass

from src.application.message.schemas import MessagesFilterDto
from src.application.ports import LLMResponse, IMessageGateway
from src.application.ports import (
	IChatsService,
	UserMessageDTO,
	IGatewayFactory,
)

logger = logging.getLogger(__name__)


@dataclass
class LLMChatsService(IChatsService):
	gateway_factory: IGatewayFactory
	messages_gateway: IMessageGateway

	async def send_message(self, chat_dto: UserMessageDTO) -> LLMResponse:
		logger.info(f"Processing LLM chat message with model: {chat_dto.llm_model}")
		# Create appropriate gateway based on the LLM model
		gateway = self.gateway_factory.create_gateway(chat_dto.llm_model.value)

		message_dto = MessagesFilterDto(chats_ids=[chat_dto.chat_id])

		history = await self.messages_gateway.search(message_dto)
		history = [
			UserMessageDTO(message=m.message, chat_id=chat_dto.chat_id, llm_model=chat_dto.llm_model, role=m.role)
			for m in history.items
		]

		response = await gateway.generate_response(chat_dto.message, history)

		logger.info("Successfully generated LLM response")
		return response
