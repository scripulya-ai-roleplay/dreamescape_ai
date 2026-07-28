import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from src.application.memory.graph_entities import ENTITY_TYPES
from src.application.ports.memory import IGraphMemoryGateway
from src.conf import settings
from src.infrastructure.logging.logger import Logger


def _build_graphiti() -> Any:
	# Imported lazily so the backend starts even when FalkorDB is absent and GRAPH_MEMORY_ENABLED
	# is off; the falkordb client connects on construction, so this only runs on first use.
	from graphiti_core import Graphiti
	from graphiti_core.driver.falkordb_driver import FalkorDriver
	from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
	from graphiti_core.llm_client.config import LLMConfig
	from graphiti_core.llm_client.openai_client import OpenAIClient

	driver = FalkorDriver(
		host=settings.FALKORDB_HOST,
		port=settings.FALKORDB_PORT,
		username=settings.FALKORDB_USERNAME or None,
		password=settings.FALKORDB_PASSWORD or None,
		database=settings.FALKORDB_DATABASE,
	)
	llm_client = OpenAIClient(
		LLMConfig(
			api_key=settings.OPENAI_API_KEY,
			base_url=settings.OPENAI_BASE_URL,
			model=settings.GRAPH_EXTRACTION_MODEL,
			small_model=settings.GRAPH_SMALL_MODEL,
		)
	)
	embedder = OpenAIEmbedder(OpenAIEmbedderConfig(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL))
	return Graphiti(graph_driver=driver, llm_client=llm_client, embedder=embedder)


@dataclass
class GraphitiMemoryGateway(IGraphMemoryGateway):
	_graphiti: Any = None
	_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
	logger: logging.Logger = field(default_factory=lambda: logging.getLogger(Logger.LOGGER_NAME))

	async def _ensure(self) -> Any:
		if self._graphiti is None:
			async with self._lock:
				if self._graphiti is None:
					self._graphiti = _build_graphiti()
		return self._graphiti

	async def store(self, chat_id: UUID, user_msg: str, model_reply: str, reference_time: datetime) -> None:
		graphiti = await self._ensure()
		episode_body = f"[User] {user_msg}\n[Character] {model_reply}".strip()
		await graphiti.add_episode(
			name=str(chat_id),
			episode_body=episode_body,
			source_description="roleplay turn",
			reference_time=reference_time,
			group_id=str(chat_id),
			entity_types=ENTITY_TYPES,
		)

	async def retrieve(self, chat_id: UUID, query: str) -> list[str]:
		graphiti = await self._ensure()
		edges = await graphiti.search(
			query,
			group_ids=[str(chat_id)],
			num_results=settings.GRAPH_MEMORY_SEARCH_RESULTS,
		)
		facts = [edge.fact for edge in edges if edge.invalid_at is None and edge.expired_at is None and edge.fact]
		return facts[: settings.GRAPH_MEMORY_MAX_FACTS]

	async def delete_group(self, chat_id: UUID) -> None:
		graphiti = await self._ensure()
		await graphiti.driver.execute_query("MATCH (n {group_id: $group_id}) DETACH DELETE n", group_id=str(chat_id))
