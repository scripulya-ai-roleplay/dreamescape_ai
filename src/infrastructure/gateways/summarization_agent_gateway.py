from dataclasses import dataclass
from logging import Logger
from uuid import uuid4

from faststream.rabbit import RabbitBroker

from src.application.chats.settings import ChatSettings
from src.application.ports.llm import LLMErrorResponse, LLMModelType
from src.application.ports.summarization import (
	ISummarizationAgentGateway,
	ITextCompleter,
	SummaryRequest,
	SummaryResult,
)
from src.infrastructure.exceptions import LLMGatewayException


@dataclass
class SummarizationAgentGateway(ISummarizationAgentGateway):
	broker: RabbitBroker
	request_queue: str
	timeout: float
	logger: Logger

	async def submit(self, request: SummaryRequest) -> SummaryResult | None:
		try:
			await self.broker.publish(
				request.model_dump(mode="json"),
				self.request_queue,
				correlation_id=str(request.summary_id),
				timeout=self.timeout,
			)
		except Exception as exc:
			self.logger.warning("summary request publish failed summary_id=%s: %s", request.summary_id, exc)
			raise LLMGatewayException(
				message=f"failed to publish summary request to scripulya_agent: {exc}",
				details={"summary_id": str(request.summary_id), "chat_id": str(request.chat_id)},
			)
		self.logger.info("summary request published summary_id=%s model=%s", request.summary_id, request.llm_model)
		return None


@dataclass
class DisabledSummarizationAgentGateway(ISummarizationAgentGateway):
	logger: Logger

	async def submit(self, request: SummaryRequest) -> SummaryResult | None:
		self.logger.info(
			"scripulya_agent disabled: dropping summary request summary_id=%s (LLM_AGENT_ENABLED=false)",
			request.summary_id,
		)
		return SummaryResult(
			summary_id=request.summary_id,
			chat_id=request.chat_id,
			error=LLMErrorResponse(
				error_code="agent_disabled",
				status=503,
				reason="Summarization agent is disabled",
				message="scripulya_agent is disabled (LLM_AGENT_ENABLED=false); use testing_mock to summarize offline",
			),
		)


@dataclass
class MockSummarizationGateway(ISummarizationAgentGateway):
	logger: Logger

	async def submit(self, request: SummaryRequest) -> SummaryResult | None:
		self.logger.info("mock summarization gateway received summary_id=%s", request.summary_id)
		return SummaryResult(
			summary_id=request.summary_id,
			chat_id=request.chat_id,
			text=f"Mock summary of {len(request.content)} characters of transcript.",
		)


@dataclass
class AgentRpcTextCompleter(ITextCompleter):
	broker: RabbitBroker
	request_queue: str
	timeout: float
	chat_settings: ChatSettings | None = None

	async def complete(self, llm_model: LLMModelType, system_prompt: str, content: str) -> str:
		request = SummaryRequest(
			summary_id=uuid4(),
			chat_id=uuid4(),
			llm_model=llm_model,
			system_prompt=system_prompt,
			content=content,
			chat_settings=self.chat_settings,
		)
		response = await self.broker.request(
			request.model_dump(mode="json"),
			self.request_queue,
			correlation_id=str(request.summary_id),
			timeout=self.timeout,
		)
		result = SummaryResult.model_validate(await response.decode())
		if result.error is not None:
			raise LLMGatewayException(
				message=f"{result.error.error_code}: {result.error.message}",
				details={"llm_model": llm_model.value},
			)
		return result.text or ""
