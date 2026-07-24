import logging
from uuid import UUID
from typing import List

from asgi_correlation_id import correlation_id
from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, Query, Path, Body, Depends, HTTPException

from src.application.ports.scenes import ISceneService, IInitialMessageService
from src.application.ports.characters import ICharacterService
from src.application.ports.common import ApiResponse, Page, LikeState, BookmarkState
from src.application.scene.schemas import SceneFilterDTO, AttachCharactersDTO
from src.domain.models import Scene, Character, InitialMessage, User
from src.controllers.api.v1.auth_dependencies import get_current_user, get_optional_user
from src.infrastructure.logging.redact import preview

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/v1/scenes", tags=["scenes"])


@router.post("/")
@inject
async def create_scene(
	scenes_service: FromDishka[ISceneService],
	scene: Scene = Body(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse:
	user_id = current_user.id

	if logger.isEnabledFor(logging.DEBUG):
		logger.debug(
			"create_scene user=%s role=%s title=%r background_prompt=%r initial_messages=%d",
			current_user.id,
			current_user.role,
			preview(scene.title),
			preview(scene.background_prompt),
			len(scene.initial_messages),
		)

	# Validate that the Scene's owner_id matches the authenticated user
	if scene.owner_id != user_id:
		logger.warning(f"Owner ID mismatch: scene.owner_id={scene.owner_id}, user_id={user_id}")
		raise HTTPException(status_code=403, detail="Scene owner_id must match authenticated user")

	await scenes_service.create_scene(scene)
	return ApiResponse(result=[], correlation_id=correlation_id.get())


@router.get("/{scene_id}")
@inject
async def get_scene_details(
	scenes_service: FromDishka[ISceneService],
	scene_id: UUID = Path(),
	current_user: User | None = Depends(get_optional_user),
) -> ApiResponse[Scene]:
	actor_id = current_user.id if current_user else None
	result = await scenes_service.get_one(scene_id, actor_id)
	return ApiResponse(result=result, correlation_id=correlation_id.get())


@router.get("/")
@inject
async def search_scene(
	scene_service: FromDishka[ISceneService],
	dto: SceneFilterDTO = Query(SceneFilterDTO()),
	current_user: User | None = Depends(get_optional_user),
) -> ApiResponse[Page[Scene]]:
	actor_id = current_user.id if current_user else None
	result = await scene_service.search(dto, actor_id)
	return ApiResponse(result=result, correlation_id=correlation_id.get())


@router.delete("/{scene_id}")
@inject
async def delete_scene(
	scene_service: FromDishka[ISceneService],
	scene_id: UUID = Path(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse:
	actor_id = current_user.id
	await scene_service.delete(scene_id, actor_id)
	return ApiResponse(result=[], correlation_id=correlation_id.get())


@router.post("/update/{scene_id}")
@inject
async def update_scene(
	scene_service: FromDishka[ISceneService],
	scene_id: UUID = Path(),
	update_data: Scene = Body(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse:
	actor_id = current_user.id
	await scene_service.update(scene_id, update_data, actor_id)
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
	# Attach mutates the scene: get_one permits public reads, but only the owner may edit.
	scene = await scene_service.get_one(scene_id, user_id)
	if scene.owner_id != user_id:
		raise HTTPException(status_code=403, detail="Only the scene owner can attach characters")
	for character_id in dto.character_ids:
		await character_service.get_one(character_id, user_id)

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
	await scene_service.get_one(scene_id, user_id)
	characters = await character_service.get_for_scene(scene_id, actor_id=user_id)
	return ApiResponse(result=characters, correlation_id=correlation_id.get())


@router.get("/{scene_id}/initial-messages")
@inject
async def get_scene_initial_messages(
	initial_message_service: FromDishka[IInitialMessageService],
	scene_id: UUID = Path(),
	current_user: User | None = Depends(get_optional_user),
) -> ApiResponse[List[InitialMessage]]:
	actor_id = current_user.id if current_user else None
	result = await initial_message_service.list_for_scene(scene_id, actor_id)
	return ApiResponse(result=result, correlation_id=correlation_id.get())


@router.put("/{scene_id}/initial-messages/{initial_message_id}")
@inject
async def update_scene_initial_message(
	initial_message_service: FromDishka[IInitialMessageService],
	scene_id: UUID = Path(),
	initial_message_id: UUID = Path(),
	updated_text: str = Body(embed=True),
	current_user: User = Depends(get_current_user),
) -> ApiResponse:
	await initial_message_service.update(initial_message_id, updated_text, current_user.id)
	return ApiResponse(result=[], correlation_id=correlation_id.get())


@router.delete("/{scene_id}/initial-messages/{initial_message_id}")
@inject
async def delete_scene_initial_message(
	initial_message_service: FromDishka[IInitialMessageService],
	scene_id: UUID = Path(),
	initial_message_id: UUID = Path(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse:
	await initial_message_service.delete(initial_message_id, current_user.id)
	return ApiResponse(result=[], correlation_id=correlation_id.get())
