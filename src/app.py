import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from asgi_correlation_id import CorrelationIdMiddleware

from src.conf import settings
from src.controllers.api.v1.auth import set_token_to_request_state
from src.controllers.api.v1.health import router as health_router
from src.controllers.rabbit.v1 import llm as rabbit_llm  # noqa: F401  registers the result subscriber
from src.controllers.rabbit.v1.broker import broker
from src.controllers.api.v1.characters import router as characters_router
from src.controllers.api.v1.messages import router as message_router
from src.controllers.api.v1.chat_events import router as chat_events_router
from src.controllers.api.v1.chats import router as chat_router
from src.controllers.api.v1.chat_settings import router as chat_settings_router
from src.controllers.api.v1.scenes import router as scenes_router
from src.controllers.api.v1.users import router as users_router
from src.controllers.api.v1.media import router as media_router
from src.application.ports import IObjectStorageGateway
from src.infrastructure.web.global_exceptions_handler import register_exception_handlers
from src.infrastructure.web.middlewares import TraceAndLogRequestsMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
	"""Start/stop the RabbitMQ broker alongside the HTTP app.

	dishka is wired to the broker in main.run_http_server before the app starts,
	so FromDishka[...] resolves inside the result subscriber once it is started here.

	The broker (and thus the RabbitMQ/scripulya_agent dependency) is only started when
	LLM_AGENT_ENABLED is true. When disabled, a MockScripulyaAgentClient is injected and
	no broker connection is made, so the app runs without RabbitMQ (local docker).
	"""
	# Best-effort: provision the media buckets early (and surface a MinIO
	# misconfig at boot). Non-fatal — upload retries lazily on first use.
	try:
		storage = await app.state.dishka_container.get(IObjectStorageGateway)
		await storage.ensure_buckets()
		logger.info("Media buckets ensured")
	except Exception:
		logger.warning("Could not ensure media buckets at startup; will retry on first upload", exc_info=True)

	if not settings.LLM_AGENT_ENABLED:
		logger.info("scripulya_agent disabled (LLM_AGENT_ENABLED=false); RabbitMQ broker not started")
		yield
		return

	await broker.start()
	logger.info("RabbitMQ broker started; consuming %s", settings.LLM_AGENT_RESULT_QUEUE)
	try:
		yield
	finally:
		await broker.close()
		logger.info("RabbitMQ broker closed")


def create_app() -> FastAPI:
	logger.info("Creating FastAPI application")

	app = FastAPI(
		title=settings.APP_NAME,
		version=settings.APP_VERSION,
		description="Service for roleplay chatting using LLM",
		debug=settings.DEBUG,
		dependencies=[Depends(set_token_to_request_state)],
		lifespan=lifespan,
	)

	# Add correlation ID middleware
	app.add_middleware(TraceAndLogRequestsMiddleware)
	app.add_middleware(CorrelationIdMiddleware)
	logger.info("Correlation ID middleware registered")

	# Register global exception handlers (per concrete exception type — see
	# register_exception_handlers for why this isn't keyed on `Exception`).
	register_exception_handlers(app)
	logger.info("Global exception handlers registered")

	app.include_router(health_router)
	app.include_router(characters_router)
	app.include_router(chat_router)
	app.include_router(chat_settings_router)
	app.include_router(chat_events_router)
	app.include_router(scenes_router)
	app.include_router(users_router)
	app.include_router(message_router)
	app.include_router(media_router)
	logger.info("API routes registered")

	return app
