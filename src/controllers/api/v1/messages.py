import logging
from uuid import UUID

from asgi_correlation_id import correlation_id
from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, Query, Path, Body, Depends, status
from pydantic import BaseModel, ConfigDict

from src.application.ports.llm import LLMModelType, UserMessageDTO
from src.application.message.schemas import MessagesFilterDto
from src.application.ports.common import ApiResponse, Page
from src.application.ports.messages import IMessageService
from src.application.ports.chats import IChatsService
from src.domain.models import ChatRoles, Message, User
from src.controllers.api.v1.auth_dependencies import get_current_user

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/v1/messages", tags=["messages"])


class SendMessageRequest(BaseModel):
	model_config = ConfigDict(extra="forbid")

	chat_id: UUID
	message: str
	llm_model: LLMModelType | None = LLMModelType.testing_mock


@router.post("/", status_code=status.HTTP_202_ACCEPTED)
@inject
async def create_message(
	llm_service: FromDishka[IChatsService],
	payload: SendMessageRequest = Body(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse[Message]:
	logger.info(f"Creating message for chat: {payload.chat_id}")
	message = UserMessageDTO(
		chat_id=payload.chat_id,
		message=payload.message,
		llm_model=payload.llm_model,
		role=ChatRoles.USER,
	)
	result = await llm_service.send_message(message, current_user.id)
	return ApiResponse(result=result, correlation_id=correlation_id.get())


@router.get("/{message_id}")
@inject
async def get_message_details(
	message_service: FromDishka[IMessageService],
	message_id: UUID = Path(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse[Message]:
	result = await message_service.get_one(message_id, current_user.id)
	return ApiResponse(result=result, correlation_id=correlation_id.get())


@router.get("/")
@inject
async def search_messages(
	message_service: FromDishka[IMessageService],
	dto: MessagesFilterDto = Query(MessagesFilterDto()),
	current_user: User = Depends(get_current_user),
) -> ApiResponse[Page[Message]]:
	result = await message_service.search(dto, current_user.id)
	return ApiResponse(result=result, correlation_id=correlation_id.get())


@router.put("/{message_id}")
@inject
async def update_message(
	message_service: FromDishka[IMessageService],
	message_id: UUID = Path(),
	updated_text: str = Body(embed=True),
	current_user: User = Depends(get_current_user),
) -> ApiResponse:
	await message_service.update(message_id, updated_text, current_user.id)
	return ApiResponse(result=[], correlation_id=correlation_id.get())


@router.delete("/{message_id}")
@inject
async def delete_message(
	message_service: FromDishka[IMessageService],
	message_id: UUID = Path(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse:
	await message_service.delete(message_id, current_user.id)
	return ApiResponse(result=[], correlation_id=correlation_id.get())
