import logging

from fastapi import FastAPI, Depends
from asgi_correlation_id import CorrelationIdMiddleware

from settings.conf import settings
from src.controllers.api.v1.auth import set_token_to_request_state
from src.controllers.api.v1.chats import router as chat_router
from src.controllers.api.v1.users import router as users_router
from src.infrastructure.web.global_exceptions_handler import global_exception_handler
from src.infrastructure.web.middlewares import TraceAndLogRequestsMiddleware

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    logger.info("Creating FastAPI application")

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Service for roleplay chatting using LLM",
        debug=settings.DEBUG,
        dependencies=[Depends(set_token_to_request_state)],
    )

    # Add correlation ID middleware
    app.add_middleware(TraceAndLogRequestsMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    logger.info("Correlation ID middleware registered")

    # Register global exception handler
    app.add_exception_handler(Exception, global_exception_handler)
    logger.info("Global exception handler registered")

    app.include_router(chat_router)
    app.include_router(users_router)
    logger.info("API routes registered")

    return app
