import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from src.application.ports.chats import IChatEventGateway
from src.domain.models import Message
from src.infrastructure.logging.logger import Logger

# Bounded so a slow/stalled SSE client can't accumulate unbounded memory.
_LISTENER_MAXSIZE = 32


@dataclass
class ChatEventGateway(IChatEventGateway):
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)
	_listeners: dict[UUID, set[asyncio.Queue]] = field(default_factory=dict)

	def subscribe(self, chat_id: UUID) -> asyncio.Queue:
		queue: asyncio.Queue = asyncio.Queue(maxsize=_LISTENER_MAXSIZE)
		self._listeners.setdefault(chat_id, set()).add(queue)
		self.logger.info("SSE listener subscribed to chat_id=%s (%d total)", chat_id, len(self._listeners[chat_id]))
		return queue

	def unsubscribe(self, chat_id: UUID, queue: asyncio.Queue) -> None:
		listeners = self._listeners.get(chat_id)
		if listeners and queue in listeners:
			listeners.discard(queue)
			if not listeners:
				self._listeners.pop(chat_id, None)
			self.logger.info("SSE listener unsubscribed from chat_id=%s", chat_id)

	def publish(self, chat_id: UUID, event: dict[str, Any]) -> None:
		listeners = self._listeners.get(chat_id)
		if not listeners:
			return
		for queue in listeners:
			try:
				queue.put_nowait(event)
			except asyncio.QueueFull:
				self.logger.warning("SSE listener queue full for chat_id=%s; dropping event", chat_id)

	def publish_message(self, chat_id: UUID, message: Message) -> None:
		self.publish(chat_id, {"message": message.model_dump(mode="json")})
