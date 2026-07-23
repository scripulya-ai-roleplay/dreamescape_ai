import logging
from dataclasses import dataclass, field
from uuid import UUID

import redis.asyncio

from src.application.ports.messages import IGenerationHeartbeat
from src.conf import settings
from src.infrastructure.logging.logger import Logger

# The key names + alive/done protocol are a CONTRACT shared with scripulya_agent
# (it writes :alive/:done with the same names) — keep them in sync across repos.
_INFLIGHT_KEY = "gen:inflight"
# Lingers ~1h so a late sweep or a redelivery can't re-FAIL a request the agent
# already finished.
_DONE_TTL_SECONDS = 3600


def _chat_key(request_id: str) -> str:
	return f"gen:{request_id}:chat"


def _alive_key(request_id: str) -> str:
	return f"gen:{request_id}:alive"


def _done_key(request_id: str) -> str:
	return f"gen:{request_id}:done"


@dataclass
class RedisGenerationHeartbeat(IGenerationHeartbeat):
	"""Best-effort: every Redis op is swallowed + logged, so a Redis outage only
	disables the safety net — it must never break generation."""

	_redis: redis.asyncio.Redis
	logger: logging.Logger = field(default_factory=lambda: logging.getLogger(Logger.LOGGER_NAME))

	async def register_inflight(self, request_id: str, chat_id: UUID) -> None:
		try:
			pipe = self._redis.pipeline(transaction=True)
			pipe.sadd(_INFLIGHT_KEY, request_id)
			pipe.set(_chat_key(request_id), str(chat_id), ex=settings.LLM_HEARTBEAT_HARD_DEADLINE_SECONDS)
			pipe.set(_alive_key(request_id), "1", ex=settings.LLM_HEARTBEAT_GRACE_TTL)
			await pipe.execute()
		except Exception:
			self.logger.warning("heartbeat register_inflight failed rid=%s", request_id, exc_info=True)

	async def sweep_dead(self) -> list[tuple[str, UUID]]:
		try:
			request_ids = await self._redis.smembers(_INFLIGHT_KEY)
		except Exception:
			self.logger.warning("heartbeat sweep: could not read inflight set", exc_info=True)
			return []

		dead: list[tuple[str, UUID]] = []
		for rid in request_ids:
			try:
				if await self._redis.exists(_alive_key(rid)):
					continue
				# NX-claim the done marker so a concurrent sweep or the agent's own
				# finish can't both act on the same request (no double-FAIL).
				claimed = await self._redis.set(_done_key(rid), "watchdog", ex=_DONE_TTL_SECONDS, nx=True)
				await self._redis.srem(_INFLIGHT_KEY, rid)
				if not claimed:
					continue
				chat = await self._redis.get(_chat_key(rid))
				if chat:
					dead.append((rid, UUID(chat)))
			except Exception:
				self.logger.warning("heartbeat sweep: failed processing rid=%s", rid, exc_info=True)
		return dead
