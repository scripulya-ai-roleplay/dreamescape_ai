from dataclasses import dataclass
from logging import Logger
from uuid import uuid4

from faststream.rabbit import RabbitBroker

from src.application.chats.settings import ChatSettings
from src.application.ports.llm import ILLMChatGateway, IScripulyaAgentClient, LLMRequest, LLMResponse, UserMessageDTO
from src.application.ports.messages import IGenerationHeartbeat
from src.infrastructure.exceptions import LLMGatewayException


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
