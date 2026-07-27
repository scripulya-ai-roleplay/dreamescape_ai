import asyncio
import logging
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

import redis.asyncio

from src.application.chats.prompt_sections import PromptSections
from src.application.chats.settings import MemorySettings
from src.application.ports.chats import IChatSettingsGateway
from src.application.ports.common import IUnitOfWork
from src.application.ports.embedder import IEmbedder
from src.application.ports.memory import (
	EnrichResult,
	IGraphMemoryGateway,
	IMemoryService,
	ISummaryGateway,
	IVectorMemoryGateway,
	MemoryChunk,
)
from src.application.ports.messages import IMessageGateway
from src.conf import settings
from src.domain.models import ChatRoles
from src.infrastructure.logging.logger import Logger

if TYPE_CHECKING:
	from src.application.memory.summary_service import SummaryService

_DEFAULT_MEMORY_SETTINGS = MemorySettings()


@dataclass
class MemoryService(IMemoryService):
	summary_gateway: ISummaryGateway
	vector_gateway: IVectorMemoryGateway
	graph_gateway: IGraphMemoryGateway
	message_gateway: IMessageGateway
	chat_settings_gateway: IChatSettingsGateway
	summary_service: "SummaryService"
	_uow: IUnitOfWork
	_embedder: IEmbedder | None = None
	_redis: redis.asyncio.Redis | None = None
	logger: logging.Logger = field(default_factory=lambda: logging.getLogger(Logger.LOGGER_NAME))

	async def enrich(self, chat_id: UUID, user_msg: str, memory_settings: MemorySettings | None = None) -> EnrichResult:
		per_chat = memory_settings or _DEFAULT_MEMORY_SETTINGS
		summary_enabled = settings.SUMMARY_ENABLED and per_chat.summaryEnabled
		vector_enabled = settings.VECTOR_MEMORY_ENABLED and per_chat.vectorMemoryEnabled
		graph_enabled = settings.GRAPH_MEMORY_ENABLED and per_chat.graphMemoryEnabled

		latest_summary = await self._safe(self.summary_gateway.latest(chat_id) if summary_enabled else _none(), None)
		boundary = latest_summary.to_message_id if latest_summary else None
		tail_limit = settings.HISTORY_MAX_TAIL if summary_enabled else None
		tail = await self._safe(self.message_gateway.tail_after(chat_id, boundary, tail_limit), [])
		exclude_ids = {message.id for message in tail if message.id is not None}
		summary_text = latest_summary.content if latest_summary else ""

		dedup_embedding = await self._safe(self._embed(summary_text), None) if summary_text else None

		chunks, facts = await asyncio.gather(
			self._safe(self._retrieve_chunks(chat_id, user_msg, vector_enabled, exclude_ids, dedup_embedding), []),
			self._safe(self._retrieve_facts(chat_id, user_msg, graph_enabled), []),
		)

		chunks = await self._dedup_chunks_vs_facts(chunks, facts)
		sections = PromptSections(
			summary=summary_text, memories=_render_chunks(chunks), facts="\n".join(f for f in facts if f)
		)
		return EnrichResult(sections=sections, tail=tail)

	async def ingest(self, chat_id: UUID, model_reply_message_id: UUID) -> None:
		per_chat = await self._memory_settings(chat_id)
		if not await self._acquire_ingest_lock(chat_id, model_reply_message_id):
			self.logger.info("memory ingest skipped (already done) chat_id=%s mid=%s", chat_id, model_reply_message_id)
			return

		model_message = await self.message_gateway.get_one(model_reply_message_id)
		user_message = await self.message_gateway.message_before(chat_id, model_reply_message_id)

		if settings.VECTOR_MEMORY_ENABLED and per_chat.vectorMemoryEnabled:
			try:
				async with self._uow:
					if user_message is not None:
						await self.vector_gateway.store(
							chat_id, user_message.id, user_message.role.value, user_message.message
						)
					await self.vector_gateway.store(
						chat_id, model_reply_message_id, model_message.role.value, model_message.message
					)
			except Exception:
				self.logger.warning("vector memory store failed chat_id=%s", chat_id, exc_info=True)

		if settings.GRAPH_MEMORY_ENABLED and per_chat.graphMemoryEnabled:
			try:
				reference_time = model_message.date_created or datetime.now(UTC)
				await self.graph_gateway.store(
					chat_id,
					user_message.message if user_message is not None else "",
					model_message.message,
					reference_time,
				)
			except Exception:
				self.logger.warning("graph memory store failed chat_id=%s", chat_id, exc_info=True)

		if settings.SUMMARY_ENABLED and per_chat.summaryEnabled:
			try:
				await self.summary_service.maybe_fold(chat_id)
			except Exception:
				self.logger.warning("summary fold failed chat_id=%s", chat_id, exc_info=True)

	async def _retrieve_chunks(
		self,
		chat_id: UUID,
		query: str,
		vector_enabled: bool,
		exclude_ids: set[UUID],
		dedup_embedding: list[float] | None,
	) -> list[MemoryChunk]:
		if not vector_enabled:
			return []
		return await self.vector_gateway.retrieve(
			chat_id,
			query,
			k=settings.MEMORIES_K,
			max_distance=settings.MEMORIES_MAX_DISTANCE,
			exclude_message_ids=exclude_ids,
			dedup_embedding=dedup_embedding,
		)

	async def _retrieve_facts(self, chat_id: UUID, query: str, graph_enabled: bool) -> list[str]:
		if not graph_enabled:
			return []
		return await self.graph_gateway.retrieve(chat_id, query)

	async def _dedup_chunks_vs_facts(self, chunks: list[MemoryChunk], facts: list[str]) -> list[MemoryChunk]:
		# Drop a verbatim chunk that restates a graph fact (the fact is already in [KNOWN FACTS]).
		if not chunks or not facts or self._embedder is None:
			return chunks
		try:
			fact_embeddings = await self._embedder.embed(facts)
		except Exception:
			self.logger.warning("fact dedup embedding failed", exc_info=True)
			return chunks
		threshold = 1 - settings.MEMORY_SUMMARY_DEDUP_SIMILARITY
		kept: list[MemoryChunk] = []
		for chunk in chunks:
			if chunk.embedding is None or not any(
				_cosine_distance(chunk.embedding, fact_embedding) < threshold for fact_embedding in fact_embeddings
			):
				kept.append(chunk)
		return kept

	async def _memory_settings(self, chat_id: UUID) -> MemorySettings:
		try:
			chat_settings = await self.chat_settings_gateway.get_for_chat(chat_id)
			return chat_settings.memory if chat_settings is not None else _DEFAULT_MEMORY_SETTINGS
		except Exception:
			self.logger.warning("failed to load memory settings chat_id=%s", chat_id, exc_info=True)
			return _DEFAULT_MEMORY_SETTINGS

	async def _embed(self, text: str) -> list[float] | None:
		if self._embedder is None:
			return None
		embeddings = await self._embedder.embed([text])
		return embeddings[0] if embeddings else None

	async def _acquire_ingest_lock(self, chat_id: UUID, model_reply_message_id: UUID) -> bool:
		if self._redis is None:
			return True
		key = f"memory:ingested:{chat_id}:{model_reply_message_id}"
		set_ok = await self._redis.set(key, "1", nx=True, ex=settings.MEMORY_INGEST_IDEMPOTENCY_TTL_SECONDS)
		return bool(set_ok)

	async def _safe(self, coro, default):
		try:
			return await asyncio.wait_for(coro, timeout=settings.MEMORY_SOURCE_TIMEOUT_MS / 1000)
		except Exception:
			self.logger.warning("memory source failed", exc_info=True)
			return default


def _render_chunks(chunks: list[MemoryChunk]) -> str:
	if not chunks:
		return ""
	lines: list[str] = []
	for chunk in chunks:
		label = "User" if chunk.role == ChatRoles.USER.value else "Character"
		lines.append(f'[{label}] "{chunk.content}"')
	return "\n".join(lines)


def _cosine_distance(a: list[float], b: list[float]) -> float:
	dot = sum(x * y for x, y in zip(a, b, strict=False))
	norm_a = math.sqrt(sum(x * x for x in a))
	norm_b = math.sqrt(sum(y * y for y in b))
	if norm_a == 0 or norm_b == 0:
		return 1.0
	return 1.0 - (dot / (norm_a * norm_b))


async def _none() -> None:
	return None
