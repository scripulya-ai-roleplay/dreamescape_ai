import logging
from dataclasses import dataclass

from openai import AsyncOpenAI

from src.application.ports.embedder import IEmbedder
from src.infrastructure.logging.logger import Logger


@dataclass
class OpenAIEmbedder(IEmbedder):
	_client: AsyncOpenAI
	_model: str
	_dimension: int
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)

	@property
	def dimension(self) -> int:
		return self._dimension

	async def embed(self, texts: list[str]) -> list[list[float]]:
		if not texts:
			return []
		response = await self._client.embeddings.create(model=self._model, input=texts)
		ordered = sorted(response.data, key=lambda item: item.index)
		return [item.embedding for item in ordered]
