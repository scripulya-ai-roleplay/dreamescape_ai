import logging

from src.conf import settings


class Logger:
	LOGGER_NAME = "scripulya"

	@classmethod
	def configure(cls) -> None:
		level = logging.INFO
		if settings.DEBUG:
			level = logging.DEBUG

		logging.basicConfig(
			level=level,
			format="%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(funcName)s:%(lineno)d): %(message)s",
		)
