import logging

from asgi_correlation_id import correlation_id
from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, Depends, File, Form, UploadFile

from src.application.imports.schemas import ImportLorebookResultDTO
from src.application.ports.common import ApiResponse
from src.application.ports.imports import IImportService
from src.controllers.api.v1.auth_dependencies import get_current_user
from src.domain.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/import", tags=["import"])


@router.post("/lorebook")
@inject
async def import_lorebook(
	import_service: FromDishka[IImportService],
	file: UploadFile = File(..., description="SillyTavern World Info / lorebook JSON"),
	is_public: bool = Form(False),
	import_images: bool = Form(True),
	current_user: User = Depends(get_current_user),
) -> ApiResponse[ImportLorebookResultDTO]:
	raw = await file.read()
	result = await import_service.import_lorebook(
		raw, current_user.id, is_public=is_public, import_images=import_images
	)
	return ApiResponse(result=result, correlation_id=correlation_id.get())
