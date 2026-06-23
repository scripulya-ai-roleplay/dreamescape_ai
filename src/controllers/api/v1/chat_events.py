from typing import Any, Dict
from uuid import UUID

from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, Depends, Path
from fastapi.responses import StreamingResponse

from src.application.ports import IServerEventsService
from src.infrastructure.auth.dependencies import get_current_user

router = APIRouter(prefix="/api/v1/chats", tags=["chats"])


@router.get("/{chat_id}/events")
@inject
async def stream_chat_events(
	events_service: FromDishka[IServerEventsService],
	current_user: Dict[str, Any] = Depends(get_current_user),
	chat_id: UUID = Path(),
) -> StreamingResponse:
	"""Server-Sent Events stream of model-message lifecycle events for a chat.

	The client opens this after POSTing a message; the completed/failed reply is
	pushed here when scripulya_agent answers (no polling). On connect, the latest
	model message is emitted as a `state` reconciliation frame so a client that
	connected after the reply landed (or on reconnect) can dedupe by message id.

	Ownership of the chat is verified and the latest message read inside the service;
	that DB work happens in a short-lived session that is closed before this response
	starts streaming, so the SSE connection does not pin a DB connection.
	"""
	user_id = UUID(current_user["sub"])
	return await events_service.open_stream(chat_id, user_id)
