import logging
from uuid import UUID

from asgi_correlation_id import correlation_id
from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, Path, Body, Depends, HTTPException

from src.application.chats.settings import ChatSettings
from src.application.ports import ApiResponse, IChatService, IChatSettingsService
from src.controllers.api.v1.auth import get_current_user
from src.domain.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chats", tags=["chat-settings"])


async def _assert_chat_owner(chat_service: IChatService, chat_id: UUID, user_id: UUID) -> None:
	"""Confirm the chat belongs to user_id (403 otherwise, 404 if missing)."""
	await chat_service.get_one(chat_id, user_id)


@router.put("/{chat_id}/settings")
@inject
async def upsert_chat_settings(
	chat_service: FromDishka[IChatService],
	settings_service: FromDishka[IChatSettingsService],
	chat_id: UUID = Path(),
	settings: ChatSettings = Body(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse[ChatSettings]:
	user_id = current_user.id
	await _assert_chat_owner(chat_service, chat_id, user_id)
	result = await settings_service.upsert(chat_id, settings)
	return ApiResponse(result=result, correlation_id=correlation_id.get())


@router.get("/{chat_id}/settings")
@inject
async def get_chat_settings(
	chat_service: FromDishka[IChatService],
	settings_service: FromDishka[IChatSettingsService],
	chat_id: UUID = Path(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse[ChatSettings]:
	user_id = current_user.id
	await _assert_chat_owner(chat_service, chat_id, user_id)
	settings = await settings_service.get_for_chat(chat_id)
	if settings is None:
		raise HTTPException(status_code=404, detail="No settings configured for this chat")
	return ApiResponse(result=settings, correlation_id=correlation_id.get())
