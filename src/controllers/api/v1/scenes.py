import logging
from uuid import UUID

from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter
from pydantic import BaseModel

from src.application.ports import IGatewayFactory

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/v1/chats", tags=["networks"]
)


class SceneCreatiobDTO(BaseModel):
    owner_id: UUID
    title: str
    background_prompt: str


@router.post("/")
@inject
async def create_scene(
    scene_dto: SceneCreatiobDTO,
    gateway_factory: FromDishka[IGatewayFactory],
) -> APIResponseDTO:
    # noinspection PyTypeChecker
    gateway = gateway_factory.create_gateway(user_message_dto.llm_model.value)
    json_data = gateway.generate_response(user_message_dto.message)
    return APIResponseDTO.model_validate(json_data)
