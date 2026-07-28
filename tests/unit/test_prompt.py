from uuid import uuid4

import pytest

from src.application.chats.prompt_service import PromptService
from src.conf import settings
from src.domain.models import Character, Scene


def _scene(title: str = "Forest", background: str = "A dark wood.", description: str | None = None) -> Scene:
	return Scene(
		title=title,
		owner_id=uuid4(),
		background_prompt=background,
		description=description,
	)


def _character(name: str = "Aria", system_prompt: str = "A brave knight.") -> Character:
	return Character(name=name, system_prompt=system_prompt)


@pytest.fixture
def service() -> PromptService:
	return PromptService()


@pytest.mark.unit
class TestBuildSystemPrompt:
	def test_global_prompt_always_present(self, service):
		prompt = service.build_system_prompt(None, [])
		assert settings.SYSTEM_PROMPT.strip() in prompt

	def test_characters_block_included(self, service):
		prompt = service.build_system_prompt(None, [_character(name="Aria", system_prompt="A brave knight.")])
		assert "Aria" in prompt
		assert "A brave knight." in prompt
		assert "# Characters" in prompt

	def test_scene_block_included(self, service):
		prompt = service.build_system_prompt(_scene(title="Dark Forest", background="Misty woodland."), [])
		assert "Dark Forest" in prompt
		assert "Misty woodland." in prompt
		assert "# Scene" in prompt

	def test_scene_and_characters_together(self, service):
		prompt = service.build_system_prompt(
			_scene(title="Tavern", background="A loud tavern."),
			[_character(name="Bart", system_prompt="The gruff bartender.")],
		)
		assert settings.SYSTEM_PROMPT.strip() in prompt
		assert "Bart" in prompt
		assert "The gruff bartender." in prompt
		assert "Tavern" in prompt

	def test_empty_characters_omits_characters_block(self, service):
		prompt = service.build_system_prompt(None, [])
		assert "# Characters" not in prompt

	def test_no_scene_omits_scene_block(self, service):
		prompt = service.build_system_prompt(None, [_character()])
		assert "# Scene" not in prompt

	def test_scene_description_optional(self, service):
		prompt = service.build_system_prompt(_scene(description="An ancient ruin."), [])
		assert "An ancient ruin." in prompt

	def test_player_character_block_included(self, service):
		prompt = service.build_system_prompt(None, [], _character(name="Kael", system_prompt="A wandering bard."))
		assert "# Player Character (the human's persona)" in prompt
		assert "Kael" in prompt
		assert "A wandering bard." in prompt

	def test_no_player_character_omits_player_block(self, service):
		prompt = service.build_system_prompt(None, [], None)
		assert "# Player Character" not in prompt

	def test_characters_block_marked_as_narrator_portrayed(self, service):
		prompt = service.build_system_prompt(None, [_character(name="Aria", system_prompt="A brave knight.")])
		assert "YOU (the narrator) portray" in prompt

	def test_player_character_tied_to_human(self, service):
		prompt = service.build_system_prompt(None, [], _character(name="Kael", system_prompt="A wandering bard."))
		assert "plays AS Kael" in prompt
		assert "the SAME person" in prompt
		assert "as 'you'" in prompt

	def test_player_character_disambiguated_from_characters(self, service):
		prompt = service.build_system_prompt(
			None,
			[_character(name="Aria", system_prompt="A brave knight.")],
			_character(name="Kael", system_prompt="A wandering bard."),
		)
		assert prompt.index("# Characters") < prompt.index("# Player Character")

	def test_characters_block_is_first_block(self, service):
		prompt = service.build_system_prompt(
			_scene(title="Forest", background="A dark wood."),
			[_character(name="Aria", system_prompt="A brave knight.")],
			_character(name="Kael", system_prompt="A wandering bard."),
		)
		assert prompt.index("# Characters") == 0

	def test_blocks_ordered_characters_scene_player_global(self, service):
		prompt = service.build_system_prompt(
			_scene(title="Forest", background="A dark wood."),
			[_character(name="Aria", system_prompt="A brave knight.")],
			_character(name="Kael", system_prompt="A wandering bard."),
		)
		assert prompt.index("# Characters") < prompt.index("# Scene")
		assert prompt.index("# Scene") < prompt.index("# Player Character")
		assert prompt.index("# Player Character") < prompt.index("You are the narrator")

	def test_global_prompt_last_even_without_characters(self, service):
		prompt = service.build_system_prompt(_scene(title="Forest", background="A dark wood."), [])
		assert prompt.index("# Scene") < prompt.index("You are the narrator")
