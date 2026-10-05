import logging
from uuid import UUID

from asgi_correlation_id import correlation_id
from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, Body, Depends, Path, Query, status

from src.application.ports.common import ApiResponse, Page
from src.application.ports.summarization import ISummarizationService
from src.application.summarization.schemas import (
	CreateSummariesDTO,
	SummariesFilterDTO,
	SummaryChapter,
	UpdateSummaryDTO,
)
from src.controllers.api.v1.auth_dependencies import get_current_user
from src.domain.models import ChatSummary, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/summarization", tags=["summarization"])


@router.get("/chapters")
@inject
async def list_chapters(
	service: FromDishka[ISummarizationService],
	chat_id: UUID = Query(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse[list[SummaryChapter]]:
	result = await service.list_chapters(chat_id, current_user.id)
	return ApiResponse(result=result, correlation_id=correlation_id.get())


@router.post("/", status_code=status.HTTP_202_ACCEPTED)
@inject
async def create_summaries(
	service: FromDishka[ISummarizationService],
	payload: CreateSummariesDTO = Body(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse[list[ChatSummary]]:
	result = await service.summarize(payload, current_user.id)
	return ApiResponse(result=result, correlation_id=correlation_id.get())


@router.get("/")
@inject
async def search_summaries(
	service: FromDishka[ISummarizationService],
	dto: SummariesFilterDTO = Query(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse[Page[ChatSummary]]:
	result = await service.search(dto, current_user.id)
	return ApiResponse(result=result, correlation_id=correlation_id.get())


@router.get("/{summary_id}")
@inject
async def get_summary(
	service: FromDishka[ISummarizationService],
	summary_id: UUID = Path(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse[ChatSummary]:
	result = await service.get_one(summary_id, current_user.id)
	return ApiResponse(result=result, correlation_id=correlation_id.get())


@router.put("/{summary_id}")
@inject
async def update_summary(
	service: FromDishka[ISummarizationService],
	summary_id: UUID = Path(),
	payload: UpdateSummaryDTO = Body(),
	current_user: User = Depends(get_current_user),
) -> ApiResponse[ChatSummary]:
	result = await service.update(summary_id, payload, current_user.id)
	return ApiResponse(result=result, correlation_id=correlation_id.get())
