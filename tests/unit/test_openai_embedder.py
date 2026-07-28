from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infrastructure.gateways.openai_embedder import OpenAIEmbedder


@pytest.mark.unit
@pytest.mark.asyncio
async def test_embed_returns_vectors_sorted_by_index():
	client = AsyncMock()
	client.embeddings.create = AsyncMock(
		return_value=SimpleNamespace(
			data=[
				SimpleNamespace(index=1, embedding=[0.2, 0.0, 0.0, 0.0]),
				SimpleNamespace(index=0, embedding=[0.1, 0.0, 0.0, 0.0]),
			]
		)
	)
	embedder = OpenAIEmbedder(_client=client, _model="text-embedding-3-small", _dimension=1536)

	result = await embedder.embed(["a", "b"])

	assert result == [[0.1, 0.0, 0.0, 0.0], [0.2, 0.0, 0.0, 0.0]]
	assert embedder.dimension == 1536


@pytest.mark.unit
@pytest.mark.asyncio
async def test_embed_empty_input_returns_empty():
	embedder = OpenAIEmbedder(_client=AsyncMock(), _model="m", _dimension=4)
	assert await embedder.embed([]) == []
