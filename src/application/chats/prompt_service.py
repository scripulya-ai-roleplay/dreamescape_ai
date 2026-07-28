from dataclasses import dataclass

from src.application.chats.prompt_sections import PromptSections, render_system_prompt
from src.application.ports.llm import IPromptService
from src.conf import settings
from src.domain.models import Character, Scene

_CHARS_PER_TOKEN = 4
_REMINDER_WORDS_PER_ENTRY = 30


@dataclass
class PromptService(IPromptService):
	def _assemble_system_block(
		self, scene: Scene | None, characters: list[Character], user_character: Character | None = None
	) -> str:
		parts: list[str] = []
		if characters:
			character_lines = ["# Characters"]
			for character in characters:
				character_lines.append(f"## {character.name}\n{character.system_prompt}".rstrip())
			parts.append("\n\n".join(character_lines))
		if scene is not None:
			scene_lines = ["# Scene", f"## {scene.title}\n{scene.background_prompt}".rstrip()]
			if scene.description:
				scene_lines.append(scene.description.strip())
			parts.append("\n\n".join(scene_lines))
		if user_character is not None:
			parts.append(f"# User\n## {user_character.name}\n{user_character.system_prompt}".rstrip())
		parts.append(settings.SYSTEM_PROMPT.strip())
		return "\n\n".join(part for part in parts if part).strip()

	def build_system_prompt(
		self, scene: Scene | None, characters: list[Character], user_character: Character | None = None
	) -> str:
		return render_system_prompt(self.build_prompt_sections(scene, characters, user_character))

	def build_prompt_sections(
		self, scene: Scene | None, characters: list[Character], user_character: Character | None = None
	) -> PromptSections:
		return PromptSections(system=self._assemble_system_block(scene, characters, user_character))

	def build_reminder(
		self, scene: Scene | None, characters: list[Character], user_character: Character | None = None
	) -> str:
		lines: list[str] = []
		for character in characters or []:
			lines.append(f"{character.name}: {_first_words(character.system_prompt, _REMINDER_WORDS_PER_ENTRY)}")
		if user_character is not None:
			lines.append(
				f"(you play as) {user_character.name}: "
				f"{_first_words(user_character.system_prompt, _REMINDER_WORDS_PER_ENTRY)}"
			)
		if scene is not None:
			lines.append(f"setting [{scene.title}]: {_first_sentence(scene.background_prompt)}")
		body = "\n".join(lines).strip()
		char_cap = settings.REMINDER_TOKEN_CAP * _CHARS_PER_TOKEN
		if len(body) > char_cap:
			body = body[:char_cap].rstrip() + "…"
		return body


def _first_words(text: str, count: int) -> str:
	words = text.split()
	if len(words) <= count:
		return " ".join(words)
	return " ".join(words[:count]) + "…"


def _first_sentence(text: str) -> str:
	stripped = text.strip()
	for delim in (". ", "! ", "? "):
		idx = stripped.find(delim)
		if idx > 0:
			return stripped[: idx + 1]
	return stripped
