import logging
from uuid import UUID
from typing import Dict, Any

from asgi_correlation_id import correlation_id
from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, Query, Path, Body, Depends, HTTPException

from src.application.ports import ISceneService, ApiResponse, Page, LikeState, BookmarkState
from src.application.scene.schemas import SceneFilterDTO
from src.domain.models import Scene
from src.infrastructure.auth.dependencies import get_current_user

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/v1/scenes", tags=["scenes"])


@router.post("/")
@inject
async def create_scene(
	scenes_service: FromDishka[ISceneService],
	scene: Scene = Body(),
	current_user: Dict[str, Any] = Depends(get_current_user),
) -> ApiResponse:
	logger.info(f"Current user payload: {current_user}")
	user_id = UUID(current_user["sub"])
	logger.info(f"Extracted user ID: {user_id}")

	# Debug: Log the received scene object
	logger.info(f"Received scene object: {scene}")
	logger.info(f"Scene title: {scene.title}")
	logger.info(f"Scene background_prompt: {scene.background_prompt}")
	logger.info(f"Scene initial_message_text: {scene.initial_message_text}")
	logger.info(f"Scene owner_id: {scene.owner_id}")

	# Validate that the Scene's owner_id matches the authenticated user
	if scene.owner_id != user_id:
		logger.warning(f"Owner ID mismatch: scene.owner_id={scene.owner_id}, user_id={user_id}")
		raise HTTPException(status_code=403, detail="Scene owner_id must match authenticated user")

	logger.info(f"Scene object validation passed with owner_id: {scene.owner_id}")

	await scenes_service.create_scene(scene)
	return ApiResponse(result=[], correlation_id=correlation_id.get())


@router.get("/{scene_id}")
@inject
async def get_scene_details(scenes_service: FromDishka[ISceneService], scene_id: UUID = Path()) -> ApiResponse[Scene]:
	result = await scenes_service.get_one(scene_id)
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
async def delete_scene(scene_service: FromDishka[ISceneService], scene_id: UUID = Path()) -> ApiResponse:
	await scene_service.delete(scene_id)
	return ApiResponse(result=[], correlation_id=correlation_id.get())


@router.post("/update/{scene_id}")
@inject
async def update_scene(
	scene_service: FromDishka[ISceneService],
	scene_id: UUID = Path(),
	update_data: Scene = Body(),
) -> ApiResponse:
	await scene_service.update(scene_id, update_data)
	return ApiResponse(result=[], correlation_id=correlation_id.get())


@router.post("/{scene_id}/like")
@inject
async def like_scene(
	scene_service: FromDishka[ISceneService],
	scene_id: UUID = Path(),
	current_user: Dict[str, Any] = Depends(get_current_user),
) -> ApiResponse[LikeState]:
	user_id = UUID(current_user["sub"])
	state = await scene_service.like(scene_id, user_id)
	return ApiResponse(result=state, correlation_id=correlation_id.get())


@router.delete("/{scene_id}/like")
@inject
async def unlike_scene(
	scene_service: FromDishka[ISceneService],
	scene_id: UUID = Path(),
	current_user: Dict[str, Any] = Depends(get_current_user),
) -> ApiResponse[LikeState]:
	user_id = UUID(current_user["sub"])
	state = await scene_service.unlike(scene_id, user_id)
	return ApiResponse(result=state, correlation_id=correlation_id.get())


@router.get("/{scene_id}/like")
@inject
async def get_scene_like_state(
	scene_service: FromDishka[ISceneService],
	scene_id: UUID = Path(),
	current_user: Dict[str, Any] = Depends(get_current_user),
) -> ApiResponse[LikeState]:
	user_id = UUID(current_user["sub"])
	state = await scene_service.get_like_state(scene_id, user_id)
	return ApiResponse(result=state, correlation_id=correlation_id.get())


@router.post("/{scene_id}/bookmark")
@inject
async def bookmark_scene(
	scene_service: FromDishka[ISceneService],
	scene_id: UUID = Path(),
	current_user: Dict[str, Any] = Depends(get_current_user),
) -> ApiResponse[BookmarkState]:
	user_id = UUID(current_user["sub"])
	state = await scene_service.bookmark(scene_id, user_id)
	return ApiResponse(result=state, correlation_id=correlation_id.get())


@router.delete("/{scene_id}/bookmark")
@inject
async def unbookmark_scene(
	scene_service: FromDishka[ISceneService],
	scene_id: UUID = Path(),
	current_user: Dict[str, Any] = Depends(get_current_user),
) -> ApiResponse[BookmarkState]:
	user_id = UUID(current_user["sub"])
	state = await scene_service.unbookmark(scene_id, user_id)
	return ApiResponse(result=state, correlation_id=correlation_id.get())


@router.get("/{scene_id}/bookmark")
@inject
async def get_scene_bookmark_state(
	scene_service: FromDishka[ISceneService],
	scene_id: UUID = Path(),
	current_user: Dict[str, Any] = Depends(get_current_user),
) -> ApiResponse[BookmarkState]:
	user_id = UUID(current_user["sub"])
	state = await scene_service.get_bookmark_state(scene_id, user_id)
	return ApiResponse(result=state, correlation_id=correlation_id.get())
