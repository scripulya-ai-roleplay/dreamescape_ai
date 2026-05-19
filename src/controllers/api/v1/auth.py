import logging

from dishka import AsyncContainer
from fastapi import Depends, HTTPException
from starlette import status
from starlette.requests import Request
from fastapi.security import HTTPBearer

from src.application.ports import IJWTService
from src.domain.models import User

logger = logging.getLogger(__name__)
oauth2_scheme = HTTPBearer(auto_error=False)


async def set_token_to_request_state(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
):
    request.state.credentials = token


async def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
) -> User:
    container: AsyncContainer = request.state.dishka_container
    jwt_service = await container.get(IJWTService)

    if token is None:
        logger.warning("Missing Authorization header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user = jwt_service.verify_token(token)

        request.state.username = user.username

        logger.info(
            "User authenticated successfully: %s (role: %s)",
            user.username,
            user.role,
        )
        return user
    except Exception as e:
        logger.warning("Authentication failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
