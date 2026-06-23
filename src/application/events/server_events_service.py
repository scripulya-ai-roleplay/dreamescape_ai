import asyncio
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional
from uuid import UUID

from dishka import AsyncContainer, Scope
from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse

from src.application.ports import (
	IChatEventGateway,
	IChatService,
	IMessageService,
	IServerEventsService,
)
from src.domain.models import Message, MessageStatus

# How often to emit a keepalive comment on an idle stream (also bounds how long a
# queue.get() blocks before we can react to a client disconnect).
_KEEPALIVE_SECONDS = 15.0

_SSE_HEADERS = {
	"Cache-Control": "no-cache",
	"Connection": "keep-alive",
	# Hint proxies (e.g. nginx) not to buffer the stream.
	"X-Accel-Buffering": "no",
}


def _sse_frame(payload: Dict[str, Any]) -> str:
	"""Format one SSE frame. The `event:` name reflects the message status so a
	failed generation is delivered as an `error` event."""
	message = payload.get("message") or {}
	name = "error" if message.get("status") == MessageStatus.FAILED.value else "message"
	data = json.dumps(payload, ensure_ascii=False, default=str)
	return f"event: {name}\ndata: {data}\n\n"


@dataclass
class ServerEventsService(IServerEventsService):
	"""Owns the SSE streaming mechanics for a chat's message-lifecycle events.

	APP-scoped: the long-lived stream generator closes over only the APP-scoped
	event gateway + plain values, never a request-scoped DB session. The ownership
	check and latest-message read run in a manually entered REQUEST child scope that
	is exited before the StreamingResponse is returned, so the AsyncSession (and its
	DB connection) is released before the stream starts iterating. Without this,
	Dishka's ContainerMiddleware would keep the request scope — and thus the session
	— open for the entire SSE connection.
	"""

	_events: IChatEventGateway
	_container: AsyncContainer

	async def open_stream(self, chat_id: UUID, user_id: UUID) -> StreamingResponse:
		# Prepare reads run in a short-lived REQUEST scope; exiting it closes the
		# AsyncSession before the (potentially long-lived) stream body starts.
		async with self._container(scope=Scope.REQUEST) as request_container:
			chat_service = await request_container.get(IChatService)
			message_service = await request_container.get(IMessageService)

			chat = await chat_service.get_one(chat_id)
			if chat.user_id != user_id:
				raise HTTPException(
					status_code=status.HTTP_403_FORBIDDEN,
					detail="Chat does not belong to the authenticated user",
				)
			latest = await message_service.latest_model_message(chat_id)

		return StreamingResponse(
			self._stream(chat_id, latest),
			media_type="text/event-stream",
			headers=_SSE_HEADERS,
		)

	async def _stream(self, chat_id: UUID, latest: Optional[Message]):
		queue = self._events.subscribe(chat_id)
		try:
			if latest is not None:
				yield _sse_frame({"message": latest.model_dump(mode="json")})
			while True:
				try:
					event = await asyncio.wait_for(queue.get(), timeout=_KEEPALIVE_SECONDS)
				except asyncio.TimeoutError:
					yield ": keepalive\n\n"
					continue
				yield _sse_frame(event)
		finally:
			self._events.unsubscribe(chat_id, queue)
