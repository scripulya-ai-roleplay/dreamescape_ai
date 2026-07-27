from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.application.chats.budgeter import HeuristicTokenCounter
from src.application.memory.summary_service import SummaryService
from src.conf import settings
from src.domain.models import ChatRoles, ConversationSummary, Message


def _uow_cm():
	uow = AsyncMock()
	uow.__aenter__.return_value = uow
	uow.__aexit__.return_value = None
	return uow


def _msg(text: str, role=ChatRoles.USER) -> Message:
	return Message(id=uuid4(), message=text, chat_id=uuid4(), role=role)


def _service(summary_gateway, message_gateway, summary_model):
	return SummaryService(
		summary_gateway=summary_gateway,
		message_gateway=message_gateway,
		summary_model=summary_model,
		token_counter=HeuristicTokenCounter(),
		_uow=_uow_cm(),
	)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_maybe_fold_noop_under_threshold(monkeypatch):
	monkeypatch.setattr(settings, "SUMMARY_TRIGGER_TOKENS", 1000)
	summary_gateway = AsyncMock(latest=AsyncMock(return_value=None))
	message_gateway = AsyncMock(tail_after=AsyncMock(return_value=[_msg("short")]))
	summary_model = AsyncMock()
	svc = _service(summary_gateway, message_gateway, summary_model)

	await svc.maybe_fold(uuid4())

	summary_model.summarize.assert_not_awaited()
	summary_gateway.insert.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fold_inserts_summary_superseding_latest(monkeypatch):
	monkeypatch.setattr(settings, "SUMMARY_TRIGGER_TOKENS", 5)
	monkeypatch.setattr(settings, "SUMMARY_FOLD_BATCH_TOKENS", 1000)
	chat_id = uuid4()
	latest = ConversationSummary(
		id=uuid4(), chat_id=chat_id, from_message_id=uuid4(), to_message_id=uuid4(), content="old", model="x"
	)
	tail = [_msg("a reasonably long message body " * 5), _msg("another long message body " * 5)]
	summary_gateway = AsyncMock(latest=AsyncMock(return_value=latest), insert=AsyncMock())
	message_gateway = AsyncMock(tail_after=AsyncMock(return_value=tail))
	summary_model = AsyncMock(summarize=AsyncMock(return_value="new combined summary"))
	svc = _service(summary_gateway, message_gateway, summary_model)

	await svc.maybe_fold(chat_id)

	summary_model.summarize.assert_awaited_once()
	inserted = summary_gateway.insert.await_args.args[0]
	assert isinstance(inserted, ConversationSummary)
	assert inserted.content == "new combined summary"
	assert inserted.supersedes_id == latest.id
	assert inserted.to_message_id == tail[-1].id


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fold_swallows_duplicate_insert(monkeypatch):
	from sqlalchemy.exc import IntegrityError

	monkeypatch.setattr(settings, "SUMMARY_TRIGGER_TOKENS", 5)
	monkeypatch.setattr(settings, "SUMMARY_FOLD_BATCH_TOKENS", 1000)
	summary_gateway = AsyncMock(
		latest=AsyncMock(return_value=None), insert=AsyncMock(side_effect=IntegrityError("stmt", {}, Exception()))
	)
	message_gateway = AsyncMock(tail_after=AsyncMock(return_value=[_msg("a long message body " * 5)]))
	summary_model = AsyncMock(summarize=AsyncMock(return_value="summary"))
	svc = _service(summary_gateway, message_gateway, summary_model)

	await svc.maybe_fold(uuid4())  # redelivery duplicate must not raise
