import logging
from uuid import UUID

from asgi_correlation_id import correlation_id
from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, Body, Depends, Path
from pydantic import BaseModel, Field

from src.application.ports.chats import IChatService
from src.application.ports.common import ApiResponse
from src.application.ports.memory import IMemoryControlService
from src.controllers.api.v1.auth_dependencies import get_current_user
from src.domain.models import ConversationSummary, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chats", tags=["memory"])


async def _assert_chat_owner(chat_service: IChatService, chat_id: UUID, user_id: UUID) -> None:
	await chat_service.get_one(chat_id, user_id)


class SummaryEditBody(BaseModel):
	content: str = Field(min_length=1)


@router.get("/{chat_id}/summary")
@inject
async def get_summary(
	chat_service: FromDishka[IChatService],
	memory_control: FromDishka[IMemoryControlService],
	chat_id: UUID = Path(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse[ConversationSummary | None]:
	await _assert_chat_owner(chat_service, chat_id, current_user.id)
	summary = await memory_control.current_summary(chat_id, current_user.id)
	return ApiResponse(result=summary, correlation_id=correlation_id.get())


@router.put("/{chat_id}/summary")
@inject
async def set_summary(
	chat_service: FromDishka[IChatService],
	memory_control: FromDishka[IMemoryControlService],
	chat_id: UUID = Path(),
	body: SummaryEditBody = Body(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse[ConversationSummary]:
	await _assert_chat_owner(chat_service, chat_id, current_user.id)
	summary = await memory_control.set_summary(chat_id, body.content, current_user.id)
	return ApiResponse(result=summary, correlation_id=correlation_id.get())


@router.get("/{chat_id}/context-usage")
@inject
async def get_context_usage(
	chat_service: FromDishka[IChatService],
	memory_control: FromDishka[IMemoryControlService],
	chat_id: UUID = Path(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse[dict]:
	await _assert_chat_owner(chat_service, chat_id, current_user.id)
	usage = await memory_control.context_usage(chat_id, current_user.id)
	return ApiResponse(result=usage, correlation_id=correlation_id.get())
