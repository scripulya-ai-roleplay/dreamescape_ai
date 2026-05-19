import argparse
import logging

import google.generativeai as genai
import uvicorn
from dishka.integrations.fastapi import setup_dishka

from app import create_app
from settings.conf import settings
from src.infrastructure.di import create_container

genai.configure(api_key=settings.GEMINI_API_KEY)


logger = logging.getLogger(__name__)


def run_http_server() -> None:
    app = create_app()

    logger.info("Starting HTTP server on %s:%s", settings.HOST, settings.PORT)

    container = create_container()
    app.state.dishka_container = container
    setup_dishka(container, app)

    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT,
        log_level="info",
    )


def main() -> int:
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
