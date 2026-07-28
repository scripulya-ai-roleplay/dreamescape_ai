from dataclasses import dataclass

from src.application.ports.llm import IPromptService
from src.conf import settings
from src.domain.models import Character, Scene


@dataclass
class PromptService(IPromptService):
	def build_system_prompt(
		self, scene: Scene | None, characters: list[Character], user_character: Character | None = None
	) -> str:
		parts: list[str] = []
		if characters:
			character_lines = [
				"# Characters",
				(
					"These are the non-player characters that YOU (the narrator) portray. "
					"Voice and act for them. NEVER act, speak, or think for the Player Character."
				),
			]
			for character in characters:
				character_lines.append(f"## {character.name}\n{character.system_prompt}".rstrip())
			parts.append("\n\n".join(character_lines))
		if scene is not None:
			scene_lines = ["# Scene", f"## {scene.title}\n{scene.background_prompt}".rstrip()]
			if scene.description:
				scene_lines.append(scene.description.strip())
			parts.append("\n\n".join(scene_lines))
		if user_character is not None:
			persona_lines = [
				"# Player Character (the human's persona)",
				f"## {user_character.name}",
				user_character.system_prompt.rstrip(),
				(
					f"The human player plays AS {user_character.name}. The human and "
					f"{user_character.name} are the SAME person — there is no separate 'user'. "
					f"Every message the human sends is {user_character.name} speaking, acting, "
					f"and thinking. Address {user_character.name} in the second person as 'you'. "
					f"NEVER write {user_character.name}'s dialogue, actions, or decisions."
				),
			]
			parts.append("\n\n".join(persona_lines))
		parts.append(settings.SYSTEM_PROMPT.strip())
		return "\n\n".join(part for part in parts if part).strip()
