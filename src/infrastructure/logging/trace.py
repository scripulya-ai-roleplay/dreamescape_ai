import logging
import uuid
from contextvars import ContextVar

from asgi_correlation_id import correlation_id

# Request-scoped context variables. Populated by the auth path and read by
# RequestContextFilter so every log line emitted during a request carries the
# correlation id and the caller's user id.
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")
user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)


def get_trace_id() -> str:
	return trace_id_var.get()


def set_trace_id(trace_id: str) -> None:
	trace_id_var.set(trace_id)


def generate_trace_id() -> str:
	return str(uuid.uuid4())


def get_user_id() -> str | None:
	return user_id_var.get()


def set_user_id(user_id: str | None) -> None:
	user_id_var.set(user_id)


class RequestContextFilter(logging.Filter):
	"""Stamp every log record with the request's trace_id and caller user_id.

	Both are read from contextvars (set by the logging middleware before the
	route runs) and default to ``"-"`` when absent — startup logs, background
	tasks, or anonymous requests — so the format string can reference
	``%(trace_id)s`` / ``%(user_id)s`` unconditionally.
	"""

	def filter(self, record: logging.LogRecord) -> bool:
		record.trace_id = correlation_id.get() or "-"  # type: ignore[attr-defined]
		record.user_id = user_id_var.get() or "-"  # type: ignore[attr-defined]
		return True
