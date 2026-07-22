import asyncio
import logging
from dataclasses import dataclass, field

from dishka import AsyncContainer, Scope

from src.application.ports import IChatEventGateway, IGenerationHeartbeat, IMessageService
from src.conf import settings
from src.infrastructure.logging.logger import Logger


@dataclass
class GenerationWatchdog:
	_heartbeat: IGenerationHeartbeat
	_events: IChatEventGateway
	_container: AsyncContainer
	logger: logging.Logger = field(default_factory=lambda: logging.getLogger(Logger.LOGGER_NAME))

	async def sweep_once(self) -> None:
		dead = await self._heartbeat.sweep_dead()
		for request_id, chat_id in dead:
			try:
				# A fresh REQUEST scope per item so each FAILED row commits in its own
				# session/UoW — same shape as the RabbitMQ result consumer.
				async with self._container(scope=Scope.REQUEST) as request_container:
					message_service = await request_container.get(IMessageService)
					failed = await message_service.record_failed_generation(
						chat_id, "LLM generation timed out: the agent stopped responding."
					)
				self._events.publish_message(chat_id, failed)
				self.logger.warning(
					"watchdog: agent heartbeat lost for chat_id=%s (request_id=%s); emitted FAILED",
					chat_id,
					request_id,
				)
			except Exception:
				self.logger.exception("watchdog: failed to materialize FAILED for request_id=%s", request_id)

	async def run_forever(self) -> None:
		# Catch per-iteration so a single bad sweep never kills the loop.
		while True:
			try:
				await self.sweep_once()
			except Exception:
				self.logger.exception("watchdog sweep crashed")
			await asyncio.sleep(settings.LLM_SWEEP_INTERVAL_SECONDS)
