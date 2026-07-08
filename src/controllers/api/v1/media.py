import logging
from typing import Dict, Any
from uuid import UUID

from asgi_correlation_id import correlation_id
from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, Query, Path, Depends, File, Form, UploadFile

from src.application.media.schemas import MediaAssetDTO, MediaFilterDTO
from src.application.ports import ApiResponse, Page, IMediaService
from src.domain.models import MediaEntityType
from src.infrastructure.auth.dependencies import get_current_user, get_optional_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/media", tags=["media"])


@router.post("/")
@inject
async def upload_media(
	media_service: FromDishka[IMediaService],
	file: UploadFile = File(..., description="Image file (png/jpeg/webp/gif/svg/...)"),
	entity_type: MediaEntityType = Form(..., description="Owning entity kind: character | scene | user"),
	entity_id: UUID = Form(..., description="ID of the owning entity"),
	is_public: bool = Form(False, description="Anonymous-readable (public bucket) or owner-only (presigned)"),
	current_user: Dict[str, Any] = Depends(get_current_user),
) -> ApiResponse[MediaAssetDTO]:
	owner_id = UUID(current_user["sub"])
	logger.info("Upload request from user %s for %s/%s (public=%s)", owner_id, entity_type, entity_id, is_public)

	result = await media_service.upload(
		file=file,
		entity_type=entity_type,
		entity_id=entity_id,
		is_public=is_public,
		owner_id=owner_id,
	)
	return ApiResponse(result=result, correlation_id=correlation_id.get())


@router.get("/{media_id}")
@inject
async def get_media(
	media_service: FromDishka[IMediaService],
	media_id: UUID = Path(),
	current_user: Dict[str, Any] | None = Depends(get_optional_user),
) -> ApiResponse[MediaAssetDTO]:
	# Public assets are reachable anonymously; private assets require the owner.
	actor_id = UUID(current_user["sub"]) if current_user else None
	result = await media_service.get_one(media_id, actor_id=actor_id)
	return ApiResponse(result=result, correlation_id=correlation_id.get())


@router.get("/")
@inject
async def search_media(
	media_service: FromDishka[IMediaService],
	dto: MediaFilterDTO = Query(MediaFilterDTO()),
	current_user: Dict[str, Any] = Depends(get_current_user),
) -> ApiResponse[Page[MediaAssetDTO]]:
	actor_id = UUID(current_user["sub"])
	result = await media_service.search(dto, actor_id=actor_id)
	return ApiResponse(result=result, correlation_id=correlation_id.get())


@router.delete("/{media_id}")
@inject
async def delete_media(
	media_service: FromDishka[IMediaService],
	media_id: UUID = Path(),
	current_user: Dict[str, Any] = Depends(get_current_user),
) -> ApiResponse:
	actor_id = UUID(current_user["sub"])
	await media_service.delete(media_id, actor_id=actor_id)
	return ApiResponse(result=[], correlation_id=correlation_id.get())
