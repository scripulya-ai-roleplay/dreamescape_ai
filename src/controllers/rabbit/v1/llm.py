import logging

from dishka.integrations.faststream import FromDishka

from src.application.memory.ingest_dispatcher import MemoryIngestDispatcher
from src.application.ports.chats import IChatEventGateway
from src.application.ports.llm import LLMResult
from src.application.ports.messages import IMessageService
from src.conf import settings
from src.controllers.rabbit.v1.broker import broker
from src.domain.models import MessageStatus
from src.infrastructure.logging.logger import Logger

logger = logging.getLogger(Logger.LOGGER_NAME)


async def _dispatch_agent_result(
	result: LLMResult,
	message_service: IMessageService,
	events: IChatEventGateway,
	ingest_dispatcher: MemoryIngestDispatcher | None = None,
) -> None:
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
	if ingest_dispatcher is not None and message.status == MessageStatus.COMPLETED:
		ingest_dispatcher.dispatch(result.chat_id, message.id)


@broker.subscriber(settings.LLM_AGENT_RESULT_QUEUE)
async def handle_agent_result(
	result: LLMResult,
	message_service: FromDishka[IMessageService],
	events: FromDishka[IChatEventGateway],
	ingest_dispatcher: FromDishka[MemoryIngestDispatcher],
) -> None:
	await _dispatch_agent_result(result, message_service, events, ingest_dispatcher)
