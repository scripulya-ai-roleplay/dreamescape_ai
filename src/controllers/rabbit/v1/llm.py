from dishka.integrations.faststream import FromDishka

from src.application.ports import LLMResult
from src.conf import settings
from src.controllers.rabbit.v1.broker import broker
from src.infrastructure.gateways.scripulya_agent_gateway import ScripulyaAgentClient


@broker.subscriber(settings.LLM_AGENT_RESULT_QUEUE)
async def handle_agent_result(
	result: LLMResult,
	client: FromDishka[ScripulyaAgentClient],
) -> None:
	"""Consume an LLMResult published by scripulya_agent and resolve the awaiting request.

	scripulya_agent publishes every result to this fixed queue; correlation back to
	the originating request is by chat_id (see ScripulyaAgentClient.resolve).
	"""
	client.resolve(result)
