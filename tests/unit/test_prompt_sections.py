import pytest

from src.application.chats.prompt_sections import PromptSections, render_system_prompt


@pytest.mark.unit
class TestRenderSystemPrompt:
	def test_system_only_has_no_header(self):
		sections = PromptSections(system="You are a narrator.")
		assert render_system_prompt(sections) == "You are a narrator."

	def test_empty_sections_renders_blank(self):
		assert render_system_prompt(PromptSections()) == ""

	def test_non_empty_sections_get_headers(self):
		sections = PromptSections(system="base", summary="the plot thickened", memories='[User] "hi"')
		out = render_system_prompt(sections)
		assert out.startswith("base")
		assert "[STORY SO FAR]\nthe plot thickened" in out
		assert '[MEMORIES]\n[User] "hi"' in out

	def test_known_facts_slot_renders_when_present(self):
		out = render_system_prompt(PromptSections(facts="A and B are allies."))
		assert "[KNOWN FACTS]\nA and B are allies." in out

	def test_empty_sections_are_omitted(self):
		out = render_system_prompt(PromptSections(system="base", summary="", memories="", facts=""))
		assert "[STORY SO FAR]" not in out
		assert "[MEMORIES]" not in out
		assert "[KNOWN FACTS]" not in out

	def test_is_empty(self):
		assert PromptSections().is_empty() is True
		assert PromptSections(system="x").is_empty() is False
