import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse

from src.application.events import server_events_service
from src.application.events.server_events_service import ServerEventsService
from src.application.ports import IChatService, IMessageService
from src.domain.models import ChatRoles, Message, MessageStatus
from src.infrastructure.gateways.chat_event_gateway import ChatEventGateway


def _model_message(chat_id, text="hi", status_=MessageStatus.COMPLETED):
	return Message(id=uuid4(), message=text, chat_id=chat_id, role=ChatRoles.MODEL, status=status_)


async def _next_frame(iterator, timeout=1.0):
	return await asyncio.wait_for(iterator.__anext__(), timeout=timeout)


async def _publish_once_subscribed(gateway, chat_id, message):
	"""Wait until the stream has subscribed for chat_id, then fan the message out."""
	while chat_id not in gateway._listeners:
		await asyncio.sleep(0)
	gateway.publish_message(chat_id, message)


def _fake_container(chat_service, message_service):
	"""A stand-in AsyncContainer whose REQUEST child scope resolves the two services.

	The scope context manager records enter/exit so tests can assert the session is
	released (scope exited) before the stream starts.
	"""
	request_container = MagicMock()
	request_container.get = AsyncMock(
		side_effect=lambda dep: {IChatService: chat_service, IMessageService: message_service}.get(dep)
	)
	scope_cm = MagicMock()
	scope_cm.__aenter__ = AsyncMock(return_value=request_container)
	scope_cm.__aexit__ = AsyncMock(return_value=None)
	container = MagicMock()
	container.return_value = scope_cm  # container(scope=Scope.REQUEST) -> scope_cm
	return container


class TestServerEventsServiceStreaming:
	"""SSE frame mechanics, driven directly through the _stream generator."""

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_emits_latest_message_as_first_reconcile_frame(self):
		chat_id = uuid4()
		gateway = ChatEventGateway()
		service = ServerEventsService(_events=gateway, _container=MagicMock())
		latest = _model_message(chat_id, text="prior reply")

		iterator = service._stream(chat_id, latest)
		first = await _next_frame(iterator)

		assert first.startswith("event: message\n")
		assert "prior reply" in first

		await iterator.aclose()
		assert gateway._listeners.get(chat_id) is None  # unsubscribed on close

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_published_completed_message_is_message_event(self):
		chat_id = uuid4()
		gateway = ChatEventGateway()
		service = ServerEventsService(_events=gateway, _container=MagicMock())
		msg = _model_message(chat_id, text="hello there")

		iterator = service._stream(chat_id, None)
		task = asyncio.create_task(_publish_once_subscribed(gateway, chat_id, msg))

		frame = await _next_frame(iterator)
		await task

		assert frame.startswith("event: message\n")
		assert "hello there" in frame

		await iterator.aclose()
		assert gateway._listeners.get(chat_id) is None

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_published_failed_message_is_error_event(self):
		chat_id = uuid4()
		gateway = ChatEventGateway()
		service = ServerEventsService(_events=gateway, _container=MagicMock())
		msg = _model_message(chat_id, text="boom", status_=MessageStatus.FAILED)

		iterator = service._stream(chat_id, None)
		task = asyncio.create_task(_publish_once_subscribed(gateway, chat_id, msg))

		frame = await _next_frame(iterator)
		await task

		assert frame.startswith("event: error\n")
		assert "boom" in frame

		await iterator.aclose()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_idle_stream_emits_keepalive_comment(self, monkeypatch):
		monkeypatch.setattr(server_events_service, "_KEEPALIVE_SECONDS", 0.05)
		chat_id = uuid4()
		service = ServerEventsService(_events=ChatEventGateway(), _container=MagicMock())

		iterator = service._stream(chat_id, None)
		frame = await _next_frame(iterator)

		assert frame == ": keepalive\n\n"

		await iterator.aclose()


class TestServerEventsServiceOpenStream:
	"""open_stream: ownership check + latest read run in a short-lived scope that
	closes before the StreamingResponse is returned."""

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_returns_streaming_response_and_closes_scope_before_streaming(self):
		chat_id = uuid4()
		user_id = uuid4()
		chat = MagicMock(user_id=user_id)
		chat_service = AsyncMock(spec=IChatService)
		chat_service.get_one.return_value = chat
		latest = _model_message(chat_id, text="prior")
		message_service = AsyncMock(spec=IMessageService)
		message_service.latest_model_message.return_value = latest

		container = _fake_container(chat_service, message_service)
		service = ServerEventsService(_events=ChatEventGateway(), _container=container)

		response = await service.open_stream(chat_id, user_id)

		assert isinstance(response, StreamingResponse)
		assert response.media_type == "text/event-stream"
		# The REQUEST scope was exited before the response was returned, i.e. the
		# AsyncSession is released before the stream body starts iterating.
		scope_cm = container.return_value
		scope_cm.__aenter__.assert_awaited_once()
		scope_cm.__aexit__.assert_awaited_once()

		first = await _next_frame(response.body_iterator)
		assert first.startswith("event: message\n")
		assert "prior" in first
		await response.body_iterator.aclose()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_raises_403_and_closes_scope_when_chat_not_owned(self):
		chat_id = uuid4()
		user_id = uuid4()
		chat = MagicMock(user_id=uuid4())  # owned by a different user
		chat_service = AsyncMock(spec=IChatService)
		chat_service.get_one.return_value = chat
		message_service = AsyncMock(spec=IMessageService)

		container = _fake_container(chat_service, message_service)
		service = ServerEventsService(_events=ChatEventGateway(), _container=container)

		with pytest.raises(HTTPException) as exc:
			await service.open_stream(chat_id, user_id)

		assert exc.value.status_code == status.HTTP_403_FORBIDDEN
		# latest is never read on the unauthorized path...
		message_service.latest_model_message.assert_not_called()
		# ...and the scope is still exited (session released) even though we raised.
		container.return_value.__aexit__.assert_awaited_once()
