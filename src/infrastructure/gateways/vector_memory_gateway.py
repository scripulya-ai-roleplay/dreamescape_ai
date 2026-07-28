import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.embedder import IEmbedder
from src.application.ports.memory import IVectorMemoryGateway, MemoryChunk
from src.conf import settings
from src.infrastructure.database.models import ChatMemory as ChatMemoryModel
from src.infrastructure.logging.logger import Logger


@dataclass
class PgVectorMemoryGateway(IVectorMemoryGateway):
	_session: AsyncSession
	_embedder: IEmbedder
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)

	async def store(self, chat_id: UUID, message_id: UUID, role: str, content: str) -> None:
		embeddings = await self._embedder.embed([content])
		embedding = embeddings[0]
		stmt = (
			pg_insert(ChatMemoryModel)
			.values(
				chat_id=chat_id,
				message_id=message_id,
				role=role,
				content=content,
				embedding=embedding,
			)
			.on_conflict_do_nothing(index_elements=[ChatMemoryModel.chat_id, ChatMemoryModel.message_id])
		)
		await self._session.execute(stmt)

	async def retrieve(
		self,
		chat_id: UUID,
		query: str,
		k: int = settings.MEMORIES_K,
		max_distance: float = settings.MEMORIES_MAX_DISTANCE,
		exclude_message_ids: set[UUID] | None = None,
		dedup_embedding: list[float] | None = None,
		dedup_max_distance: float = 0.08,
	) -> list[MemoryChunk]:
		await self._session.execute(text("SET LOCAL hnsw.ef_search = :ef"), {"ef": settings.MEMORIES_EF_SEARCH})
		embeddings = await self._embedder.embed([query])
		query_embedding = embeddings[0]

		distance = ChatMemoryModel.embedding.cosine_distance(query_embedding).label("distance")
		columns: list = [ChatMemoryModel, distance]
		if dedup_embedding is not None:
			columns.append(ChatMemoryModel.embedding.cosine_distance(dedup_embedding).label("dedup_distance"))
		stmt = select(*columns).where(ChatMemoryModel.chat_id == chat_id).order_by(distance).limit(k * 3)
		rows = (await self._session.execute(stmt)).all()

		excluded = exclude_message_ids or set()
		chunks: list[MemoryChunk] = []
		for row in rows:
			model = row[0]
			query_distance = row[1]
			if query_distance > max_distance:
				continue
			if model.message_id in excluded:
				continue
			if dedup_embedding is not None and row[2] < dedup_max_distance:
				continue
			chunks.append(
				MemoryChunk(
					message_id=model.message_id,
					role=model.role,
					content=model.content,
					distance=query_distance,
					embedding=list(model.embedding) if model.embedding is not None else None,
				)
			)
			if len(chunks) >= k:
				break
		return chunks
