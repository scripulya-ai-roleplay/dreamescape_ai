import logging
import sys

from src.conf import settings
from src.infrastructure.logging.json_formatter import JsonFormatter
from src.infrastructure.logging.trace import RequestContextFilter

_TEXT_FORMAT = (
	"%(asctime)s [%(levelname)s] %(name)s "
	"user=%(user_id)s trace=%(trace_id)s "
	"(%(filename)s:%(funcName)s:%(lineno)d): %(message)s"
)


class Logger:
	LOGGER_NAME = "scripulya"

	@classmethod
	def configure(cls) -> None:
		level = logging.INFO
		if settings.DEBUG:
			level = logging.DEBUG

		handler = logging.StreamHandler(sys.stdout)
		if settings.LOG_FORMAT_JSON:
			handler.setFormatter(JsonFormatter())
		else:
			handler.setFormatter(logging.Formatter(_TEXT_FORMAT))

		logging.basicConfig(level=level, force=True, handlers=[handler])

		ctx_filter = RequestContextFilter()
		for configured_handler in logging.getLogger().handlers:
			configured_handler.addFilter(ctx_filter)
