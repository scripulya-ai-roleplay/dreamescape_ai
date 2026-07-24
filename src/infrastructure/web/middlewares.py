import logging
import time

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware

from src.application.auth.jwt_service import JWTService
from src.conf import settings
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

	async def _resolve_caller(self, request: Request) -> User | None:
		# Logging-only: decode the bearer token to enrich request logs. Auth is
		# enforced by the route dependency, not here, so any decode/payload error
		# is swallowed. On success, publish the caller's id onto the request
		# context (trace.set_user_id) BEFORE the route runs, so every downstream
		# log line — including the error path in dispatch() — is correlatable.
		credentials = getattr(request.state, "credentials", None)
		if credentials is None:
			return None
		try:
			user = self._jwt_service.verify_token(credentials.credentials)
		except Exception:  # noqa: BLE001 — logging must never break the request
			return None
		trace.set_user_id(str(user.id))
		return user

	async def dispatch(self, request: Request, call_next):
		start_time = time.time()
		client_host = request.client.host if request.client else "-"

		# Resolve the caller up front; sets the user_id contextvar for the whole
		# request (propagated into the route running inside call_next).
		await self._resolve_caller(request)

		logger.info("Request started: %s %s from %s", request.method, request.url.path, client_host)

		try:
			response = await call_next(request)
		except Exception as e:
			process_time = time.time() - start_time
			logger.error(
				"Request failed: %s %s (in %.3fs): %s",
				request.method,
				request.url.path,
				process_time,
				e,
				exc_info=True,
			)
			raise e

		process_time = time.time() - start_time
		# Always emit a completion line (anonymous requests included) so public
		# endpoints don't look like dropped logs. The caller id is rendered from
		# the user_id contextvar by RequestContextFilter, not repeated here.
		logger.info(
			"Request completed: %s %s -> %s in %.3fs",
			request.method,
			request.url.path,
			response.status_code,
			process_time,
		)
		return response
