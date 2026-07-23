from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.application.streaming.llm_watchdog import GenerationWatchdog
from src.domain.models import ChatRoles, Message, MessageStatus


def _fake_container(message_service):
	"""Stand-in AsyncContainer whose REQUEST child scope resolves IMessageService.

	container(scope=Scope.REQUEST) -> async cm -> request_container.get(IMessageService)."""
	request_container = MagicMock()
	request_container.get = AsyncMock(return_value=message_service)
	scope_cm = MagicMock()
	scope_cm.__aenter__ = AsyncMock(return_value=request_container)
	scope_cm.__aexit__ = AsyncMock(return_value=None)
	container = MagicMock()
	container.return_value = scope_cm
	return container


@pytest.mark.unit
class TestGenerationWatchdog:
	@pytest.mark.asyncio
	async def test_sweep_materializes_failed_and_emits_sse(self):
		chat_id = uuid4()
		heartbeat = AsyncMock()
		heartbeat.sweep_dead.return_value = [("rid", chat_id)]
		events = MagicMock()
		failed = Message(
			id=uuid4(), message="timed out", chat_id=chat_id, role=ChatRoles.MODEL, status=MessageStatus.FAILED
		)
		message_service = AsyncMock()
		message_service.record_failed_generation.return_value = failed

		watchdog = GenerationWatchdog(
			_heartbeat=heartbeat, _events=events, _container=_fake_container(message_service), logger=MagicMock()
		)

		await watchdog.sweep_once()

		heartbeat.sweep_dead.assert_awaited_once()
		args, _ = message_service.record_failed_generation.await_args
		assert args[0] == chat_id
		events.publish_message.assert_called_once_with(chat_id, failed)

	@pytest.mark.asyncio
	async def test_sweep_with_no_dead_does_nothing(self):
		heartbeat = AsyncMock()
		heartbeat.sweep_dead.return_value = []
		events = MagicMock()
		message_service = AsyncMock()

		watchdog = GenerationWatchdog(
			_heartbeat=heartbeat, _events=events, _container=_fake_container(message_service), logger=MagicMock()
		)

		await watchdog.sweep_once()

		message_service.record_failed_generation.assert_not_awaited()
		events.publish_message.assert_not_called()

	@pytest.mark.asyncio
	async def test_failure_to_materialize_one_does_not_abort_the_rest(self):
		chat_a, chat_b = uuid4(), uuid4()
		heartbeat = AsyncMock()
		heartbeat.sweep_dead.return_value = [("a", chat_a), ("b", chat_b)]
		events = MagicMock()
		failed_b = Message(id=uuid4(), message="ok", chat_id=chat_b, role=ChatRoles.MODEL, status=MessageStatus.FAILED)
		message_service = AsyncMock()
		# First call (chat_a) blows up, second (chat_b) succeeds.
		message_service.record_failed_generation.side_effect = [RuntimeError("db down"), failed_b]

		watchdog = GenerationWatchdog(
			_heartbeat=heartbeat, _events=events, _container=_fake_container(message_service), logger=MagicMock()
		)

		await watchdog.sweep_once()  # must not raise

		assert message_service.record_failed_generation.await_count == 2
		events.publish_message.assert_called_once_with(chat_b, failed_b)
