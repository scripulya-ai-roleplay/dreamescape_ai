import logging
from dataclasses import dataclass

from src.application.message.schemas import MessagesFilterDto
from src.application.ports import (
	IChatsService,
	IChatEventGateway,
	IChatSettingsGateway,
	IGatewayFactory,
	IMessageGateway,
	IUnitOfWork,
	UserMessageDTO,
)
from src.domain.models import ChatRoles, Message, MessageStatus

logger = logging.getLogger(__name__)


@dataclass
class LLMChatsService(IChatsService):
	gateway_factory: IGatewayFactory
	messages_gateway: IMessageGateway
	chat_settings_gateway: IChatSettingsGateway
	_uow: IUnitOfWork
	_events: IChatEventGateway

	async def send_message(self, chat_dto: UserMessageDTO) -> Message:
		logger.info(f"Processing LLM chat message with model: {chat_dto.llm_model}")
		gateway = self.gateway_factory.create_gateway(chat_dto.llm_model.value)

		# Prior turns only; the current user message is passed separately as chat_dto.
		# (search runs before the user message is persisted below, so it is excluded.)
		history_page = await self.messages_gateway.search(MessagesFilterDto(chats_ids=[chat_dto.chat_id]))
		history = [
			UserMessageDTO(message=m.message, chat_id=chat_dto.chat_id, llm_model=chat_dto.llm_model, role=m.role)
			for m in history_page.items
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

		# Hand the turn to the provider. Fire-and-forget gateways return None and
		# the reply arrives later via RabbitMQ and is appended by the result
		# subscriber; synchronous/offline gateways (mock) return the LLMResponse
		# immediately, so the reply is appended inline and pushed to SSE here.
		chat_settings = await self.chat_settings_gateway.get_for_chat(chat_dto.chat_id)
		response = await gateway.submit(chat_dto, history, chat_settings=chat_settings)
		if response is not None:
			async with self._uow:
				model_message = await self.messages_gateway.create(
					Message(
						message=response.text,
						chat_id=chat_dto.chat_id,
						role=ChatRoles.MODEL,
						status=MessageStatus.COMPLETED,
					)
				)
			self._events.publish_message(chat_dto.chat_id, model_message)

		return user_message
