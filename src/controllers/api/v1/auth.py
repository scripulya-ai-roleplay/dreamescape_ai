import logging

from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter

from src.application.auth.schemas import LoginRequest, Token
from src.application.ports import IAuthService, IJWTService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=Token)
@inject
async def login(
	body: LoginRequest,
	auth_service: FromDishka[IAuthService],
	jwt_service: FromDishka[IJWTService],
) -> Token:
	user = await auth_service.authenticate(body.username, body.password)
	access_token = jwt_service.create_token(user)
	return Token(access_token=access_token)
