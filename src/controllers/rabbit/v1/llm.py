from dishka.integrations.faststream import FromDishka

from src.application.ports import IChatEventGateway, IMessageService, LLMResult
from src.conf import settings
from src.controllers.rabbit.v1.broker import broker


@broker.subscriber(settings.LLM_AGENT_RESULT_QUEUE)
async def handle_agent_result(
	result: LLMResult,
	message_service: FromDishka[IMessageService],
	events: FromDishka[IChatEventGateway],
) -> None:
	message = await message_service.append_model_message(result)
	events.publish_message(result.chat_id, message)
