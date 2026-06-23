import logging
from dataclasses import dataclass

from src.application.message.schemas import MessagesFilterDto
from src.application.ports import (
	IChatsService,
	IChatEventGateway,
	IGatewayFactory,
	IMessageGateway,
	IUnitOfWork,
	SendMessageResult,
	UserMessageDTO,
)
from src.domain.models import ChatRoles, Message, MessageStatus

logger = logging.getLogger(__name__)


@dataclass
class LLMChatsService(IChatsService):
	gateway_factory: IGatewayFactory
	messages_gateway: IMessageGateway
	_uow: IUnitOfWork
	_events: IChatEventGateway

	async def send_message(self, chat_dto: UserMessageDTO) -> SendMessageResult:
		logger.info(f"Processing LLM chat message with model: {chat_dto.llm_model}")
		gateway = self.gateway_factory.create_gateway(chat_dto.llm_model.value)

		# Prior turns only; the current user message is passed separately as chat_dto.
		# PENDING placeholders are excluded so empty in-flight model messages are
		# never fed back to the model as history.
		history_page = await self.messages_gateway.search(MessagesFilterDto(chats_ids=[chat_dto.chat_id]))
		history = [
			UserMessageDTO(message=m.message, chat_id=chat_dto.chat_id, llm_model=chat_dto.llm_model, role=m.role)
			for m in history_page.items
			if m.status != MessageStatus.PENDING
		]

		async with self._uow:
			user_message = await self.messages_gateway.create(
				Message(
					message=chat_dto.message,
					chat_id=chat_dto.chat_id,
					role=chat_dto.role,
					status=MessageStatus.COMPLETED,
				)
			)
			model_message = await self.messages_gateway.create(
				Message(message="", chat_id=chat_dto.chat_id, role=ChatRoles.MODEL, status=MessageStatus.PENDING)
			)

		# Hand the turn to the provider. Fire-and-forget gateways return None and
		# the reply arrives via RabbitMQ; synchronous/offline gateways (mock)
		# return the LLMResponse immediately and are resolved inline below.
		response = await gateway.submit(chat_dto, history)
		if response is not None:
			async with self._uow:
				resolved = await self.messages_gateway.complete_pending(
					chat_dto.chat_id, response.text, MessageStatus.COMPLETED
				)
			if resolved is not None:
				model_message = resolved
			self._events.publish_message(chat_dto.chat_id, model_message)

		return SendMessageResult(user_message=user_message, model_message=model_message)
