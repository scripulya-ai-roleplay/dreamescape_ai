from dataclasses import dataclass
from logging import Logger

from faststream.rabbit import RabbitBroker

from src.application.chats.settings import ChatSettings
from src.application.ports import (
	ILLMChatGateway,
	IScripulyaAgentClient,
	LLMRequest,
	LLMResponse,
	UserMessageDTO,
)
from src.infrastructure.exceptions import LLMGatewayException


@dataclass
class ScripulyaAgentClient(IScripulyaAgentClient):
	"""Fire-and-forget RabbitMQ publisher for the scripulya_agent worker.

	Publishes LLMRequests to the request queue (correlated by chat_id) and returns
	immediately. The reply arrives later on the llm.agent.result queue and is handled
	by the result subscriber (controllers/rabbit/v1/llm.py), which persists it and
	notifies the chat SSE listeners. There is no in-process awaiting here — the HTTP
	request returns 202 as soon as the request is queued.

	Safe to share as an APP-scoped singleton.
	"""

	broker: RabbitBroker
	request_queue: str
	timeout: float
	logger: Logger

	async def publish(self, req: LLMRequest) -> None:
		"""Publish a request to scripulya_agent, correlated by chat_id."""
		chat_id = req.message.chat_id
		try:
			await self.broker.publish(
				req.model_dump(mode="json"),
				self.request_queue,
				correlation_id=str(chat_id),
				timeout=self.timeout,
			)
		except Exception as exc:  # broker down / publish confirm timeout
			self.logger.warning("scripulya_agent publish failed chat_id=%s: %s", chat_id, exc)
			raise LLMGatewayException(
				message=f"failed to publish request to scripulya_agent: {exc}",
				details={"chat_id": str(chat_id)},
			)


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
