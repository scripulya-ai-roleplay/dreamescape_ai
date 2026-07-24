import logging

from dishka.integrations.faststream import FromDishka

from src.application.ports.chats import IChatEventGateway
from src.application.ports.llm import LLMResult
from src.application.ports.messages import IMessageService
from src.conf import settings
from src.controllers.rabbit.v1.broker import broker
from src.infrastructure.logging.logger import Logger

logger = logging.getLogger(Logger.LOGGER_NAME)


async def _dispatch_agent_result(
	result: LLMResult,
	message_service: IMessageService,
	events: IChatEventGateway,
) -> None:
	# Surface provider failures in the backend log too. Without this the only
	# trace of a failed generation lived in the agent process, so backend-side
	# debugging showed nothing while the client hung on the error reply.
	if result.error is not None:
		logger.warning(
			"LLM generation failed chat_id=%s provider=%s code=%s status=%s: %s",
			result.chat_id,
			result.error.provider,
			result.error.error_code,
			result.error.status,
			result.error.message,
		)
	message = await message_service.append_model_message(result)
	events.publish_message(result.chat_id, message)


@broker.subscriber(settings.LLM_AGENT_RESULT_QUEUE)
async def handle_agent_result(
	result: LLMResult,
	message_service: FromDishka[IMessageService],
	events: FromDishka[IChatEventGateway],
) -> None:
	# Plain helper kept separate (and DI-free) so the dispatch logic is unit-testable
	# without standing up the dishka container the FromDishka middleware resolves.
	await _dispatch_agent_result(result, message_service, events)
