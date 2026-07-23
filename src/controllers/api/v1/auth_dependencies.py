import logging

from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette import status
from starlette.requests import Request

from src.application.ports.auth import IJWTService
from src.domain.models import User

logger = logging.getLogger(__name__)

oauth2_scheme = HTTPBearer(auto_error=False)


async def set_token_to_request_state(
	request: Request,
	token: HTTPAuthorizationCredentials | None = Depends(oauth2_scheme),
):
	# Global app dependency: TraceAndLogRequestsMiddleware reads
	# request.state.credentials outside FastAPI's dependency system, so the token
	# is stashed here for the route deps and the middleware to share.
	request.state.credentials = token


def _verify_credentials(
	credentials: HTTPAuthorizationCredentials | None,
	jwt_service: IJWTService,
) -> User | None:
	# Shared by get_current_user and get_optional_user so both accept the same
	# tokens — diverging would let an optionally-authed route accept what a
	# required-auth route rejects.
	if credentials is None:
		return None
	try:
		return jwt_service.verify_token(credentials.credentials)
	except Exception as e:  # noqa: BLE001
		logger.warning("Authentication failed: %s", e)
		return None


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

	user = _verify_credentials(credentials, jwt_service)
	if user is None:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Invalid authentication credentials",
			headers={"WWW-Authenticate": "Bearer"},
		)

	logger.info("User authenticated successfully (role: %s)", user.role)
	return user


@inject
async def get_optional_user(
	request: Request,
	jwt_service: FromDishka[IJWTService],
) -> User | None:
	return _verify_credentials(getattr(request.state, "credentials", None), jwt_service)
