from fastapi import status

from src.infrastructure.web.global_exceptions_handler import BaseAPIException


class QuotaExceededException(BaseAPIException):
	def __init__(self, message: str = "API quota exceeded", **kwargs):
		super().__init__(
			message=message, status_code=status.HTTP_429_TOO_MANY_REQUESTS, error_code="QUOTA_EXCEEDED", **kwargs
		)


class JSONParsingException(BaseAPIException):
	def __init__(self, message: str = "Failed to parse JSON response", **kwargs):
		super().__init__(
			message=message, status_code=status.HTTP_502_BAD_GATEWAY, error_code="JSON_PARSING_ERROR", **kwargs
		)


class ContentSafetyException(BaseAPIException):
	def __init__(self, message: str = "Content blocked by safety filters", **kwargs):
		super().__init__(
			message=message, status_code=status.HTTP_400_BAD_REQUEST, error_code="CONTENT_SAFETY_VIOLATION", **kwargs
		)


class LLMGatewayException(BaseAPIException):
	def __init__(self, message: str = "LLM gateway error", **kwargs):
		super().__init__(
			message=message, status_code=status.HTTP_502_BAD_GATEWAY, error_code="LLM_GATEWAY_ERROR", **kwargs
		)


class RateLimitException(BaseAPIException):
	def __init__(self, message: str = "Rate limit exceeded", **kwargs):
		super().__init__(
			message=message, status_code=status.HTTP_429_TOO_MANY_REQUESTS, error_code="RATE_LIMIT_EXCEEDED", **kwargs
		)


class UnsupportedImageTypeException(BaseAPIException):
	def __init__(self, message: str = "Unsupported image content type", **kwargs):
		super().__init__(
			message=message,
			status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
			error_code="UNSUPPORTED_IMAGE_TYPE",
			**kwargs,
		)


class ImageTooLargeException(BaseAPIException):
	def __init__(self, message: str = "Image exceeds the size limit", **kwargs):
		super().__init__(
			message=message,
			status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
			error_code="IMAGE_TOO_LARGE",
			**kwargs,
		)


class PersonaRequiredException(BaseAPIException):
	def __init__(self, message: str = "To play a story choose who to play as", **kwargs):
		super().__init__(
			message=message,
			status_code=status.HTTP_400_BAD_REQUEST,
			error_code="PERSONA_REQUIRED",
			**kwargs,
		)


class InitialMessageRequiredException(BaseAPIException):
	def __init__(self, message: str = "Choose an initial message to start the chat", **kwargs):
		super().__init__(
			message=message,
			status_code=status.HTTP_400_BAD_REQUEST,
			error_code="INITIAL_MESSAGE_REQUIRED",
			**kwargs,
		)
