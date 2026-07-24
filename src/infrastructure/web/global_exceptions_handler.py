import json
import logging
from typing import Any

from fastapi import HTTPException
from fastapi.exception_handlers import http_exception_handler
from sqlalchemy.exc import IntegrityError, MultipleResultsFound, NoResultFound
from starlette import status
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.application.auth.errors import InvalidCredentialsError

logger = logging.getLogger(__name__)


class BaseAPIException(Exception):
	"""Base exception for API-related errors"""

	def __init__(
		self,
		message: str,
		status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
		error_code: str | None = None,
		details: dict[str, Any] | None = None,
	):
		self.message = message
		self.status_code = status_code
		self.error_code = error_code or self.__class__.__name__
		self.details = details or {}
		super().__init__(self.message)


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
	"""
	Global exception handler for all unhandled exceptions.
	Provides consistent error responses across the application.
	"""

	# Handle custom API exceptions
	if isinstance(exc, BaseAPIException):
		logger.warning("API exception occurred: %s - %s", exc.error_code, exc.message, extra={"details": exc.details})
		return JSONResponse(
			status_code=exc.status_code,
			content={"error": {"code": exc.error_code, "message": exc.message, "details": exc.details}},
		)

	# Domain auth error — carries no HTTP status (unlike BaseAPIException), so it
	# needs its own branch.
	if isinstance(exc, InvalidCredentialsError):
		logger.info("Authentication rejected: %s", exc.message)
		return JSONResponse(
			status_code=status.HTTP_401_UNAUTHORIZED,
			content={"error": {"code": "INVALID_CREDENTIALS", "message": exc.message, "details": {}}},
		)

	# Handle FastAPI HTTPException
	if isinstance(exc, HTTPException):
		return await http_exception_handler(request, exc)

	# Handle ValueError exceptions (e.g., "not found" cases)
	if isinstance(exc, ValueError):
		error_message = str(exc)
		if "not found" in error_message.lower():
			logger.warning("Resource not found: %s", error_message)
			return JSONResponse(
				status_code=status.HTTP_404_NOT_FOUND,
				content={
					"error": {
						"code": "RESOURCE_NOT_FOUND",
						"message": "The requested resource was not found",
						"details": {},
					}
				},
			)
		else:
			logger.error("ValueError occurred: %s", error_message)
			return JSONResponse(
				status_code=status.HTTP_400_BAD_REQUEST,
				content={
					"error": {
						"code": "INVALID_REQUEST",
						"message": "Invalid request data",
						"details": {"error": error_message},
					}
				},
			)

	# Handle SQLAlchemy exceptions
	if isinstance(exc, NoResultFound):
		logger.warning("Database record not found: %s", str(exc))
		return JSONResponse(
			status_code=status.HTTP_404_NOT_FOUND,
			content={
				"error": {
					"code": "RECORD_NOT_FOUND",
					"message": "The requested resource was not found",
					"details": {},
				}
			},
		)

	if isinstance(exc, MultipleResultsFound):
		logger.error("Multiple database records found when expecting one: %s", str(exc))
		return JSONResponse(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			content={
				"error": {
					"code": "MULTIPLE_RECORDS_FOUND",
					"message": "Database query returned multiple records when expecting one",
					"details": {},
				}
			},
		)

	if isinstance(exc, IntegrityError):
		logger.error("Database integrity error: %s", str(exc))
		return JSONResponse(
			status_code=status.HTTP_409_CONFLICT,
			content={
				"error": {
					"code": "INTEGRITY_ERROR",
					"message": "Database constraint violation",
					"details": {"constraint_error": str(exc.orig) if hasattr(exc, "orig") else str(exc)},
				}
			},
		)

	# Handle Google API specific exceptions
	if "google.api_core.exceptions" in str(type(exc)):
		return await handle_google_api_exception(request, exc)

	# Handle JSON decode errors
	if isinstance(exc, json.JSONDecodeError):
		logger.error("JSON parsing error: %s", str(exc))
		return JSONResponse(
			status_code=status.HTTP_502_BAD_GATEWAY,
			content={
				"error": {
					"code": "JSON_PARSING_ERROR",
					"message": "Failed to parse response from external service",
					"details": {"parse_error": str(exc)},
				}
			},
		)

	# Handle any other unhandled exceptions
	logger.error("Unhandled exception occurred: %s", str(exc), exc_info=True)
	return JSONResponse(
		status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
		content={"error": {"code": "INTERNAL_SERVER_ERROR", "message": "An unexpected error occurred", "details": {}}},
	)


