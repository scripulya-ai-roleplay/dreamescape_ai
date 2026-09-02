import json
import logging
from datetime import UTC, datetime

from src.conf import settings

_RESERVED = (
	"asctime",
	"levelname",
	"name",
	"user_id",
	"trace_id",
	"filename",
	"funcName",
	"lineno",
	"message",
	"msg",
	"args",
	"exc_info",
	"exc_text",
	"stack_info",
	"msecs",
	"relativeCreated",
	"created",
	"task",
	"threadName",
	"thread",
	"processName",
	"process",
	"module",
	"pathname",
	"name",
	"levelno",
	"funcName",
)


class JsonFormatter(logging.Formatter):
	"""One JSON object per line for log shippers to index verbatim.

	Emits the same fields the text format renders (timestamp, level, logger,
	location, trace_id, user_id, message) plus any ``extra={...}`` keys a call
	site attached, and the formatted exception when ``exc_info`` is set.
	"""

	def format(self, record: logging.LogRecord) -> str:
		payload = {
			"timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
			"level": record.levelname,
			"logger": record.name,
			"service": settings.LOG_SERVICE_NAME,
			"user_id": getattr(record, "user_id", None),
			"trace_id": getattr(record, "trace_id", None),
			"location": f"{record.filename}:{record.funcName}:{record.lineno}",
			"message": record.getMessage(),
		}

		for key, value in record.__dict__.items():
			if key in payload or key in _RESERVED or key.startswith("_"):
				continue
			payload[key] = value

		if record.exc_info:
			payload["exception"] = self.formatException(record.exc_info)

		return json.dumps(payload, ensure_ascii=False, default=str)
