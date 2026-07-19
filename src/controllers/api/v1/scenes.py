import logging
from uuid import UUID
from typing import List

from asgi_correlation_id import correlation_id
from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, Query, Path, Body, Depends, HTTPException

from src.application.ports import ISceneService, ICharacterService, ApiResponse, Page, LikeState, BookmarkState
from src.application.scene.schemas import SceneFilterDTO, AttachCharactersDTO
from src.domain.models import Scene, Character, User
from src.controllers.api.v1.auth import get_current_user

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/v1/scenes", tags=["scenes"])


@router.post("/")
@inject
async def create_scene(
	scenes_service: FromDishka[ISceneService],
	scene: Scene = Body(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse:
	logger.info(f"Current user payload: {current_user}")
	user_id = current_user.id
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
	current_user: User = Depends(get_current_user),
) -> ApiResponse[LikeState]:
	user_id = current_user.id
	state = await scene_service.like(scene_id, user_id)
	return ApiResponse(result=state, correlation_id=correlation_id.get())


@router.delete("/{scene_id}/like")
@inject
async def unlike_scene(
	scene_service: FromDishka[ISceneService],
	scene_id: UUID = Path(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse[LikeState]:
	user_id = current_user.id
	state = await scene_service.unlike(scene_id, user_id)
	return ApiResponse(result=state, correlation_id=correlation_id.get())


@router.get("/{scene_id}/like")
@inject
async def get_scene_like_state(
	scene_service: FromDishka[ISceneService],
	scene_id: UUID = Path(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse[LikeState]:
	user_id = current_user.id
	state = await scene_service.get_like_state(scene_id, user_id)
	return ApiResponse(result=state, correlation_id=correlation_id.get())


@router.post("/{scene_id}/bookmark")
@inject
async def bookmark_scene(
	scene_service: FromDishka[ISceneService],
	scene_id: UUID = Path(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse[BookmarkState]:
	user_id = current_user.id
	state = await scene_service.bookmark(scene_id, user_id)
	return ApiResponse(result=state, correlation_id=correlation_id.get())


@router.delete("/{scene_id}/bookmark")
@inject
async def unbookmark_scene(
	scene_service: FromDishka[ISceneService],
	scene_id: UUID = Path(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse[BookmarkState]:
	user_id = current_user.id
	state = await scene_service.unbookmark(scene_id, user_id)
	return ApiResponse(result=state, correlation_id=correlation_id.get())


@router.get("/{scene_id}/bookmark")
@inject
async def get_scene_bookmark_state(
	scene_service: FromDishka[ISceneService],
	scene_id: UUID = Path(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse[BookmarkState]:
	user_id = current_user.id
	state = await scene_service.get_bookmark_state(scene_id, user_id)
	return ApiResponse(result=state, correlation_id=correlation_id.get())


@router.post("/{scene_id}/characters")
@inject
async def attach_characters_to_scene(
	scene_service: FromDishka[ISceneService],
	character_service: FromDishka[ICharacterService],
	scene_id: UUID = Path(),
	dto: AttachCharactersDTO = Body(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse:
	user_id = current_user.id

	# Attaching mutates the scene every chat in it sees, so (unlike a personal
	# like/bookmark) only the owner may change which characters belong to it.
	scene = await scene_service.get_one(scene_id)
	if scene.owner_id != user_id:
		raise HTTPException(status_code=403, detail="Only the scene owner can attach characters")

	# Resolve + authorize each character before the INSERT: missing → 404 (not an
	# FK 500), and a private non-owned character is 403 (it would leak via chats).
	for character_id in dto.character_ids:
		character = await character_service.get_one(character_id)
		if not character.is_public and character.owner_id != user_id:
			raise HTTPException(status_code=403, detail="Not allowed to attach this character")

	await scene_service.attach_characters(scene_id, dto.character_ids)
	return ApiResponse(result=[], correlation_id=correlation_id.get())


@router.get("/{scene_id}/characters")
@inject
async def get_scene_characters(
	scene_service: FromDishka[ISceneService],
	character_service: FromDishka[ICharacterService],
	scene_id: UUID = Path(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse[List[Character]]:
	user_id = current_user.id
	await scene_service.get_one(scene_id)
	characters = await character_service.get_for_scene(scene_id, actor_id=user_id)
	return ApiResponse(result=characters, correlation_id=correlation_id.get())
