from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.application.memory.graph_entities import ENTITY_TYPES
from src.infrastructure.gateways.graphiti_memory_gateway import GraphitiMemoryGateway


def _edge(fact, invalid_at=None, expired_at=None):
	return SimpleNamespace(fact=fact, invalid_at=invalid_at, expired_at=expired_at)


def _gateway(graphiti):
	return GraphitiMemoryGateway(_graphiti=graphiti)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_store_adds_episode_with_chat_group_id_and_entity_types():
	graphiti = AsyncMock()
	gateway = _gateway(graphiti)

	await gateway.store(uuid4(), "I hid the key.", "Where?", datetime.now(UTC))

	kwargs = graphiti.add_episode.await_args.kwargs
	assert "I hid the key." in kwargs["episode_body"]
	assert "Where?" in kwargs["episode_body"]
	assert kwargs["entity_types"] is ENTITY_TYPES


@pytest.mark.unit
@pytest.mark.asyncio
async def test_retrieve_returns_only_current_facts_and_caps_count(monkeypatch):
	from src.conf import settings

	monkeypatch.setattr(settings, "GRAPH_MEMORY_MAX_FACTS", 3)
	graphiti = AsyncMock()
	graphiti.search = AsyncMock(
		return_value=[
			_edge("current fact one"),
			_edge("current fact two"),
			_edge("stale fact", invalid_at=datetime.now(UTC)),
			_edge("expired fact", expired_at=datetime.now(UTC)),
			_edge("current fact three"),
			_edge("current fact four"),
		]
	)
	gateway = _gateway(graphiti)

	facts = await gateway.retrieve(uuid4(), "query")

	assert facts == ["current fact one", "current fact two", "current fact three"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_group_runs_detach_delete_cypher():
	graphiti = AsyncMock()
	graphiti.driver.execute_query = AsyncMock()
	gateway = _gateway(graphiti)

	chat_id = uuid4()
	await gateway.delete_group(chat_id)

	graphiti.driver.execute_query.assert_awaited_once()
	args, kwargs = graphiti.driver.execute_query.await_args
	assert "DETACH DELETE" in args[0]
	assert kwargs["group_id"] == str(chat_id)
