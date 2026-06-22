import asyncio
import json
import logging
from typing import Any, Dict
from uuid import UUID

from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, Depends, HTTPException, Path, status
from fastapi.responses import StreamingResponse

from src.application.ports import IChatService, IMessageService
from src.domain.models import MessageStatus
from src.infrastructure.auth.dependencies import get_current_user
from src.infrastructure.web.chat_event_broker import ChatEventBroker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chats", tags=["chats"])

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


@router.get("/{chat_id}/events")
@inject
async def stream_chat_events(
	chat_service: FromDishka[IChatService],
	message_service: FromDishka[IMessageService],
	events: FromDishka[ChatEventBroker],
	current_user: Dict[str, Any] = Depends(get_current_user),
	chat_id: UUID = Path(),
) -> StreamingResponse:
	"""Server-Sent Events stream of model-message lifecycle events for a chat.

	The client opens this after POSTing a message; the completed/failed reply is
	pushed here when scripulya_agent answers (no polling). On connect, the latest
	model message is emitted as a `state` reconciliation frame so a client that
	connected after the reply landed (or on reconnect) can dedupe by message id.
	"""
	user_id = UUID(current_user["sub"])
	chat = await chat_service.get_one(chat_id)
	if chat.user_id != user_id:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN, detail="Chat does not belong to the authenticated user"
		)

	# Reconcile read happens before streaming so we don't hold a DB session for the
	# (potentially long-lived) stream duration.
	latest = await message_service.latest_model_message(chat_id)

	async def event_stream():
		queue = events.subscribe(chat_id)
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
			events.unsubscribe(chat_id, queue)

	return StreamingResponse(event_stream(), media_type="text/event-stream", headers=_SSE_HEADERS)
