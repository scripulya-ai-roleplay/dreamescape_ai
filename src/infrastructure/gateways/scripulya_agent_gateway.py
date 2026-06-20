import asyncio
from dataclasses import dataclass, field
from logging import Logger
from typing import NoReturn
from uuid import UUID

from faststream.rabbit import RabbitBroker

from src.application.ports import (
	ILLMChatGateway,
	LLMErrorResponse,
	LLMModelType,
	LLMRequest,
	LLMResponse,
	LLMResult,
	UserMessageDTO,
)
from src.infrastructure.exceptions import (
	ContentSafetyException,
	JSONParsingException,
	LLMGatewayException,
	RateLimitException,
)


def _raise_agent_error(error: LLMErrorResponse) -> NoReturn:
	"""Translate a scripulya_agent LLMErrorResponse into the matching API exception.

	The agent's error codes are mapped onto this service's BaseAPIException
	subclasses so the existing global_exception_handler renders them uniformly.
	The original error_code/status are preserved in `details`.
	"""
	details = {"agent_error_code": error.error_code, "agent_status": error.status, **error.details}
	message = error.message or error.reason or "scripulya_agent error"

	if error.error_code == "rate_limit_exceeded":
		raise RateLimitException(message=message, details=details)
	if error.error_code == "content_safety_blocked":
		raise ContentSafetyException(message=message, details=details)
	if error.error_code == "response_is_invalid":
		raise JSONParsingException(message=message, details=details)
	# provider_auth_failed, model_is_unknown, model_is_inaccessible,
	# internal_error and any unmapped code surface as a generic gateway error.
	raise LLMGatewayException(message=message, details=details)


@dataclass
class ScripulyaAgentClient:
	"""RabbitMQ client for the scripulya_agent worker.

	Publishes LLMRequests to the request queue and correlates each with the
	LLMResult consumed from the fixed result queue by chat_id (scripulya_agent
	echoes it back). A per-chat_id pending-future registry is used because
	scripulya_agent publishes to a fixed queue and does not honour AMQP
	reply_to, so FastStream's rpc=True cannot be used.

	Safe to share as an APP-scoped singleton: all registry access happens on the
	single asyncio event loop.
	"""

	broker: RabbitBroker
	request_queue: str
	timeout: float
	logger: Logger
	_pending: dict[UUID, asyncio.Future] = field(default_factory=dict)

	async def request(self, req: LLMRequest) -> LLMResult:
		"""Publish a request and await its correlated result (or timeout)."""
		chat_id = req.message.chat_id
		fut: asyncio.Future = asyncio.get_running_loop().create_future()
		self._pending[chat_id] = fut
		try:
			await self.broker.publish(
				req.model_dump(mode="json"),
				self.request_queue,
				correlation_id=str(chat_id),
			)
			return await asyncio.wait_for(fut, self.timeout)
		except asyncio.TimeoutError:
			self.logger.warning("scripulya_agent request timed out chat_id=%s", chat_id)
			raise LLMGatewayException(
				message=f"scripulya_agent request timed out after {self.timeout}s",
				details={"chat_id": str(chat_id)},
			)
		finally:
			self._pending.pop(chat_id, None)

	def resolve(self, result: LLMResult) -> None:
		"""Resolve the pending request matching result.chat_id.

		Called by the llm.agent.result subscriber controller. Results without a
		matching pending request (e.g. duplicates / late arrivals) are logged.
		"""
		fut = self._pending.pop(result.chat_id, None)
		if fut is not None and not fut.done():
			fut.set_result(result)
		else:
			self.logger.warning("scripulya_agent result with no pending request chat_id=%s", result.chat_id)


@dataclass
class ScripulyaAgentGateway(ILLMChatGateway):
	"""LLM gateway that delegates generation to scripulya_agent over RabbitMQ."""

	logger: Logger
	_client: ScripulyaAgentClient

	async def generate_response(
		self,
		message: UserMessageDTO,
		history: list[UserMessageDTO],
	) -> LLMResponse:
		result = await self._client.request(LLMRequest(message=message, history=history))

		if result.error is not None:
			self.logger.warning(
				"scripulya_agent error chat_id=%s code=%s",
				message.chat_id,
				result.error.error_code,
			)
			_raise_agent_error(result.error)

		if result.message is None:
			raise LLMGatewayException(
				message="scripulya_agent returned neither a message nor an error",
				details={"chat_id": str(message.chat_id)},
			)

		self.logger.info("scripulya_agent ok chat_id=%s", message.chat_id)
		return LLMResponse(
			text=result.message.message,
			model=message.llm_model or LLMModelType.testing_mock,
			usage=None,
			provider="scripulya_agent",
		)
