import asyncio
import logging
from contextlib import asynccontextmanager

from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.application.ports.media import IObjectStorageGateway
from src.application.streaming.llm_watchdog import GenerationWatchdog
from src.conf import settings
from src.controllers.api.v1.auth import router as auth_router
from src.controllers.api.v1.auth_dependencies import set_token_to_request_state
from src.controllers.api.v1.characters import router as characters_router
from src.controllers.api.v1.chat_events import router as chat_events_router
from src.controllers.api.v1.chat_settings import router as chat_settings_router
from src.controllers.api.v1.chats import router as chat_router
from src.controllers.api.v1.health import router as health_router
from src.controllers.api.v1.media import router as media_router
from src.controllers.api.v1.memory import router as memory_router
from src.controllers.api.v1.messages import router as message_router
from src.controllers.api.v1.scenes import router as scenes_router
from src.controllers.api.v1.users import router as users_router
from src.controllers.rabbit.v1 import llm as rabbit_llm  # noqa: F401  registers the result subscriber
from src.controllers.rabbit.v1.broker import broker
from src.infrastructure.web.global_exceptions_handler import register_exception_handlers
from src.infrastructure.web.middlewares import TraceAndLogRequestsMiddleware

logger = logging.getLogger(__name__)

_DIMENSION_QUERY = (
	"SELECT atttypmod FROM pg_attribute WHERE attrelid = 'chat_memories'::regclass AND attname = 'embedding'"
)


async def _verify_embedding_dimension(container) -> None:
	# pgvector bakes the dimension into the column type (atttypmod). A mismatch between the
	# configured embedder dimension and the stored column means every store would silently fail
	# (caught and degraded in ingest), so surface it loudly at startup rather than per-write.
	if not settings.VECTOR_MEMORY_ENABLED:
		return
	try:
		engine = await container.get(AsyncEngine)
		async with engine.connect() as conn:
			column_dim = (await conn.execute(text(_DIMENSION_QUERY))).scalar_one_or_none()
	except Exception:
		logger.warning("Could not verify pgvector embedding dimension at startup", exc_info=True)
		return
	if column_dim is None:
		logger.info("chat_memories not present yet; skipping embedding dimension check")
		return
	if column_dim != settings.EMBEDDING_DIMENSION:
		logger.error(
			"Embedding dimension mismatch: configured=%d but chat_memories.embedding is vector(%d). "
			"Switching embedders requires ALTERing the column and re-embedding existing rows.",
			settings.EMBEDDING_DIMENSION,
			column_dim,
		)
		return
	logger.info("pgvector embedding dimension verified: vector(%d)", settings.EMBEDDING_DIMENSION)


@asynccontextmanager
async def lifespan(app: FastAPI):
	try:
		storage = await app.state.dishka_container.get(IObjectStorageGateway)
		await storage.ensure_buckets()
		logger.info("Media buckets ensured")
	except Exception:
		logger.warning("Could not ensure media buckets at startup; will retry on first upload", exc_info=True)

	await _verify_embedding_dimension(app.state.dishka_container)

	if not settings.LLM_AGENT_ENABLED:
		logger.info("scripulya_agent disabled (LLM_AGENT_ENABLED=false); RabbitMQ broker not started")
		yield
		return

	await broker.start()
	logger.info("RabbitMQ broker started; consuming %s", settings.LLM_AGENT_RESULT_QUEUE)

	# Anti-hang watchdog: marks in-flight generations FAILED when the agent's Redis
	# heartbeat expires, so a dead/stalled agent can't hang the client SSE forever.
	watchdog_task: asyncio.Task[None] | None = None
	try:
		watchdog = await app.state.dishka_container.get(GenerationWatchdog)
		watchdog_task = asyncio.create_task(watchdog.run_forever())
		logger.info("Generation watchdog started (sweep every %ss)", settings.LLM_SWEEP_INTERVAL_SECONDS)
	except Exception:
		logger.warning("Could not start generation watchdog; anti-hang safety net inactive", exc_info=True)

	try:
		yield
	finally:
		if watchdog_task is not None:
			watchdog_task.cancel()
			try:
				await watchdog_task
			except asyncio.CancelledError:
				pass
			logger.info("Generation watchdog stopped")
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
	app.include_router(auth_router)
	app.include_router(characters_router)
	app.include_router(chat_router)
	app.include_router(chat_settings_router)
	app.include_router(chat_events_router)
	app.include_router(scenes_router)
	app.include_router(users_router)
	app.include_router(message_router)
	app.include_router(media_router)
	app.include_router(memory_router)
	logger.info("API routes registered")

	return app
