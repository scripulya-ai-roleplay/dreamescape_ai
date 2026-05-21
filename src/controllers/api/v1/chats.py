import logging

from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter
from asgi_correlation_id.context import correlation_id

from src.application.ports import LLMResponse, UserMessageDTO, IChatsService, ApiResponse

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/v1/chats", tags=["chats"])


@router.post("/")
@inject
async def send_message(
	user_message_dto: UserMessageDTO,
	chat_service: FromDishka[IChatsService],
) -> ApiResponse[LLMResponse]:
	json_data = await chat_service.send_message(user_message_dto)
	response = LLMResponse.model_validate(json_data)

	return ApiResponse[LLMResponse](result=response, correlation_id=correlation_id.get())
