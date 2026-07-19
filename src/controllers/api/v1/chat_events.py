from uuid import UUID

from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, Depends, Path
from fastapi.responses import StreamingResponse

from src.application.ports import IServerEventsService
from src.controllers.api.v1.auth import get_current_user
from src.domain.models import User

router = APIRouter(prefix="/api/v1/chats", tags=["chats"])


@router.get("/{chat_id}/events")
@inject
async def stream_chat_events(
	events_service: FromDishka[IServerEventsService],
	current_user: User = Depends(get_current_user),
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
	user_id = current_user.id
	return await events_service.open_stream(chat_id, user_id)
