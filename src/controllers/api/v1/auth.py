import logging

from dishka import AsyncContainer
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette import status
from starlette.requests import Request

from src.application.ports import IJWTService
from src.domain.models import User

logger = logging.getLogger(__name__)

# Single bearer scheme for the whole app. The token is extracted once, by the
# global ``set_token_to_request_state`` dependency, and stashed on request.state;
# route dependencies and the logging middleware read it from there.
oauth2_scheme = HTTPBearer(auto_error=False)


async def set_token_to_request_state(
	request: Request,
	token: HTTPAuthorizationCredentials | None = Depends(oauth2_scheme),
):
	request.state.credentials = token


async def get_current_user(request: Request) -> User:
	"""Dependency that yields the authenticated user, or 401."""
	credentials: HTTPAuthorizationCredentials | None = getattr(request.state, "credentials", None)
	if credentials is None:
		logger.warning("Missing Authorization header")
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Missing authentication credentials",
			headers={"WWW-Authenticate": "Bearer"},
		)

	container: AsyncContainer = request.state.dishka_container
	jwt_service = await container.get(IJWTService)
	try:
		user = jwt_service.verify_token(credentials.credentials)
	except Exception as e:  # noqa: BLE001
		logger.warning("Authentication failed: %s", e)
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Invalid authentication credentials",
			headers={"WWW-Authenticate": "Bearer"},
		) from e

	request.state.username = user.username
	logger.info("User authenticated successfully: %s (role: %s)", user.username, user.role)
	return user


async def get_optional_user(request: Request) -> User | None:
	"""Like ``get_current_user`` but returns ``None`` instead of 401 — for routes
	reachable anonymously (e.g. fetching a public media asset)."""
	credentials: HTTPAuthorizationCredentials | None = getattr(request.state, "credentials", None)
	if credentials is None:
		return None

	container: AsyncContainer = request.state.dishka_container
	jwt_service = await container.get(IJWTService)
	try:
		return jwt_service.verify_token(credentials.credentials)
	except Exception as e:  # noqa: BLE001
		logger.warning("Authentication failed: %s", e)
		return None
