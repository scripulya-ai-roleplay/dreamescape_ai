"""
Global exception handling module for FastAPI application.
Handles LLM-specific exceptions including quota, JSON parsing, and content safety violations.
"""

from fastapi import status

from src.infrastructure.web.global_exceptions_handler import BaseAPIException


class QuotaExceededException(BaseAPIException):
    """Raised when API quota is exceeded"""
    
    def __init__(self, message: str = "API quota exceeded", **kwargs):
        super().__init__(
            message=message,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            error_code="QUOTA_EXCEEDED",
            **kwargs
        )


class JSONParsingException(BaseAPIException):
    """Raised when JSON parsing fails"""
    
    def __init__(self, message: str = "Failed to parse JSON response", **kwargs):
        super().__init__(
            message=message,
            status_code=status.HTTP_502_BAD_GATEWAY,
            error_code="JSON_PARSING_ERROR",
            **kwargs
        )


class ContentSafetyException(BaseAPIException):
    """Raised when content is blocked by safety filters"""
    
    def __init__(self, message: str = "Content blocked by safety filters", **kwargs):
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="CONTENT_SAFETY_VIOLATION",
            **kwargs
        )


class LLMGatewayException(BaseAPIException):
    """Raised when LLM gateway encounters an error"""
    
    def __init__(self, message: str = "LLM gateway error", **kwargs):
        super().__init__(
            message=message,
            status_code=status.HTTP_502_BAD_GATEWAY,
            error_code="LLM_GATEWAY_ERROR",
            **kwargs
        )


class RateLimitException(BaseAPIException):
    """Raised when rate limit is exceeded"""
    
    def __init__(self, message: str = "Rate limit exceeded", **kwargs):
        super().__init__(
            message=message,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            error_code="RATE_LIMIT_EXCEEDED",
            **kwargs
        )


