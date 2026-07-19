import logging
import time

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware

from src.conf import settings
from src.application.auth.jwt_service import JWTService
from src.domain.models import User
from src.infrastructure.logging import trace

logger = logging.getLogger(__name__)


class TraceAndLogRequestsMiddleware(BaseHTTPMiddleware):
	def __init__(self, app: FastAPI):
		super().__init__(app)
		# APP-scoped, stateless decoder used only to enrich logs with the caller's
		# identity. Mirrors the DI-provided JWTService config. Auth is enforced by
		# the route dependency, not here, so decoding must never fail the request.
		self._jwt_service = JWTService(
			logger=logger,
			private_key=settings.JWT_SECRET_KEY,
			public_key=settings.JWT_PUBLIC_KEY,
			algorithm=settings.JWT_ALGORITHM,
			access_token_expire_minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
		)

	async def get_current_user(self, request: Request) -> User | None:
		# Logging-only: resolve the bearer token to a user purely to enrich request
		# logs. Auth is enforced by the route dependency, not here, so this must
		# never fail the request — any decode/payload error is swallowed.
		credentials = getattr(request.state, "credentials", None)
		if credentials is None:
			return None

		try:
			return self._jwt_service.verify_token(credentials.credentials)
		except Exception:  # noqa: BLE001 — logging must never break the request
			return None

	async def dispatch(self, request: Request, call_next):
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
