import logging
import time
from uuid import UUID

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from starlette import status
from starlette.middleware.base import BaseHTTPMiddleware

from src.conf import settings
from src.application.auth.jwt_service import JWTService
from src.domain.models import User, UserRole
from src.infrastructure.logging import trace

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)


class TraceAndLogRequestsMiddleware(BaseHTTPMiddleware):
	def __init__(self, app: FastAPI):
		super().__init__(app)
		self._secret_key = settings.JWT_SECRET_KEY
		self._public_key = settings.JWT_PUBLIC_KEY
		self._algorithm = settings.JWT_ALGORITHM

	async def _get_current_user(
		self,
		request: Request,
		credentials: HTTPAuthorizationCredentials,
		jwt_service: JWTService,
	) -> User:
		if credentials is None:
			logger.warning("Missing Authorization header")
			raise HTTPException(
				status_code=status.HTTP_401_UNAUTHORIZED,
				detail="Missing authentication credentials",
				headers={"WWW-Authenticate": "Bearer"},
			)

		token = credentials.credentials

		try:
			user = jwt_service.verify_token(token)

			trace.set_username(user.username)

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

	async def get_current_user(self, request) -> User | None:
		# Logging-only: resolve the bearer token to a user purely to enrich request
		# logs. Auth is enforced by the route dependency, not here, so this must
		# never fail the request — any decode/payload error is swallowed.
		if getattr(request.state, "credentials", None) is None:
			return None

		token = request.state.credentials.credentials
		try:
			# For HS256, use secret key; for ES256, use public key
			key = self._secret_key if self._algorithm.startswith("HS") else self._public_key
			payload = jwt.decode(token, key, algorithms=[self._algorithm])
			return User(
				id=UUID(payload.get("sub")) if payload.get("sub") else None,
				username=payload.get("username"),
				role=UserRole(payload["role"]) if payload.get("role") else UserRole.API,
			)
		except Exception:
			return None

	async def dispatch(
		self,
		request: Request,
		call_next,
		credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
	):
		start_time = time.time()

		logger.info(
			"Request started",
			extra={
				"method": request.method,
				"path": request.url.path,
				"client_host": request.client.host if request.client else None,
			},
		)

		try:
			response = await call_next(request)
			process_time = time.time() - start_time

			log_extra = {
				"method": request.method,
				"path": request.url.path,
				"status_code": response.status_code,
				"duration": round(process_time, 3),
			}

			user = await self.get_current_user(request)
			if user is not None:
				log_extra["username"] = user.username
				log_extra["user_role"] = user.role
				logger.info("Request completed", extra=log_extra)

			return response
		except Exception as e:
			process_time = time.time() - start_time

			username = trace.get_username()

			log_extra = {
				"method": request.method,
				"path": request.url.path,
				"duration": round(process_time, 3),
				"error": str(e),
			}

			if username:
				log_extra["username"] = username

			logger.error("Request failed", extra=log_extra, exc_info=True)
			raise e
