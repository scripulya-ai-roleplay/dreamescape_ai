import logging
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.application.ports import LLMErrorResponse, LLMResult

# Importing the module registers the result subscriber on the module-level broker.
from src.controllers.rabbit.v1.llm import handle_agent_result  # noqa: F401
from src.domain.models import ChatRoles, Message, MessageStatus


def _failed_result(chat_id):
	return LLMResult(
		chat_id=chat_id,
		error=LLMErrorResponse(
			error_code="model_is_inaccessible",
			status=503,
			reason="Model is inaccessible",
			message="Google gateway error: 404 NOT_FOUND",
			provider="Google",
		),
	)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_error_result_is_logged_and_dispatched(caplog):
	"""A provider failure arriving over RabbitMQ is surfaced in the backend log
	(not only in the agent) and still persisted + pushed to SSE as a FAILED turn."""
	chat_id = uuid4()
	result = _failed_result(chat_id)
	created = Message(
		id=uuid4(),
		message=result.error.message,
		chat_id=chat_id,
		role=ChatRoles.MODEL,
		status=MessageStatus.FAILED,
	)
	message_service = AsyncMock()
	message_service.append_model_message.return_value = created
	# publish_message is a sync method on IChatEventGateway, so a plain MagicMock.
	events = MagicMock()

	with caplog.at_level(logging.WARNING):
		await handle_agent_result(result, message_service=message_service, events=events)

	message_service.append_model_message.assert_awaited_once_with(result)
	events.publish_message.assert_called_once_with(chat_id, created)
	assert any("model_is_inaccessible" in rec.message and str(chat_id) in rec.message for rec in caplog.records), (
		"provider failure must be logged on the backend side too"
	)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_success_result_is_dispatched_without_warning(caplog):
	"""A successful reply is dispatched normally and produces no failure warning."""
	chat_id = uuid4()
	result = LLMResult(chat_id=chat_id)  # error is None -> no failure warning
	created = Message(id=uuid4(), message="ok", chat_id=chat_id, role=ChatRoles.MODEL, status=MessageStatus.COMPLETED)
	message_service = AsyncMock()
	message_service.append_model_message.return_value = created
	events = MagicMock()

	with caplog.at_level(logging.WARNING):
		await handle_agent_result(result, message_service=message_service, events=events)

	message_service.append_model_message.assert_awaited_once_with(result)
	events.publish_message.assert_called_once_with(chat_id, created)
	assert not any(rec.levelno >= logging.WARNING for rec in caplog.records)
