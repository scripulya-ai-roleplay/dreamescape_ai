from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.application.chats.settings import MemorySettings
from src.application.memory.service import MemoryService
from src.application.ports.memory import MemoryChunk
from src.conf import settings
from src.domain.models import ChatRoles, ConversationSummary, Message, MessageStatus


def _uow_cm():
	uow = AsyncMock()
	uow.__aenter__.return_value = uow
	uow.__aexit__.return_value = None
	return uow


def _session_cm():
	# A passthrough SAVEPOINT: _safe wraps each read in `async with session.begin_nested()`.
	# `session` is a plain MagicMock so begin_nested() returns the nested cm directly (an AsyncMock
	# call would instead return a coroutine).
	session = MagicMock()
	nested = AsyncMock()
	nested.__aenter__.return_value = nested
	nested.__aexit__.return_value = None  # falsy => does not suppress => exception re-raises
	session.begin_nested.return_value = nested
	return session


def _service(**overrides):
	summary_gateway = overrides.get("summary_gateway", AsyncMock())
	vector_gateway = overrides.get("vector_gateway", AsyncMock())
	graph_gateway = overrides.get("graph_gateway")
	if graph_gateway is None:
		graph_gateway = AsyncMock()
		graph_gateway.retrieve = AsyncMock(return_value=[])
	message_gateway = overrides.get("message_gateway", AsyncMock())
	chat_settings_gateway = overrides.get("chat_settings_gateway", AsyncMock())
	summary_service = overrides.get("summary_service", AsyncMock())
	uow = overrides.get("uow", _uow_cm())
	session = overrides.get("session", _session_cm())
	return MemoryService(
		summary_gateway=summary_gateway,
		vector_gateway=vector_gateway,
		graph_gateway=graph_gateway,
		message_gateway=message_gateway,
		chat_settings_gateway=chat_settings_gateway,
		summary_service=summary_service,
		_uow=uow,
		_session=session,
		_embedder=None,
		_redis=None,
	)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_enrich_fills_summary_memories_and_tail():
	chat_id = uuid4()
	tail = [Message(id=uuid4(), message="hi", chat_id=chat_id, role=ChatRoles.USER)]
	summary = ConversationSummary(
		chat_id=chat_id, from_message_id=uuid4(), to_message_id=tail[0].id, content="the story so far", model="x"
	)
	chunk = MemoryChunk(message_id=uuid4(), role=ChatRoles.MODEL.value, content="a callback line", distance=0.1)
	svc = _service(
		summary_gateway=AsyncMock(latest=AsyncMock(return_value=summary)),
		message_gateway=AsyncMock(tail_after=AsyncMock(return_value=tail)),
		vector_gateway=AsyncMock(retrieve=AsyncMock(return_value=[chunk])),
	)

	result = await svc.enrich(chat_id, "query")

	assert result.sections.summary == "the story so far"
	assert "a callback line" in result.sections.memories
	assert result.tail == tail


@pytest.mark.unit
@pytest.mark.asyncio
async def test_enrich_vector_failure_degrades_to_empty():
	chat_id = uuid4()
	svc = _service(
		summary_gateway=AsyncMock(latest=AsyncMock(return_value=None)),
		message_gateway=AsyncMock(tail_after=AsyncMock(return_value=[])),
		vector_gateway=AsyncMock(retrieve=AsyncMock(side_effect=RuntimeError("boom"))),
	)

	result = await svc.enrich(chat_id, "query")

	assert result.sections.memories == ""
	assert result.sections.summary == ""


