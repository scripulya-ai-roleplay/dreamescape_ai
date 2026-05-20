import logging
from uuid import UUID

from asgi_correlation_id import correlation_id
from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, Query, Path, Body

from src.application.ports import ISceneService, ApiResponse, Page
from src.application.scene.schemas import SceneFilterDTO
from src.domain.models import Scene

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/v1/scenes", tags=["scenes"])


@router.post("/")
@inject
async def create_scene(
	scenes_service: FromDishka[ISceneService],
	scene: Scene = Body(),
) -> ApiResponse:
	# noinspection PyTypeChecker
	await scenes_service.create_scene(scene)
	return ApiResponse(result=[], correlation_id=correlation_id.get())


@router.get("/{scene_id}")
@inject
async def get_scene_details(scenes_service: FromDishka[ISceneService], scene_uuid: UUID = Path()) -> ApiResponse[Scene]:
	result = await scenes_service.get_one(scene_uuid)
	return ApiResponse(result=result, correlation_id=correlation_id.get())


@router.get("/")
@inject
async def search_scene(
	scene_service: FromDishka[ISceneService], dto: SceneFilterDTO = Query(SceneFilterDTO())
) -> ApiResponse[Page[Scene]]:
	result = await scene_service.search(dto)
	return ApiResponse(result=result, correlation_id=correlation_id.get())


@router.delete("/{scene_id}")
@inject
async def delete_scene(scene_service: FromDishka[ISceneService], uuid: UUID = Path()) -> ApiResponse:
	await scene_service.delete(uuid)
	return ApiResponse(result=[], correlation_id=correlation_id.get())


@router.post("/update/{scene_id}")
@inject
async def update_scene(
	scene_service: FromDishka[ISceneService],
	uuid: UUID = Path(),
	update_data: Scene = Body(),
) -> ApiResponse:
	await scene_service.update(uuid, update_data)
	return ApiResponse(result=[], correlation_id=correlation_id.get())
