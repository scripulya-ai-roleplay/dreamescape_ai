import logging
from uuid import UUID
from typing import Dict, Any

from asgi_correlation_id import correlation_id
from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, Query, Path, Body, Depends, HTTPException

from src.application.character.schemas import CharacterFilterDTO
from src.application.ports import ApiResponse, Page, ICharacterService
from src.domain.models import Character
from src.infrastructure.auth.dependencies import get_current_user

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/v1/characters", tags=["characters"])


@router.post("/")
@inject
async def create_character(
	character_service: FromDishka[ICharacterService],
	character: Character = Body(),
	current_user: Dict[str, Any] = Depends(get_current_user),
) -> ApiResponse:
	logger.info(f"Current user payload: {current_user}")
	user_id = UUID(current_user["sub"])
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
	characters_service: FromDishka[ICharacterService], character_id: UUID = Path()
) -> ApiResponse[Character]:
	result = await characters_service.get_one(character_id)
	return ApiResponse(result=result, correlation_id=correlation_id.get())


@router.get("/")
@inject
async def search_character(
	character_service: FromDishka[ICharacterService], dto: CharacterFilterDTO = Query(CharacterFilterDTO())
) -> ApiResponse[Page[Character]]:
	result = await character_service.search(dto)
	return ApiResponse(result=result, correlation_id=correlation_id.get())


@router.delete("/{character_id}")
@inject
async def delete_character(
	character_service: FromDishka[ICharacterService], character_id: UUID = Path()
) -> ApiResponse:
	await character_service.delete(character_id)
	return ApiResponse(result=[], correlation_id=correlation_id.get())


@router.post("/update/{character_id}")
@inject
async def update_character(
	character_service: FromDishka[ICharacterService],
	character_id: UUID = Path(),
	update_data: Character = Body(),
) -> ApiResponse:
	await character_service.update(character_id, update_data)
	return ApiResponse(result=[], correlation_id=correlation_id.get())
