import logging
from uuid import UUID

from asgi_correlation_id import correlation_id
from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, Query, Path, Body, Depends, HTTPException

from src.application.chats.schemas import ChatFilterDTO
from src.application.ports import ApiResponse, Page, IChatService, ICharacterService
from src.domain.models import Chat, User
from src.controllers.api.v1.auth import get_current_user

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/v1/chats", tags=["chats"])


@router.post("/")
@inject
async def create_chat(
	chat_service: FromDishka[IChatService],
	character_service: FromDishka[ICharacterService],
	chat: Chat = Body(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse:
	logger.info(f"Current user payload: {current_user}")
	user_id = current_user.id
	logger.info(f"Extracted user ID: {user_id}")

	# Validate that the Chat's user_id matches the authenticated user
	if chat.user_id != user_id:
		logger.warning(f"User ID mismatch: chat.user_id={chat.user_id}, user_id={user_id}")
		raise HTTPException(status_code=403, detail="Chat user_id must match authenticated user")

	# A persona chosen at creation must be visible to the caller (same gate as
	# set_persona: no pinning another user's private character to leak its prompt).
	if chat.user_character_id is not None:
		await character_service.get_one(chat.user_character_id, user_id)

	logger.info(f"Chat object validation passed with user_id: {chat.user_id}")

	chat_id = await chat_service.start_chat(chat)
	return ApiResponse(result={"id": str(chat_id)}, correlation_id=correlation_id.get())


@router.get("/{chat_id}")
@inject
async def get_chat_details(
	chat_service: FromDishka[IChatService],
	chat_id: UUID = Path(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse[Chat]:
	result = await chat_service.get_one(chat_id, current_user.id)
	return ApiResponse(result=result, correlation_id=correlation_id.get())


@router.get("/")
@inject
async def search_chats(
	chat_service: FromDishka[IChatService],
	dto: ChatFilterDTO = Query(ChatFilterDTO()),
	current_user: User = Depends(get_current_user),
) -> ApiResponse[Page[Chat]]:
	result = await chat_service.search(dto, current_user.id)
	return ApiResponse(result=result, correlation_id=correlation_id.get())


@router.delete("/{chat_id}")
@inject
async def delete_chat(
	chat_service: FromDishka[IChatService],
	chat_id: UUID = Path(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse:
	await chat_service.delete(chat_id, current_user.id)
	return ApiResponse(result=[], correlation_id=correlation_id.get())


@router.post("/update/{chat_id}")
@inject
async def update_chat(
	chat_service: FromDishka[IChatService],
	chat_id: UUID = Path(),
	chat_name: str = Body(embed=True),
	current_user: User = Depends(get_current_user),
) -> ApiResponse:
	await chat_service.update(chat_id, chat_name, current_user.id)
	return ApiResponse(result=[], correlation_id=correlation_id.get())


@router.post("/{chat_id}/persona")
@inject
async def set_chat_persona(
	chat_service: FromDishka[IChatService],
	character_service: FromDishka[ICharacterService],
	chat_id: UUID = Path(),
	user_character_id: UUID = Body(embed=True),
	current_user: User = Depends(get_current_user),
) -> ApiResponse:
	user_id = current_user.id
	# The persona must be visible to the caller (public or owned); otherwise a user
	# could pin another user's private character and exfiltrate its prompt via the LLM.
	await character_service.get_one(user_character_id, user_id)
	await chat_service.set_persona(chat_id, user_character_id, user_id)
	return ApiResponse(result=[], correlation_id=correlation_id.get())
