from dataclasses import dataclass

from src.application.ports import IPromptService
from src.conf import settings
from src.domain.models import Character, Scene


@dataclass
class PromptService(IPromptService):
	def build_system_prompt(self, scene: Scene | None, characters: list[Character]) -> str:
		parts: list[str] = [settings.SYSTEM_PROMPT.strip()]
		if characters:
			character_lines = ["# Персонажи"]
			for character in characters:
				character_lines.append(f"## {character.name}\n{character.system_prompt}".rstrip())
			parts.append("\n\n".join(character_lines))
		if scene is not None:
			scene_lines = ["# Сцена", f"## {scene.title}\n{scene.background_prompt}".rstrip()]
			if scene.description:
				scene_lines.append(scene.description.strip())
			parts.append("\n\n".join(scene_lines))
		return "\n\n".join(part for part in parts if part).strip()
