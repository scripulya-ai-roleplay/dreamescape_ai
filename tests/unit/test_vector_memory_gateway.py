from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.infrastructure.gateways.vector_memory_gateway import PgVectorMemoryGateway


def _row(message_id, role, content, distance, dedup_distance=None, embedding=None):
	model = SimpleNamespace(message_id=message_id, role=role, content=content, embedding=embedding)
	if dedup_distance is None:
		return (model, distance)
	return (model, distance, dedup_distance)


def _gateway(rows):
	session = AsyncMock()
	select_result = MagicMock()
	select_result.all.return_value = rows
	session.execute = AsyncMock(side_effect=[MagicMock(), select_result])
	embedder = AsyncMock()
	embedder.embed = AsyncMock(return_value=[[0.1] * 4])
	return PgVectorMemoryGateway(_session=session, _embedder=embedder), session, embedder


@pytest.mark.unit
@pytest.mark.asyncio
async def test_retrieve_filters_by_max_distance():
	kept_id = uuid4()
	far_id = uuid4()
	gateway, _, _ = _gateway([_row(kept_id, "user", "near", 0.1), _row(far_id, "user", "far", 0.9)])

	chunks = await gateway.retrieve(uuid4(), "q", k=5, max_distance=0.5)

	assert [c.message_id for c in chunks] == [kept_id]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_retrieve_excludes_tail_message_ids():
	excluded = uuid4()
	other = uuid4()
	gateway, _, _ = _gateway([_row(excluded, "user", "a", 0.1), _row(other, "user", "b", 0.2)])

	chunks = await gateway.retrieve(uuid4(), "q", k=5, max_distance=0.5, exclude_message_ids={excluded})

	assert [c.message_id for c in chunks] == [other]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_retrieve_drops_chunks_too_similar_to_summary():
	keep = uuid4()
	dup = uuid4()
	gateway, _, _ = _gateway([_row(keep, "user", "unique", 0.1, 0.5), _row(dup, "user", "redundant", 0.2, 0.01)])

	chunks = await gateway.retrieve(
		uuid4(), "q", k=5, max_distance=0.5, dedup_embedding=[0.1] * 4, dedup_max_distance=0.08
	)

	assert [c.message_id for c in chunks] == [keep]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_store_embeds_and_inserts_with_conflict_nothing():
	session = AsyncMock()
	embedder = AsyncMock()
	embedder.embed = AsyncMock(return_value=[[0.5] * 4])
	gateway = PgVectorMemoryGateway(_session=session, _embedder=embedder)

	await gateway.store(uuid4(), uuid4(), "user", "content")

	embedder.embed.assert_awaited_once_with(["content"])
	session.execute.assert_awaited_once()
