import logging

from asgi_correlation_id import correlation_id
from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from starlette import status

from src.application.imports.schemas import ImportLorebookResultDTO, ImportPreviewDTO
from src.application.ports.common import ApiResponse
from src.application.ports.imports import IImportService
from src.conf import settings
from src.controllers.api.v1.auth_dependencies import get_current_user
from src.domain.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/import", tags=["import"])

_READ_CHUNK = 64 * 1024


async def _read_bounded(file: UploadFile, max_bytes: int) -> bytes:
	buf = bytearray()
	while True:
		chunk = await file.read(_READ_CHUNK)
		if not chunk:
			break
		buf += chunk
		if len(buf) > max_bytes:
			raise HTTPException(
				status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
				detail=f"Lorebook exceeds the {max_bytes}-byte limit",
			)
	return bytes(buf)


@router.post("/lorebook/preview")
@inject
async def preview_lorebook(
	import_service: FromDishka[IImportService],
	file: UploadFile = File(..., description="SillyTavern World Info / lorebook JSON"),
	current_user: User = Depends(get_current_user),
) -> ApiResponse[ImportPreviewDTO]:
	raw = await _read_bounded(file, settings.LOREBOOK_MAX_UPLOAD_BYTES)
	result = import_service.preview_lorebook(raw)
	return ApiResponse(result=result, correlation_id=correlation_id.get())


@router.post("/lorebook")
@inject
async def import_lorebook(
	import_service: FromDishka[IImportService],
	file: UploadFile = File(..., description="SillyTavern World Info / lorebook JSON"),
	is_public: bool = Form(False),
	import_images: bool = Form(True),
	selected_keys: list[str] = Form(default=[], description="Entry keys to import; omit to import all"),
	link_scenes: bool = Form(True, description="Link every created character to each created scene"),
	current_user: User = Depends(get_current_user),
) -> ApiResponse[ImportLorebookResultDTO]:
	raw = await _read_bounded(file, settings.LOREBOOK_MAX_UPLOAD_BYTES)
	result = await import_service.import_lorebook(
		raw,
		current_user.id,
		is_public=is_public,
		import_images=import_images,
		selected_keys=selected_keys or None,
		link_scenes=link_scenes,
	)
	return ApiResponse(result=result, correlation_id=correlation_id.get())
