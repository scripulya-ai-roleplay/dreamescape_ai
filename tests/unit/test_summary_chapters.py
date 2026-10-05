from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from src.application.ports.summarization import SummarySourceMessage
from src.application.summarization import prompts
from src.application.summarization.chapters import plan_chapters
from src.domain.models import ChatRoles, MessageStatus

BASE = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def _message(index, tokens, *, archived=False, claimed=False, role=ChatRoles.USER, status=MessageStatus.COMPLETED):
	return SummarySourceMessage(
		id=uuid4(),
		role=role,
		content="x" * tokens,
		status=status,
		created_at=BASE + timedelta(minutes=index),
		is_archived=archived,
		summary_id=uuid4() if claimed else None,
	)


def _length(message):
	return len(message.content)


@pytest.mark.unit
class TestPlanChapters:
	def test_greedy_split_respects_budget(self):
		messages = [_message(i, 2000) for i in range(5)]

		chapters = plan_chapters(messages, _length, 5000)

		assert [len(c.message_ids) for c in chapters] == [2, 2, 1]
		assert [c.tokens_count for c in chapters] == [4000, 4000, 2000]
		assert [c.chapter_number for c in chapters] == [1, 2, 3]
		assert chapters[0].from_message_id == messages[0].id
		assert chapters[0].until_message_id == messages[1].id
		assert chapters[0].covered_from_at == messages[0].created_at
		assert chapters[0].covered_until_at == messages[1].created_at

	def test_oversized_message_becomes_its_own_chapter(self):
		messages = [_message(0, 100), _message(1, 9000), _message(2, 100)]

		chapters = plan_chapters(messages, _length, 5000)

		assert [c.message_ids for c in chapters] == [[messages[0].id], [messages[1].id], [messages[2].id]]

	def test_archived_and_claimed_messages_split_runs(self):
		messages = [
			_message(0, 100),
			_message(1, 100, archived=True),
			_message(2, 100),
			_message(3, 100, claimed=True),
			_message(4, 100),
		]

		chapters = plan_chapters(messages, _length, 5000)

		assert [c.message_ids for c in chapters] == [[messages[0].id], [messages[2].id], [messages[4].id]]

	def test_orders_by_creation_time(self):
		late = _message(5, 100)
		early = _message(1, 100)

		chapters = plan_chapters([late, early], _length, 5000)

		assert chapters[0].message_ids == [early.id, late.id]

	def test_empty_chat_has_no_chapters(self):
		assert plan_chapters([], _length, 5000) == []

	def test_to_chapter_exposes_public_shape(self):
		messages = [_message(0, 10), _message(1, 20)]

		chapter = plan_chapters(messages, _length, 5000)[0].to_chapter()

		assert chapter.chapter_number == 1
		assert chapter.messages_count == 2
		assert chapter.from_message_id == messages[0].id
		assert chapter.until_message_id == messages[1].id
		assert chapter.tokens_count == 30


@pytest.mark.unit
class TestSummaryPrompts:
	def test_transcript_labels_speakers_and_skips_failed(self):
		messages = [
			_message(0, 0, role=ChatRoles.MODEL).model_copy(update={"content": "The gate creaks."}),
			_message(1, 0).model_copy(update={"content": "I step inside."}),
			_message(2, 0, role=ChatRoles.MODEL, status=MessageStatus.FAILED).model_copy(update={"content": "boom"}),
		]

		transcript = prompts.format_transcript(messages, "Arin")

		assert transcript == "Narrator: The gate creaks.\n\nArin: I step inside."

	def test_player_label_falls_back(self):
		assert prompts.player_label(None) == prompts.DEFAULT_PLAYER_LABEL
		assert prompts.player_label("  ") == prompts.DEFAULT_PLAYER_LABEL
		assert prompts.player_label(" Mira ") == "Mira"

	def test_content_includes_previous_summary_when_present(self):
		content = prompts.build_content("Arin: hi", "Earlier they met.")

		assert content.index("<previous_summary>") < content.index("<transcript>")
		assert "Earlier they met." in content
		assert "<previous_summary>" not in prompts.build_content("Arin: hi", None)

	def test_target_tokens_has_floor(self):
		assert prompts.target_tokens(5000, 0.25, 200) == 1250
		assert prompts.target_tokens(100, 0.25, 200) == 200

	def test_system_prompt_mentions_player_and_budget(self):
		prompt = prompts.build_system_prompt("Arin", 1250)

		assert "Arin" in prompt
		assert "1250 tokens" in prompt
