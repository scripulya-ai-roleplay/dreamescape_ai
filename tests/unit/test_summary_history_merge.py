from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from src.application.chats.llm_service import LLMChatsService
from src.application.ports.common import Page
from src.application.ports.llm import LLMModelType
from src.application.summarization.prompts import RECAP_HEADER
from src.domain.models import ChatRoles, ChatSummary, Message, SummaryStatus

BASE = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def _page(chat_id, minutes):
	newest_first = [
		Message(message=f"m{m}", chat_id=chat_id, role=ChatRoles.USER, date_created=BASE + timedelta(minutes=m))
		for m in sorted(minutes, reverse=True)
	]
	return Page[Message](items=newest_first, count=len(newest_first), offset=0, limit=100)


def _summary(chat_id, start, end, content):
	return ChatSummary(
		id=uuid4(),
		chat_id=chat_id,
		content=content,
		status=SummaryStatus.COMPLETED,
		llm_model=LLMModelType.claude_sonnet.value,
		covered_from_at=BASE + timedelta(minutes=start),
		covered_until_at=BASE + timedelta(minutes=end),
		messages_count=1,
		source_tokens=10,
	)


def _texts(history):
	return [h.message.split("\n", 1)[1] if h.message.startswith(RECAP_HEADER) else h.message for h in history]


@pytest.mark.unit
class TestMergeHistory:
	def test_recaps_take_the_place_of_archived_ranges(self):
		chat_id = uuid4()
		page = _page(chat_id, [2, 5, 9])
		summaries = [_summary(chat_id, 6, 8, "s2"), _summary(chat_id, 0, 1, "s1")]

		history = LLMChatsService._merge_history(page, summaries, chat_id, LLMModelType.claude_sonnet)

		assert _texts(history) == ["s1", "m2", "m5", "s2", "m9"]
		recap = history[0]
		assert recap.role == ChatRoles.USER
		assert recap.message.startswith(RECAP_HEADER)
		assert recap.llm_model == LLMModelType.claude_sonnet

	def test_trailing_recap_when_everything_is_archived(self):
		chat_id = uuid4()

		history = LLMChatsService._merge_history(_page(chat_id, []), [_summary(chat_id, 0, 10, "all")], chat_id, None)

		assert _texts(history) == ["all"]

	def test_no_summaries_keeps_history_untouched(self):
		chat_id = uuid4()

		history = LLMChatsService._merge_history(_page(chat_id, [1, 2]), [], chat_id, None)

		assert _texts(history) == ["m1", "m2"]
