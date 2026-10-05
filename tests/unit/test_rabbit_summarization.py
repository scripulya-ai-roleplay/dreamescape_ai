import logging
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.application.ports.llm import LLMErrorResponse
from src.application.ports.summarization import ISummarizationService, SummaryResult
from src.controllers.rabbit.v1.summarization import _dispatch_summary_result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_result_is_handed_to_the_service():
	service = AsyncMock(spec=ISummarizationService)
	result = SummaryResult(summary_id=uuid4(), chat_id=uuid4(), text="EVENTS: ...")

	await _dispatch_summary_result(result, service)

	service.handle_result.assert_awaited_once_with(result)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_error_result_is_logged(caplog):
	service = AsyncMock(spec=ISummarizationService)
	result = SummaryResult(
		summary_id=uuid4(),
		chat_id=uuid4(),
		error=LLMErrorResponse(error_code="model_is_inaccessible", status=503, reason="down", message="404 NOT_FOUND"),
	)

	with caplog.at_level(logging.WARNING):
		await _dispatch_summary_result(result, service)

	assert "404 NOT_FOUND" in caplog.text
	service.handle_result.assert_awaited_once_with(result)
