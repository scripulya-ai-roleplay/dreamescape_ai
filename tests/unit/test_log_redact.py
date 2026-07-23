import pytest

from src.infrastructure.logging.redact import preview


@pytest.mark.unit
class TestPreview:
	def test_none_is_empty(self):
		assert preview(None) == ""

	def test_empty_is_empty(self):
		assert preview("") == ""

	def test_short_text_unchanged(self):
		assert preview("hello world") == "hello world"

	def test_exactly_max_words_unchanged(self):
		text = "one two three four five six seven eight nine ten"
		assert preview(text) == text

	def test_over_max_words_truncated_with_ellipsis(self):
		text = "one two three four five six seven eight nine ten eleven"
		assert preview(text) == "one two three four five six seven eight nine ten…"

	def test_custom_max_words(self):
		text = "a b c d e"
		assert preview(text, max_words=2) == "a b…"

	def test_long_input_is_truncated_not_full(self):
		text = " ".join(f"token{i}" for i in range(50))
		result = preview(text)
		assert result.endswith("…")
		assert "token49" not in result  # last word must be dropped
		assert len(result) < len(text)
