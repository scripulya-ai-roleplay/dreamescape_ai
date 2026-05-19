from dataclasses import dataclass

from src.application.ports import (
    IChatsService,
    UserMessageDTO,
    IGatewayFactory,
)


@dataclass
class ChatsService(IChatsService):
    gateway_factory: IGatewayFactory

    async def send_message(self, chat_dto: UserMessageDTO) -> dict:
        # noinspection PyTypeChecker
        gateway = self.gateway_factory.create_gateway(chat_dto.llm_model.value)
        json_data = await gateway.generate_response(chat_dto.message)
        return json_data

