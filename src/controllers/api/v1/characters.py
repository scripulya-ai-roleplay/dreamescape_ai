import logging
from uuid import UUID

from asgi_correlation_id import correlation_id
from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, Query, Path, Body, Depends, HTTPException

from src.application.character.schemas import CharacterFilterDTO
from src.application.ports import ApiResponse, Page, ICharacterService, LikeState, BookmarkState
from src.domain.models import Character, User
from src.controllers.api.v1.auth import get_current_user, get_optional_user

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/v1/characters", tags=["characters"])


@router.post("/")
@inject
async def create_character(
	character_service: FromDishka[ICharacterService],
	character: Character = Body(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse:
	logger.info(f"Current user payload: {current_user}")
	user_id = current_user.id
	logger.info(f"Extracted user ID: {user_id}")

	# Validate that the Character's owner_id matches the authenticated user
	if character.owner_id != user_id:
		logger.warning(f"Owner ID mismatch: character.owner_id={character.owner_id}, user_id={user_id}")
		raise HTTPException(status_code=403, detail="Character owner_id must match authenticated user")

	logger.info(f"Character object validation passed with owner_id: {character.owner_id}")

	await character_service.create_character(character)
	return ApiResponse(result=[], correlation_id=correlation_id.get())


@router.get("/{character_id}")
@inject
async def get_character_details(
	characters_service: FromDishka[ICharacterService],
	character_id: UUID = Path(),
	current_user: User | None = Depends(get_optional_user),
) -> ApiResponse[Character]:
	actor_id = current_user.id if current_user else None
	result = await characters_service.get_one(character_id, actor_id)
	return ApiResponse(result=result, correlation_id=correlation_id.get())


@router.get("/")
@inject
async def search_character(
	character_service: FromDishka[ICharacterService],
	dto: CharacterFilterDTO = Query(CharacterFilterDTO()),
	current_user: User | None = Depends(get_optional_user),
) -> ApiResponse[Page[Character]]:
	actor_id = current_user.id if current_user else None
	result = await character_service.search(dto, actor_id)
	return ApiResponse(result=result, correlation_id=correlation_id.get())


@router.delete("/{character_id}")
@inject
async def delete_character(
	character_service: FromDishka[ICharacterService],
	character_id: UUID = Path(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse:
	actor_id = current_user.id
	await character_service.delete(character_id, actor_id)
	return ApiResponse(result=[], correlation_id=correlation_id.get())


@router.post("/update/{character_id}")
@inject
async def update_character(
	character_service: FromDishka[ICharacterService],
	character_id: UUID = Path(),
	update_data: Character = Body(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse:
	actor_id = current_user.id
	await character_service.update(character_id, update_data, actor_id)
	return ApiResponse(result=[], correlation_id=correlation_id.get())


@router.post("/{character_id}/like")
@inject
async def like_character(
	character_service: FromDishka[ICharacterService],
	character_id: UUID = Path(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse[LikeState]:
	user_id = current_user.id
	state = await character_service.like(character_id, user_id)
	return ApiResponse(result=state, correlation_id=correlation_id.get())


@router.delete("/{character_id}/like")
@inject
async def unlike_character(
	character_service: FromDishka[ICharacterService],
	character_id: UUID = Path(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse[LikeState]:
	user_id = current_user.id
	state = await character_service.unlike(character_id, user_id)
	return ApiResponse(result=state, correlation_id=correlation_id.get())


@router.get("/{character_id}/like")
@inject
async def get_character_like_state(
	character_service: FromDishka[ICharacterService],
	character_id: UUID = Path(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse[LikeState]:
	user_id = current_user.id
	state = await character_service.get_like_state(character_id, user_id)
	return ApiResponse(result=state, correlation_id=correlation_id.get())


@router.post("/{character_id}/bookmark")
@inject
async def bookmark_character(
	character_service: FromDishka[ICharacterService],
	character_id: UUID = Path(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse[BookmarkState]:
	user_id = current_user.id
	state = await character_service.bookmark(character_id, user_id)
	return ApiResponse(result=state, correlation_id=correlation_id.get())


@router.delete("/{character_id}/bookmark")
@inject
async def unbookmark_character(
	character_service: FromDishka[ICharacterService],
	character_id: UUID = Path(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse[BookmarkState]:
	user_id = current_user.id
	state = await character_service.unbookmark(character_id, user_id)
	return ApiResponse(result=state, correlation_id=correlation_id.get())


@router.get("/{character_id}/bookmark")
@inject
async def get_character_bookmark_state(
	character_service: FromDishka[ICharacterService],
	character_id: UUID = Path(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse[BookmarkState]:
	user_id = current_user.id
	state = await character_service.get_bookmark_state(character_id, user_id)
	return ApiResponse(result=state, correlation_id=correlation_id.get())
