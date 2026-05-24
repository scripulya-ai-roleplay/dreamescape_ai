import json
import logging
from typing import Optional, Dict, Any

from fastapi import HTTPException
from fastapi.exception_handlers import http_exception_handler
from sqlalchemy.exc import NoResultFound, MultipleResultsFound, IntegrityError

from starlette import status
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class BaseAPIException(Exception):
	"""Base exception for API-related errors"""

	def __init__(
		self,
		message: str,
		status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
		error_code: Optional[str] = None,
		details: Optional[Dict[str, Any]] = None,
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
