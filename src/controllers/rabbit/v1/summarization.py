import logging

from dishka.integrations.faststream import FromDishka

from src.application.ports.summarization import ISummarizationService, SummaryResult
from src.conf import settings
from src.controllers.rabbit.v1.broker import broker
from src.infrastructure.logging.logger import Logger

logger = logging.getLogger(Logger.LOGGER_NAME)


async def _dispatch_summary_result(result: SummaryResult, service: ISummarizationService) -> None:
	if result.error is not None:
		logger.warning(
			"Summarization failed summary_id=%s chat_id=%s provider=%s code=%s: %s",
			result.summary_id,
			result.chat_id,
			result.error.provider,
			result.error.error_code,
			result.error.message,
		)
	await service.handle_result(result)


@broker.subscriber(settings.SUMMARY_AGENT_RESULT_QUEUE)
async def handle_summary_result(result: SummaryResult, service: FromDishka[ISummarizationService]) -> None:
	await _dispatch_summary_result(result, service)
