import argparse
import logging

import uvicorn
from dishka.integrations.fastapi import setup_dishka

from src.app import create_app
from src.conf import settings
from src.infrastructure.di import create_container


logger = logging.getLogger(__name__)

logging_level = logging.INFO
if settings.DEBUG:
	logging_level = logging.DEBUG


def setup_logging() -> None:
	logging.basicConfig(
		level=logging_level,
		format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
	)


def run_http_server() -> None:
	app = create_app()
	logger.info("Starting HTTP server on %s:%s", settings.HOST, settings.PORT)

	container = create_container()
	app.state.dishka_container = container
	setup_dishka(container, app)

	uvicorn_logging_level = "info"
	if settings.DEBUG:
		uvicorn_logging_level = "debug"

	uvicorn.run(
		app,
		host=settings.HOST,
		port=settings.PORT,
		log_level=uvicorn_logging_level,
	)


def main() -> int:
	setup_logging()
	parser = argparse.ArgumentParser(
		description="VAPI Local Networks Service",
		formatter_class=argparse.RawDescriptionHelpFormatter,
	)

	parser.add_argument(
		"--http",
		action="store_true",
		help="Run HTTP server",
	)

	parser.add_argument(
		"--version",
		action="version",
		version=f"%(prog)s {settings.APP_VERSION}",
	)

	args = parser.parse_args()

	if args.http:
		try:
			run_http_server()
			return 0
		except KeyboardInterrupt:
			logger.info("Received interrupt signal, shutting down...")
			return 0
		except Exception as e:
			logger.error("Failed to start server: %s", e, exc_info=True)
			return 1
	else:
		parser.print_help()
		logger.error("\nError: No action specified. Use --http to start the server.")
		return 1


if __name__ == "__main__":
	main()
