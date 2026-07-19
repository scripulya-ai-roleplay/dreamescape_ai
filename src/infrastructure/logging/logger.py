import logging

from src.conf import settings
from src.infrastructure.logging.trace import RequestContextFilter


class Logger:
	LOGGER_NAME = "scripulya"

	@classmethod
	def configure(cls) -> None:
		level = logging.INFO
		if settings.DEBUG:
			level = logging.DEBUG

		logging.basicConfig(
			level=level,
			format=(
				"%(asctime)s [%(levelname)s] %(name)s "
				"user=%(user_id)s trace=%(trace_id)s "
				"(%(filename)s:%(funcName)s:%(lineno)d): %(message)s"
			),
		)
		# Populate trace_id/user_id on every record (defaulting to "-"). Without
		# this filter the format's %(user_id)s/%(trace_id)s would have no source
		# and formatting would raise KeyError.
		ctx_filter = RequestContextFilter()
		for handler in logging.getLogger().handlers:
			handler.addFilter(ctx_filter)
