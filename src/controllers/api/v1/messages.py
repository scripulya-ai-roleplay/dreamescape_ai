import logging
from uuid import UUID
from typing import Dict, Any

from asgi_correlation_id import correlation_id
from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, Query, Path, Body, Depends, status

from src.application.ports import UserMessageDTO
from src.application.message.schemas import MessagesFilterDto
from src.application.ports import ApiResponse, Page, IMessageService, IChatsService, SendMessageResult
from src.domain.models import Message
from src.infrastructure.auth.dependencies import get_current_user

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/v1/messages", tags=["messages"])


@router.post("/", status_code=status.HTTP_202_ACCEPTED)
@inject
async def create_message(
	llm_service: FromDishka[IChatsService],
	message: UserMessageDTO = Body(),
	current_user: Dict[str, Any] = Depends(get_current_user),
) -> ApiResponse[SendMessageResult]:
	logger.info(f"Current user payload: {current_user}")
	user_id = UUID(current_user["sub"])
	logger.info(f"Extracted user ID: {user_id}")

	# The service persists both the user message and a PENDING placeholder model
	# message, then publishes the request to scripulya_agent (or resolves inline
	# for testing_mock) and returns immediately. The finished reply is delivered
	# to the client via the chat SSE stream (GET /api/v1/chats/{chat_id}/events).
	logger.info(f"Creating message for chat: {message.chat_id}")
	result = await llm_service.send_message(message)
	return ApiResponse(result=result, correlation_id=correlation_id.get())


@router.get("/{message_id}")
@inject
async def get_message_details(
	message_service: FromDishka[IMessageService], message_id: UUID = Path()
) -> ApiResponse[Message]:
	result = await message_service.get_one(message_id)
	return ApiResponse(result=result, correlation_id=correlation_id.get())


@router.get("/")
@inject
async def search_messages(
	message_service: FromDishka[IMessageService], dto: MessagesFilterDto = Query(MessagesFilterDto())
) -> ApiResponse[Page[Message]]:
	result = await message_service.search(dto)
	return ApiResponse(result=result, correlation_id=correlation_id.get())


@router.put("/{message_id}")
@inject
async def update_message(
	message_service: FromDishka[IMessageService],
	message_id: UUID = Path(),
	updated_text: str = Body(embed=True),
) -> ApiResponse:
	await message_service.update(message_id, updated_text)
	return ApiResponse(result=[], correlation_id=correlation_id.get())


@router.delete("/{message_id}")
@inject
async def delete_message(message_service: FromDishka[IMessageService], message_id: UUID = Path()) -> ApiResponse:
	await message_service.delete(message_id)
	return ApiResponse(result=[], correlation_id=correlation_id.get())
