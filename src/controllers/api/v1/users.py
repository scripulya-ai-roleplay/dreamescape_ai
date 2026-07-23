import logging
from uuid import UUID

from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, Depends
from fastapi.params import Query
from asgi_correlation_id.context import correlation_id

from src.application.ports.user import IUserService
from src.application.ports.common import ApiResponse, Page
from src.controllers.api.v1.auth_dependencies import get_current_user
from src.domain.models import User
from src.application.user.schemas import UserDTO

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["users"])


@router.get("/search", response_model=ApiResponse[Page[User]])
@inject
async def search_users(
	user_service: FromDishka[IUserService],
	user_dto: UserDTO = Query(default=UserDTO()),
) -> ApiResponse[Page[User]]:
	users_page = await user_service.find_users_by_dto(user_dto)

	logger.info(f"Found {users_page.count} users")

	return ApiResponse(result=users_page, correlation_id=correlation_id.get())


@router.delete("/{user_id}", response_model=ApiResponse[dict])
@inject
async def delete_user(
	user_id: UUID,
	user_service: FromDishka[IUserService],
	current_user: User = Depends(get_current_user),
) -> ApiResponse[dict]:
	await user_service.delete_user(user_id, current_user.id)
	logger.info(f"User deleted successfully: {user_id}")

	return ApiResponse(result={"message": "User deleted successfully"}, correlation_id=correlation_id.get())
