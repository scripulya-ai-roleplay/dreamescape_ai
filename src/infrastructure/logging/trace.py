import logging
import uuid
from contextvars import ContextVar

from asgi_correlation_id import correlation_id

# Context variable to store trace_id for the current request
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")

# Context variable to store username for the current request
username_var: ContextVar[str | None] = ContextVar("username", default=None)


def get_trace_id() -> str:
	return trace_id_var.get()


def set_trace_id(trace_id: str) -> None:
	trace_id_var.set(trace_id)


def generate_trace_id() -> str:
	return str(uuid.uuid4())


def get_username() -> str | None:
	return username_var.get()


def set_username(username: str | None) -> None:
	username_var.set(username)


class TraceIdFilter(logging.Filter):
	def filter(self, record: logging.LogRecord) -> bool:
		trace_id = correlation_id.get()
		if trace_id:
			record.trace_id = trace_id  # type: ignore[attr-defined]
		return True
