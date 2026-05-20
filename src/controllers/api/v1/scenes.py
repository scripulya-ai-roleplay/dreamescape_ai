import logging
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel


logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/v1/chats", tags=["networks"])


class SceneCreatiobDTO(BaseModel):
	owner_id: UUID
	title: str
	background_prompt: str


# TODO: got distracted by linting and test fixing. Gonnna implement aftter that
# @router.post("/")
# @inject
# async def create_scene(
# 	scene_dto: SceneCreatiobDTO,
# 	gateway_factory: FromDishka[IGatewayFactory],
# ) -> APIResponseDTO:
# 	# noinspection PyTypeChecker
# 	gateway = gateway_factory.create_gateway(user_message_dto.llm_model.value)
# 	json_data = gateway.generate_response(user_message_dto.message)
# 	return APIResponseDTO.model_validate(json_data)
