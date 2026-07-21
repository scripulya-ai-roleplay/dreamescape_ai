import logging

from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette import status
from starlette.requests import Request

from src.application.ports import IJWTService
from src.domain.models import User

logger = logging.getLogger(__name__)
oauth2_scheme = HTTPBearer(auto_error=False)


async def set_token_to_request_state(
	request: Request,
	token: HTTPAuthorizationCredentials | None = Depends(oauth2_scheme),
):
	request.state.credentials = token


@inject
async def get_current_user(
	request: Request,
	jwt_service: FromDishka[IJWTService],
) -> User:
	credentials: HTTPAuthorizationCredentials | None = getattr(request.state, "credentials", None)
	if credentials is None:
		logger.warning("Missing Authorization header")
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Missing authentication credentials",
			headers={"WWW-Authenticate": "Bearer"},
		)

	try:
		user = jwt_service.verify_token(credentials.credentials)
	except Exception as e:  # noqa: BLE001
		logger.warning("Authentication failed: %s", e)
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Invalid authentication credentials",
			headers={"WWW-Authenticate": "Bearer"},
		) from e

	# Caller id is rendered on every log line via RequestContextFilter (set from
	# the user_id contextvar by the logging middleware); only note the role here.
	logger.info("User authenticated successfully (role: %s)", user.role)
	return user


@inject
async def get_optional_user(
	request: Request,
	jwt_service: FromDishka[IJWTService],
) -> User | None:
	credentials: HTTPAuthorizationCredentials | None = getattr(request.state, "credentials", None)
	if credentials is None:
		return None

	try:
		return jwt_service.verify_token(credentials.credentials)
	except Exception as e:  # noqa: BLE001
		logger.warning("Authentication failed: %s", e)
		return None
