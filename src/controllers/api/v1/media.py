import logging
from typing import NamedTuple
from uuid import UUID

from asgi_correlation_id import correlation_id
from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, Depends, File, Form, Path, Query, UploadFile

from src.application.media.schemas import MediaAssetDTO, MediaFilterDTO, MediaUploadDTO
from src.application.ports.common import ApiResponse, Page
from src.application.ports.media import IMediaService
from src.controllers.api.v1.auth_dependencies import get_current_user, get_optional_user
from src.domain.models import MediaEntityType, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/media", tags=["media"])


class _UploadForm(NamedTuple):
	file: UploadFile
	entity_type: MediaEntityType
	entity_id: UUID
	is_public: bool


def upload_form(
	file: UploadFile = File(..., description="Image file (png/jpeg/webp/gif/bmp/tiff/ico)"),
	entity_type: MediaEntityType = Form(..., description="Owning entity kind: character | scene | user"),
	entity_id: UUID = Form(..., description="ID of the owning entity"),
	is_public: bool = Form(False, description="Anonymous-readable (public bucket) or owner-only (presigned)"),
) -> _UploadForm:
	return _UploadForm(file=file, entity_type=entity_type, entity_id=entity_id, is_public=is_public)


@router.post("/")
@inject
async def upload_media(
	media_service: FromDishka[IMediaService],
	form: _UploadForm = Depends(upload_form),
	current_user: User = Depends(get_current_user),
) -> ApiResponse[MediaAssetDTO]:
	owner_id = current_user.id
	logger.info(
		"Upload request from user %s for %s/%s (public=%s)", owner_id, form.entity_type, form.entity_id, form.is_public
	)

	result = await media_service.upload(
		MediaUploadDTO(
			file=form.file,
			entity_type=form.entity_type,
			entity_id=form.entity_id,
			is_public=form.is_public,
			owner_id=owner_id,
		)
	)
	return ApiResponse(result=result, correlation_id=correlation_id.get())


@router.get("/{media_id}")
@inject
async def get_media(
	media_service: FromDishka[IMediaService],
	media_id: UUID = Path(),
	current_user: User | None = Depends(get_optional_user),
) -> ApiResponse[MediaAssetDTO]:
	actor_id = current_user.id if current_user else None
	result = await media_service.get_one(media_id, actor_id=actor_id)
	return ApiResponse(result=result, correlation_id=correlation_id.get())


@router.get("/")
@inject
async def search_media(
	media_service: FromDishka[IMediaService],
	dto: MediaFilterDTO = Query(MediaFilterDTO()),
	current_user: User = Depends(get_current_user),
) -> ApiResponse[Page[MediaAssetDTO]]:
	actor_id = current_user.id
	result = await media_service.search(dto, actor_id=actor_id)
	return ApiResponse(result=result, correlation_id=correlation_id.get())


@router.delete("/{media_id}")
@inject
async def delete_media(
	media_service: FromDishka[IMediaService],
	media_id: UUID = Path(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse:
	actor_id = current_user.id
	await media_service.delete(media_id, actor_id=actor_id)
	return ApiResponse(result=[], correlation_id=correlation_id.get())