@pytest.mark.unit
@pytest.mark.asyncio
async def test_enrich_respects_per_chat_disabled_flags():
	chat_id = uuid4()
	tail = [Message(id=uuid4(), message="hi", chat_id=chat_id, role=ChatRoles.USER)]
	summary_gw = AsyncMock(latest=AsyncMock(return_value=None))
	vector_gw = AsyncMock(retrieve=AsyncMock(return_value=[]))
	svc = _service(
		summary_gateway=summary_gw,
		vector_gateway=vector_gw,
		message_gateway=AsyncMock(tail_after=AsyncMock(return_value=tail)),
	)

	await svc.enrich(chat_id, "query", MemorySettings(summaryEnabled=False, vectorMemoryEnabled=False))

	summary_gw.latest.assert_not_awaited()
	vector_gw.retrieve.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_stores_user_and_model_then_folds():
	chat_id = uuid4()
	model_id = uuid4()
	user_id = uuid4()
	model_msg = Message(
		id=model_id, message="reply", chat_id=chat_id, role=ChatRoles.MODEL, status=MessageStatus.COMPLETED
	)
	user_msg = Message(id=user_id, message="hello", chat_id=chat_id, role=ChatRoles.USER)
	chat_settings_gateway = AsyncMock()
	chat_settings_gateway.get_for_chat.return_value = MagicMock(memory=MemorySettings())
	vector_gw = AsyncMock()
	summary_svc = AsyncMock()
	svc = _service(
		vector_gateway=vector_gw,
		message_gateway=AsyncMock(
			get_one=AsyncMock(return_value=model_msg), message_before=AsyncMock(return_value=user_msg)
		),
		chat_settings_gateway=chat_settings_gateway,
		summary_service=summary_svc,
	)

	await svc.ingest(chat_id, model_id)

	assert vector_gw.store.await_count == 2
	summary_svc.maybe_fold.assert_awaited_once_with(chat_id)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_vector_store_failure_does_not_propagate():
	chat_id = uuid4()
	model_id = uuid4()
	model_msg = Message(id=model_id, message="reply", chat_id=chat_id, role=ChatRoles.MODEL)
	chat_settings_gateway = AsyncMock()
	chat_settings_gateway.get_for_chat.return_value = MagicMock(memory=MemorySettings())
	vector_gw = AsyncMock()
	vector_gw.store.side_effect = RuntimeError("db down")
	summary_svc = AsyncMock()
	svc = _service(
		vector_gateway=vector_gw,
		message_gateway=AsyncMock(
			get_one=AsyncMock(return_value=model_msg), message_before=AsyncMock(return_value=None)
		),
		chat_settings_gateway=chat_settings_gateway,
		summary_service=summary_svc,
	)

	await svc.ingest(chat_id, model_id)  # must not raise
	summary_svc.maybe_fold.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_skipped_when_idempotency_lock_not_acquired():
	chat_id = uuid4()
	model_id = uuid4()
	redis = AsyncMock()
	redis.set.return_value = False  # already ingested
	vector_gw = AsyncMock()
	svc = _service(vector_gateway=vector_gw)
	svc._redis = redis

	await svc.ingest(chat_id, model_id)

	vector_gw.store.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_stores_graph_episode_when_enabled(monkeypatch):
	monkeypatch.setattr(settings, "GRAPH_MEMORY_ENABLED", True)
	monkeypatch.setattr(settings, "VECTOR_MEMORY_ENABLED", False)
	monkeypatch.setattr(settings, "SUMMARY_ENABLED", False)
	chat_id = uuid4()
	model_id = uuid4()
	model_msg = Message(
		id=model_id, message="the reply", chat_id=chat_id, role=ChatRoles.MODEL, status=MessageStatus.COMPLETED
	)
	user_msg = Message(id=uuid4(), message="the question", chat_id=chat_id, role=ChatRoles.USER)
	chat_settings_gateway = AsyncMock()
	chat_settings_gateway.get_for_chat.return_value = MagicMock(memory=MemorySettings(graphMemoryEnabled=True))
	graph_gw = AsyncMock()
	svc = _service(
		graph_gateway=graph_gw,
		message_gateway=AsyncMock(
			get_one=AsyncMock(return_value=model_msg), message_before=AsyncMock(return_value=user_msg)
		),
		chat_settings_gateway=chat_settings_gateway,
	)

	await svc.ingest(chat_id, model_id)

	graph_gw.store.assert_awaited_once()
	args = graph_gw.store.await_args.args
	assert args[0] == chat_id
	assert "the question" in args[1]
	assert "the reply" in args[2]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_enrich_drops_chunk_that_restates_a_graph_fact(monkeypatch):
	monkeypatch.setattr(settings, "GRAPH_MEMORY_ENABLED", True)
	monkeypatch.setattr(settings, "VECTOR_MEMORY_ENABLED", True)
	monkeypatch.setattr(settings, "SUMMARY_ENABLED", False)
	chat_id = uuid4()
	fact_vec = [1.0, 0.0, 0.0, 0.0]
	other_vec = [0.0, 1.0, 0.0, 0.0]
	chunk_dup = MemoryChunk(message_id=uuid4(), role="user", content="dup of fact", distance=0.1, embedding=fact_vec)
	chunk_keep = MemoryChunk(
		message_id=uuid4(), role="model", content="unique detail", distance=0.2, embedding=other_vec
	)
	vector_gw = AsyncMock(retrieve=AsyncMock(return_value=[chunk_dup, chunk_keep]))
	graph_gw = AsyncMock(retrieve=AsyncMock(return_value=["A and B are allies."]))
	embedder = AsyncMock()
	embedder.embed = AsyncMock(return_value=[fact_vec])
	svc = _service(
		summary_gateway=AsyncMock(latest=AsyncMock(return_value=None)),
		vector_gateway=vector_gw,
		graph_gateway=graph_gw,
		message_gateway=AsyncMock(tail_after=AsyncMock(return_value=[])),
	)
	svc._embedder = embedder

	result = await svc.enrich(chat_id, "query")

	assert "unique detail" in result.sections.memories
	assert "dup of fact" not in result.sections.memories
	assert "A and B are allies." in result.sections.facts
