import abc

from src.domain.models import Message


class ISummaryModel(abc.ABC):
	@abc.abstractmethod
	async def summarize(self, prior_summary: str | None, messages: list[Message]) -> str: ...
