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
	"""Consume an LLMResult from scripulya_agent.

	Persists the reply by completing the PENDING placeholder message for the chat
	(COMPLETED + text on success, FAILED + the error message on error) and pushes
	it to any open SSE listeners for that chat. Correlation back to the originating
	placeholder is by chat_id (scripulya_agent echoes it).
	"""
	message = await message_service.complete_pending(result)
	if message is not None:
		events.publish_message(result.chat_id, message)
