import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from dishka import Scope

from src.application.memory.ingest_dispatcher import MemoryIngestDispatcher
from src.application.ports.memory import IMemoryService


def _container_with(memory_service):
	container = MagicMock()
	request_container = AsyncMock()
	request_container.get = AsyncMock(return_value=memory_service)
	scope_cm = AsyncMock()
	scope_cm.__aenter__.return_value = request_container
	scope_cm.__aexit__.return_value = None
	container.return_value = scope_cm
	return container


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_runs_ingest_in_own_request_scope():
	memory_service = AsyncMock(spec=IMemoryService)
	dispatcher = MemoryIngestDispatcher(_container=_container_with(memory_service))

	dispatcher.dispatch(uuid4(), uuid4())
	await asyncio.gather(*dispatcher._inflight)

	memory_service.ingest.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_swallows_ingest_exceptions():
	memory_service = AsyncMock(spec=IMemoryService)
	memory_service.ingest.side_effect = RuntimeError("boom")
	dispatcher = MemoryIngestDispatcher(_container=_container_with(memory_service))

	dispatcher.dispatch(uuid4(), uuid4())
	await asyncio.gather(*dispatcher._inflight)  # must not raise


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_uses_request_scope():
	memory_service = AsyncMock(spec=IMemoryService)
	container = _container_with(memory_service)
	dispatcher = MemoryIngestDispatcher(_container=container)

	dispatcher.dispatch(uuid4(), uuid4())
	await asyncio.gather(*dispatcher._inflight)

	container.assert_called_once_with(scope=Scope.REQUEST)