async def handle_google_api_exception(request: Request, exc: Exception) -> JSONResponse:
	"""
	Handle Google API specific exceptions with appropriate error responses.
	"""
	exc_str = str(exc).lower()
	exc_type = type(exc).__name__

	# Handle quota exceeded errors
	if "quota" in exc_str or "exceeded" in exc_str or exc_type == "ResourceExhausted":
		logger.warning("Google API quota exceeded: %s", str(exc))
		return JSONResponse(
			status_code=status.HTTP_429_TOO_MANY_REQUESTS,
			content={
				"error": {
					"code": "QUOTA_EXCEEDED",
					"message": "API quota exceeded. Please try again later.",
					"details": {"provider": "google_api"},
				}
			},
		)

	# Handle rate limiting
	if "rate" in exc_str and "limit" in exc_str:
		logger.warning("Google API rate limit exceeded: %s", str(exc))
		return JSONResponse(
			status_code=status.HTTP_429_TOO_MANY_REQUESTS,
			content={
				"error": {
					"code": "RATE_LIMIT_EXCEEDED",
					"message": "Rate limit exceeded. Please try again later.",
					"details": {"provider": "google_api"},
				}
			},
		)

	# Handle permission denied / authentication errors
	if "permission" in exc_str or "unauthenticated" in exc_str or exc_type == "PermissionDenied":
		logger.error("Google API authentication error: %s", str(exc))
		return JSONResponse(
			status_code=status.HTTP_401_UNAUTHORIZED,
			content={
				"error": {
					"code": "AUTHENTICATION_ERROR",
					"message": "Authentication failed with external service",
					"details": {"provider": "google_api"},
				}
			},
		)

	# Handle service unavailable
	if "unavailable" in exc_str or exc_type == "ServiceUnavailable":
		logger.error("Google API service unavailable: %s", str(exc))
		return JSONResponse(
			status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
			content={
				"error": {
					"code": "SERVICE_UNAVAILABLE",
					"message": "External service is temporarily unavailable",
					"details": {"provider": "google_api"},
				}
			},
		)

	# Generic Google API error
	logger.error("Google API error: %s", str(exc))
	return JSONResponse(
		status_code=status.HTTP_502_BAD_GATEWAY,
		content={
			"error": {
				"code": "EXTERNAL_SERVICE_ERROR",
				"message": "Error communicating with external service",
				"details": {"provider": "google_api", "error": str(exc)},
			}
		},
	)


def register_exception_handlers(app) -> None:
	"""Register the global handler for the concrete exception types it handles.

	The handler must be registered per concrete type, not for the broad
	``Exception`` base class: with Starlette 1.0 + h11 (uvicorn's default
	protocol), a handler keyed on ``Exception`` makes uvicorn close the TCP
	connection after responding, so any keep-alive client reusing that socket
	sees its next request fail with RemoteDisconnected. Keying the handler on the
	specific types is handled on the clean path and leaves the connection open.
	Exceptions not listed here (genuinely unexpected ones) fall through to
	Starlette's ServerErrorMiddleware, which routes its 500s back through
	``global_exception_handler`` via the status-code registration below.
	"""
	for exc_type in (
		BaseAPIException,
		InvalidCredentialsError,
		ValueError,
		NoResultFound,
		MultipleResultsFound,
		IntegrityError,
		json.JSONDecodeError,
	):
		app.add_exception_handler(exc_type, global_exception_handler)

	try:
		from google.api_core.exceptions import GoogleCloudError
	except ImportError:
		# google.api_core is only present with the google-genai transport stack;
		# without it the google branch of global_exception_handler is unreachable.
		pass
	else:
		app.add_exception_handler(GoogleCloudError, global_exception_handler)

	app.add_exception_handler(500, global_exception_handler)
