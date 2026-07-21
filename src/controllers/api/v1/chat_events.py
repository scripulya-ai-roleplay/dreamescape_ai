from uuid import UUID

from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, Depends, Path
from fastapi.responses import StreamingResponse

from src.application.ports import IServerEventsService
from src.controllers.api.v1.auth_dependencies import get_current_user
from src.domain.models import User

router = APIRouter(prefix="/api/v1/chats", tags=["chats"])


@router.get("/{chat_id}/events")
@inject
async def stream_chat_events(
	events_service: FromDishka[IServerEventsService],
	current_user: User = Depends(get_current_user),
	chat_id: UUID = Path(),
) -> StreamingResponse:
	user_id = current_user.id
	return await events_service.open_stream(chat_id, user_id)
