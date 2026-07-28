import abc


class IEmbedder(abc.ABC):
	@property
	@abc.abstractmethod
	def dimension(self) -> int: ...

	@abc.abstractmethod
	async def embed(self, texts: list[str]) -> list[list[float]]: ...
