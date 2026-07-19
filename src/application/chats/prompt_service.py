from dataclasses import dataclass

from src.application.ports import IPromptService
from src.conf import settings
from src.domain.models import Character, Scene


@dataclass
class PromptService(IPromptService):
	def build_system_prompt(
		self, scene: Scene | None, characters: list[Character], user_character: Character | None = None
	) -> str:
		parts: list[str] = [settings.SYSTEM_PROMPT.strip()]
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
		return "\n\n".join(part for part in parts if part).strip()
