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

	@classmethod
	def uvicorn_log_config(cls) -> dict | None:
		"""log_config for uvicorn.run so it does not override the JSON setup.

		By default uvicorn applies its own dictConfig after Logger.configure():
		uvicorn.access gets a plain-text stdout handler with propagate=False,
		which breaks the one-JSON-object-per-line contract when
		LOG_FORMAT_JSON=true. Returning None keeps uvicorn's defaults for text
		mode; in JSON mode this config strips every uvicorn logger's own
		handlers and lets records propagate to the root handler installed by
		Logger.configure() (same JsonFormatter, same RequestContextFilter).
		"""
		if not settings.LOG_FORMAT_JSON:
			return None
		return {
			"version": 1,
			"disable_existing_loggers": False,
			"loggers": {
				"uvicorn": {"propagate": True},
				"uvicorn.error": {"level": "INFO"},
				"uvicorn.access": {"propagate": True},
			},
		}
