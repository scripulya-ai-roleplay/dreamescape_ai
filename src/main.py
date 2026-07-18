import argparse
import logging

import uvicorn
from dishka.integrations.fastapi import setup_dishka
from dishka.integrations.faststream import setup_dishka as setup_broker_dishka

from src.app import create_app
from src.conf import settings
from src.controllers.rabbit.v1.broker import broker
from src.infrastructure.di import create_container
from src.infrastructure.logging.logger import Logger


logger = logging.getLogger(__name__)


def run_http_server() -> None:
	app = create_app()
	logger.info("Starting HTTP server on %s:%s", settings.HOST, settings.PORT)

	container = create_container()
	app.state.dishka_container = container
	setup_dishka(container, app)
	# Wire the broker so FromDishka[...] resolves inside the llm.agent.result subscriber.
	setup_broker_dishka(container, broker=broker, auto_inject=True)

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
	Logger.configure()
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
