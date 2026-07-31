import json

import pytest

from src.application.imports.lorebook import LorebookParser
from src.infrastructure.exceptions import InvalidLorebookException

parser = LorebookParser()


def _dump(entries):
	return json.dumps({"entries": entries}).encode()


@pytest.mark.unit
class TestLorebookParser:
	def test_parse_standard_shape_classifies_by_group(self):
		raw = _dump(
			{
				"0": {"comment": "Laeral Silverhand", "content": "Open Lord of Waterdeep.", "group": "Character"},
				"1": {"comment": "Amn", "content": "Wealthy mercantile nation.", "group": "location"},
				"2": {"comment": "bard", "content": "Musical magicians.", "group": "class"},
			}
		)
		lorebook = parser.parse(raw)

		assert len(lorebook.entries) == 3
		by_name = {e.name: e for e in lorebook.entries}
		assert by_name["Laeral Silverhand"].is_character is True
		assert by_name["Laeral Silverhand"].is_location is False
		assert by_name["Amn"].is_location is True
		assert by_name["Amn"].is_character is False
		assert by_name["bard"].is_character is False
		assert by_name["bard"].is_location is False

	def test_group_matching_is_case_insensitive(self):
		raw = _dump({"0": {"comment": "Cleric", "content": "Holy warrior.", "group": "  CHARACTER "}})
		lorebook = parser.parse(raw)
		assert lorebook.entries[0].is_character is True

	def test_accepts_entries_as_list(self):
		raw = json.dumps({"entries": [{"comment": "x", "content": "y", "group": "location"}]}).encode()
		lorebook = parser.parse(raw)
		assert len(lorebook.entries) == 1
		assert lorebook.entries[0].is_location is True

	def test_accepts_v2_character_book_location(self):
		raw = json.dumps(
			{"data": {"character_book": {"entries": {"0": {"comment": "x", "content": "y", "group": "location"}}}}}
		).encode()
		lorebook = parser.parse(raw)
		assert len(lorebook.entries) == 1

	def test_missing_entries_raises(self):
		with pytest.raises(InvalidLorebookException) as exc:
			parser.parse(json.dumps({"name": "no entries here"}).encode())
		assert exc.value.status_code == 422
		assert exc.value.error_code == "INVALID_LOREBOOK"

	def test_malformed_json_raises(self):
		with pytest.raises(InvalidLorebookException):
			parser.parse(b'{ "entries": {"0": {')

	def test_skips_entries_without_name_or_content(self):
		raw = _dump(
			{
				"0": {"comment": "ok", "content": "has both", "group": "Character"},
				"1": {"comment": "", "content": "no name", "group": "class"},
				"2": {"comment": "no content", "content": "", "group": "class"},
				"3": "not a dict",
			}
		)
		lorebook = parser.parse(raw)
		assert len(lorebook.entries) == 1
		assert lorebook.skipped == 3

	def test_extract_image_urls_markdown_and_bare(self):
		text = "see https://x.com/a.png and ![](http://y.org/b.jpg) plus https://z.com/c.jpeg?w=1"
		assert parser._extract_image_urls(text) == [
			"http://y.org/b.jpg",
			"https://x.com/a.png",
			"https://z.com/c.jpeg?w=1",
		]

	def test_extract_image_urls_dedups(self):
		text = "![](https://x.com/a.png) again https://x.com/a.png"
		assert parser._extract_image_urls(text) == ["https://x.com/a.png"]

	def test_extract_image_urls_ignores_non_image_links(self):
		assert parser._extract_image_urls("visit https://x.com/page.html now") == []

	def test_synthesize_greeting(self):
		greeting = parser.greeting("Amn", "Wealthy mercantile nation.")
		assert greeting.startswith("You find yourself in Amn.")
		assert "Wealthy mercantile nation." in greeting

	def test_build_world_context_excludes_character_and_location(self):
		raw = _dump(
			{
				"0": {"comment": "Laeral", "content": "Open Lord.", "group": "Character"},
				"1": {"comment": "Amn", "content": "Nation.", "group": "location"},
				"2": {"comment": "bard", "content": "Musician.", "group": "class"},
				"3": {"comment": "orc", "content": "Warlike.", "group": "Lore"},
			}
		)
		lorebook = parser.parse(raw)
		context = parser.world_context(lorebook.entries)
		assert "World context:" in context
		assert "bard: Musician." in context
		assert "orc: Warlike." in context
		assert "Laeral" not in context
		assert "Amn" not in context

	def test_build_world_context_empty_when_only_mapped_entries(self):
		raw = _dump({"0": {"comment": "Amn", "content": "Nation.", "group": "location"}})
		lorebook = parser.parse(raw)
		assert parser.world_context(lorebook.entries) == ""

	def test_non_string_comment_or_content_skipped_not_crash(self):
		raw = _dump(
			{
				"0": {"comment": 123, "content": "has text", "group": "Character"},
				"1": {"comment": "ok", "content": ["not", "str"], "group": "Character"},
				"2": {"comment": {"weird": True}, "content": "has text", "group": "Character"},
				"3": {"comment": "good", "content": "valid", "group": "Character"},
			}
		)
		lorebook = parser.parse(raw)
		assert [e.name for e in lorebook.entries] == ["good"]
		assert lorebook.skipped == 3

	def test_non_string_group_coerced_to_empty(self):
		raw = _dump({"0": {"comment": "x", "content": "y", "group": 99}})
		lorebook = parser.parse(raw)
		assert len(lorebook.entries) == 1
		assert lorebook.entries[0].group == ""
		assert lorebook.entries[0].is_character is False

	def test_entry_key_is_dict_key_for_mapping(self):
		raw = _dump(
			{
				"0": {"comment": "a", "content": "x", "group": "Character"},
				"7": {"comment": "b", "content": "y", "group": "location"},
			}
		)
		lorebook = parser.parse(raw)
		by_name = {e.name: e for e in lorebook.entries}
		assert by_name["a"].key == "0"
		assert by_name["b"].key == "7"

	def test_entry_key_is_index_for_list(self):
		raw = json.dumps(
			{
				"entries": [
					{"comment": "a", "content": "x", "group": "Character"},
					{"comment": "b", "content": "y", "group": "location"},
				]
			}
		).encode()
		lorebook = parser.parse(raw)
		assert [e.key for e in lorebook.entries] == ["0", "1"]
