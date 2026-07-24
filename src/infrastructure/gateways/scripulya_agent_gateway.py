import asyncio
import json
from dataclasses import dataclass, field
from logging import Logger
from uuid import UUID, uuid4

from faststream.rabbit import RabbitBroker
from redis.asyncio import Redis as AsyncRedis

from src.application.chats.settings import ChatSettings
from src.application.ports.chats import IChatEventGateway
from src.application.ports.llm import ILLMChatGateway, IScripulyaAgentClient, LLMRequest, LLMResponse, UserMessageDTO
from src.application.ports.messages import IGenerationHeartbeat
from src.conf import settings
from src.infrastructure.exceptions import LLMGatewayException
from src.infrastructure.gateways.redis_heartbeat import tokens_key

_FLUSH_INTERVAL_SECONDS = 0.025
_FLUSH_TOKEN_BATCH = 16


@dataclass
class ScripulyaAgentClient(IScripulyaAgentClient):
	"""Correlated by a per-call request_id (the RabbitMQ correlation_id), not chat_id:
	the agent reuses it as its heartbeat key and the backend watchdog keys liveness off
	it per-generation."""

	broker: RabbitBroker
	request_queue: str
	timeout: float
	logger: Logger
	heartbeat: IGenerationHeartbeat
	redis: AsyncRedis | None = None
	events: IChatEventGateway | None = None
	_relays: set = field(default_factory=set)

	async def publish(self, req: LLMRequest) -> None:
		chat_id = req.message.chat_id
		request_id = uuid4()
		try:
			await self.broker.publish(
				req.model_dump(mode="json"),
				self.request_queue,
				correlation_id=str(request_id),
				timeout=self.timeout,
			)
		except Exception as exc:  # broker down / publish confirm timeout
			self.logger.warning("scripulya_agent publish failed chat_id=%s: %s", chat_id, exc)
			raise LLMGatewayException(
				message=f"failed to publish request to scripulya_agent: {exc}",
				details={"chat_id": str(chat_id)},
			)
		# Register only after publish succeeds — a failed publish is already surfaced by
		# send_message, and a leftover entry here would be FAILed again by the watchdog.
		await self.heartbeat.register_inflight(str(request_id), chat_id)
		await self._start_token_relay(str(request_id), chat_id)

	async def _start_token_relay(self, request_id: str, chat_id: UUID) -> None:
		if self.redis is None or self.events is None:
			return
		try:
			pubsub = self.redis.pubsub()
			await pubsub.subscribe(tokens_key(request_id))
		except Exception:
			self.logger.warning("token relay subscribe failed rid=%s", request_id, exc_info=True)
			return
		task = asyncio.create_task(self._drain_tokens(pubsub, request_id, chat_id))
		self._relays.add(task)
		task.add_done_callback(self._relays.discard)

	async def _drain_tokens(self, pubsub, request_id: str, chat_id: UUID) -> None:
		loop = asyncio.get_running_loop()
		deadline = loop.time() + settings.LLM_HEARTBEAT_HARD_DEADLINE_SECONDS
		assert self.events is not None
		self.events.publish_generation_start(chat_id, UUID(request_id))
		buffer: list[str] = []
		last_flush = loop.time()
		try:
			timed_out = True
			while loop.time() <= deadline:
				msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=_FLUSH_INTERVAL_SECONDS)
				if msg is None:
					if buffer and loop.time() - last_flush >= _FLUSH_INTERVAL_SECONDS:
						self._flush(buffer, request_id, chat_id)
						buffer = []
						last_flush = loop.time()
					continue
				if msg.get("type") != "message":
					continue
				try:
					frame = json.loads(msg["data"])
				except Exception:
					self.logger.debug("token relay skipped unparseable frame rid=%s", request_id)
					continue
				kind = frame.get("type")
				if kind == "token":
					buffer.append(frame.get("text", ""))
					if len(buffer) >= _FLUSH_TOKEN_BATCH or loop.time() - last_flush >= _FLUSH_INTERVAL_SECONDS:
						self._flush(buffer, request_id, chat_id)
						buffer = []
						last_flush = loop.time()
				elif kind in ("done", "error"):
					timed_out = False
					break
			if timed_out:
				self.logger.warning("token relay deadline exceeded rid=%s", request_id)
		except Exception:
			self.logger.warning("token relay failed rid=%s", request_id, exc_info=True)
		finally:
			if buffer:
				self._flush(buffer, request_id, chat_id)
			self.events.publish_generation_done(chat_id, UUID(request_id))
			try:
				await pubsub.aclose()
			except Exception:
				pass

	def _flush(self, buffer: list[str], request_id: str, chat_id: UUID) -> None:
		text = "".join(buffer)
		if text and self.events is not None:
			self.events.publish_token(chat_id, UUID(request_id), text)


@dataclass
class ScripulyaAgentGateway(ILLMChatGateway):
	"""LLM gateway that delegates generation to scripulya_agent over RabbitMQ."""

	logger: Logger
	_client: IScripulyaAgentClient

	async def submit(
		self,
		message: UserMessageDTO,
		history: list[UserMessageDTO],
		chat_settings: ChatSettings | None = None,
		system_prompt: str = "",
	) -> LLMResponse | None:
		# Fire-and-forget: the reply is persisted and pushed to SSE by the result
		# subscriber. Returns None so the caller leaves the placeholder PENDING.
		await self._client.publish(
			LLMRequest(
				message=message,
				history=history,
				chat_settings=chat_settings,
				system_prompt=system_prompt,
			)
		)
		return None
