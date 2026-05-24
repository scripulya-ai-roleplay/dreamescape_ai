import logging
from uuid import UUID
from typing import Dict, Any

from asgi_correlation_id import correlation_id
from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, Query, Path, Body, Depends, HTTPException

from src.application.chats.schemas import ChatFilterDTO
from src.application.ports import ApiResponse, Page, IChatService
from src.domain.models import Chat
from src.infrastructure.auth.dependencies import get_current_user

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/v1/chats", tags=["chats"])


@router.post("/")
@inject
async def create_chat(
	chat_service: FromDishka[IChatService],
	chat: Chat = Body(),
	current_user: Dict[str, Any] = Depends(get_current_user),
) -> ApiResponse:
	logger.info(f"Current user payload: {current_user}")
	user_id = UUID(current_user["sub"])
	logger.info(f"Extracted user ID: {user_id}")

	# Validate that the Chat's user_id matches the authenticated user
	if chat.user_id != user_id:
		logger.warning(f"User ID mismatch: chat.user_id={chat.user_id}, user_id={user_id}")
		raise HTTPException(status_code=403, detail="Chat user_id must match authenticated user")

	logger.info(f"Chat object validation passed with user_id: {chat.user_id}")

	chat_id = await chat_service.start_chat(chat)
	return ApiResponse(result={"id": str(chat_id)}, correlation_id=correlation_id.get())


@router.get("/{chat_id}")
@inject
async def get_chat_details(chat_service: FromDishka[IChatService], chat_id: UUID = Path()) -> ApiResponse[Chat]:
	result = await chat_service.get_one(chat_id)
	return ApiResponse(result=result, correlation_id=correlation_id.get())


@router.get("/")
@inject
async def search_chats(
	chat_service: FromDishka[IChatService], dto: ChatFilterDTO = Query(ChatFilterDTO())
) -> ApiResponse[Page[Chat]]:
	result = await chat_service.search(dto)
	return ApiResponse(result=result, correlation_id=correlation_id.get())


@router.delete("/{chat_id}")
@inject
async def delete_chat(chat_service: FromDishka[IChatService], chat_id: UUID = Path()) -> ApiResponse:
	await chat_service.delete(chat_id)
	return ApiResponse(result=[], correlation_id=correlation_id.get())


@router.post("/update/{chat_id}")
@inject
async def update_chat(
	chat_service: FromDishka[IChatService],
	chat_id: UUID = Path(),
	chat_name: str = Body(embed=True),
) -> ApiResponse:
	await chat_service.update(chat_id, chat_name)
	return ApiResponse(result=[], correlation_id=correlation_id.get())
