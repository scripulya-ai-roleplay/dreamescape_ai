import asyncio
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional
from uuid import UUID

from dishka import AsyncContainer, Scope
from fastapi.responses import StreamingResponse

from src.application.ports import (
	IChatEventGateway,
	IChatService,
	IMessageService,
	IServerEventsService,
)
from src.domain.models import Message

_KEEPALIVE_SECONDS = 15.0

_SSE_HEADERS = {
	"Cache-Control": "no-cache",
	"Connection": "keep-alive",
	# Hint proxies (e.g. nginx) not to buffer the stream.
	"X-Accel-Buffering": "no",
}


@dataclass
class ServerEventsService(IServerEventsService):
	_events: IChatEventGateway
	_container: AsyncContainer

	def _sse_frame(self, payload: Dict[str, Any]) -> str:
		# Always emit on the standard "message" channel. A failed generation still
		# arrives as a chat message (status=failed is in the payload), so the client
		# can render it. Using the SSE event name "error" collided with EventSource's
		# reserved connection-error event: clients listening for "message" silently
		# dropped failed replies and the UI waited forever on provider errors.
		data = json.dumps(payload, ensure_ascii=False, default=str)
		return f"event: message\ndata: {data}\n\n"

	async def open_stream(self, chat_id: UUID, user_id: UUID) -> StreamingResponse:

		async with self._container(scope=Scope.REQUEST) as request_container:
			chat_service = await request_container.get(IChatService)
			message_service = await request_container.get(IMessageService)

			# get_one 404s if the chat is missing and 403s unless it belongs to user_id.
			await chat_service.get_one(chat_id, user_id)
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
				yield self._sse_frame({"message": latest.model_dump(mode="json")})
			while True:
				try:
					event = await asyncio.wait_for(queue.get(), timeout=_KEEPALIVE_SECONDS)
				except asyncio.TimeoutError:
					yield ": keepalive\n\n"
					continue
				yield self._sse_frame(event)
		finally:
			self._events.unsubscribe(chat_id, queue)
