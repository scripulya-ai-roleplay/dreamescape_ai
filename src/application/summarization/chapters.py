from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.application.ports.summarization import SummarySourceMessage
from src.application.summarization.schemas import SummaryChapter


class PlannedChapter(BaseModel):
	model_config = ConfigDict(frozen=True)

	chapter_number: int
	message_ids: list[UUID]
	tokens_count: int
	covered_from_at: datetime
	covered_until_at: datetime

	@property
	def from_message_id(self) -> UUID:
		return self.message_ids[0]

	@property
	def until_message_id(self) -> UUID:
		return self.message_ids[-1]

	def to_chapter(self) -> SummaryChapter:
		return SummaryChapter(
			chapter_number=self.chapter_number,
			messages_count=len(self.message_ids),
			from_message_id=self.from_message_id,
			until_message_id=self.until_message_id,
			tokens_count=self.tokens_count,
		)


def _is_summarizable(message: SummarySourceMessage) -> bool:
	return not message.is_archived and message.summary_id is None


def plan_chapters(
	messages: list[SummarySourceMessage],
	message_tokens: Callable[[SummarySourceMessage], int],
	chunk_tokens: int,
) -> list[PlannedChapter]:
	ordered = sorted(messages, key=lambda m: (m.created_at, str(m.id)))
	runs: list[list[SummarySourceMessage]] = []
	current_run: list[SummarySourceMessage] = []
	for message in ordered:
		if _is_summarizable(message):
			current_run.append(message)
		elif current_run:
			runs.append(current_run)
			current_run = []
	if current_run:
		runs.append(current_run)

	chapters: list[PlannedChapter] = []
	for run in runs:
		chunk: list[SummarySourceMessage] = []
		chunk_size = 0
		for message in run:
			size = message_tokens(message)
			if chunk and chunk_size + size > chunk_tokens:
				chapters.append(_to_planned(len(chapters) + 1, chunk, chunk_size))
				chunk = []
				chunk_size = 0
			chunk.append(message)
			chunk_size += size
		if chunk:
			chapters.append(_to_planned(len(chapters) + 1, chunk, chunk_size))
	return chapters


def _to_planned(number: int, chunk: list[SummarySourceMessage], tokens: int) -> PlannedChapter:
	return PlannedChapter(
		chapter_number=number,
		message_ids=[m.id for m in chunk],
		tokens_count=tokens,
		covered_from_at=chunk[0].created_at,
		covered_until_at=chunk[-1].created_at,
	)
