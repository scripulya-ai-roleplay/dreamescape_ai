from dataclasses import dataclass
from logging import Logger

from src.application.ports.llm import IScripulyaAgentClient, LLMRequest


@dataclass
class MockScripulyaAgentClient(IScripulyaAgentClient):
	"""Offline stand-in for ScripulyaAgentClient.

	Selected when LLM_AGENT_ENABLED is false so the app builds and runs in local
	docker without RabbitMQ or the scripulya_agent worker. publish() is a logged
	no-op: the fire-and-forget request is dropped. Pair with the testing_mock LLM
	model for a fully offline chat flow; real models stay PENDING here (nothing
	consumes the request, and the broker is never started).
	"""

	logger: Logger

	async def publish(self, req: LLMRequest) -> None:
		self.logger.info(
			"mock scripulya_agent client: dropping LLM request chat_id=%s (LLM_AGENT_ENABLED=false)",
			req.message.chat_id,
		)
