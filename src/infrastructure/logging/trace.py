import logging
import uuid
from contextvars import ContextVar

from asgi_correlation_id import correlation_id

# Context variable to store trace_id for the current request
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")

# Context variable to store username for the current request
username_var: ContextVar[str | None] = ContextVar("username", default=None)


def get_trace_id() -> str:
	"""Get current trace ID.

	Returns:
	    Current trace ID or empty string if not set
	"""
	return trace_id_var.get()


def set_trace_id(trace_id: str) -> None:
	"""Set trace ID for current context.

	Args:
	    trace_id: Trace ID to set
	"""
	trace_id_var.set(trace_id)


def generate_trace_id() -> str:
	"""Generate a new trace ID.

	Returns:
	    New UUID-based trace ID
	"""
	return str(uuid.uuid4())


def get_username() -> str | None:
	"""Get current username from context.

	Returns:
	    Current username or None if not authenticated
	"""
	return username_var.get()


def set_username(username: str | None) -> None:
	"""Set username in context for logging.

	Args:
	    username: Username to set (None for unauthenticated requests)
	"""
	username_var.set(username)


class TraceIdFilter(logging.Filter):
	def filter(self, record: logging.LogRecord) -> bool:
		"""Add trace_id to log record if available.

		Args:
		    record: Log record to modify

		Returns:
		    Always True to allow the record to be logged
		"""
		trace_id = correlation_id.get()
		if trace_id:
			record.trace_id = trace_id  # type: ignore[attr-defined]
		return True
