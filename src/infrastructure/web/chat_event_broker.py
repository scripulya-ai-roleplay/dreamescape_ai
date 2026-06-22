import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from src.domain.models import Message

logger = logging.getLogger(__name__)

# Bounded so a slow/stalled SSE client can't accumulate unbounded memory.
_LISTENER_MAXSIZE = 32


@dataclass
class ChatEventBroker:
	"""In-process fan-out of chat message events to SSE listeners.

	APP-scoped singleton. The RabbitMQ result subscriber (and the offline mock
	gateway path) publish completed/failed messages here; each open SSE connection
	owns an asyncio.Queue subscribed under its chat_id. All access happens on the
	single asyncio event loop, so no locking is required.

	Single-process only: with multiple uvicorn workers / replicas, a result consumed
	by one worker will not reach an SSE client connected to another. To scale, move
	the fan-out onto Redis pub/sub or a RabbitMQ broadcast (fanout) exchange.
	"""

	_listeners: dict[UUID, set[asyncio.Queue]] = field(default_factory=dict)

	def subscribe(self, chat_id: UUID) -> asyncio.Queue:
		queue: asyncio.Queue = asyncio.Queue(maxsize=_LISTENER_MAXSIZE)
		self._listeners.setdefault(chat_id, set()).add(queue)
		logger.info("SSE listener subscribed to chat_id=%s (%d total)", chat_id, len(self._listeners[chat_id]))
		return queue

	def unsubscribe(self, chat_id: UUID, queue: asyncio.Queue) -> None:
		listeners = self._listeners.get(chat_id)
		if listeners and queue in listeners:
			listeners.discard(queue)
			if not listeners:
				self._listeners.pop(chat_id, None)
			logger.info("SSE listener unsubscribed from chat_id=%s", chat_id)

	def publish(self, chat_id: UUID, event: dict[str, Any]) -> None:
		listeners = self._listeners.get(chat_id)
		if not listeners:
			return
		for queue in listeners:
			try:
				queue.put_nowait(event)
			except asyncio.QueueFull:
				logger.warning("SSE listener queue full for chat_id=%s; dropping event", chat_id)

	def publish_message(self, chat_id: UUID, message: Message) -> None:
		"""Publish a model-message lifecycle event.

		The SSE endpoint derives the frame's `event:` name (`message` vs `error`)
		from `message.status`.
		"""
		self.publish(chat_id, {"message": message.model_dump(mode="json")})
