from dataclasses import dataclass

from src.application.chats.settings import (
	DEFAULT_CHAT_SETTINGS,
	ChatSettings,
	ControlBehavior,
	Perspective,
	TokenLimit,
)
from src.application.ports.llm import IPromptService
from src.conf import settings
from src.domain.models import Character, Scene

_PERSPECTIVE_INSTRUCTIONS = {
	Perspective.FIRST_PERSON: 'Write the narration in the FIRST person, from the Player Character\'s point of view, using "I".',
	Perspective.SECOND_PERSON: 'Write the narration in the SECOND person, addressing the Player Character as "you".',
	Perspective.THIRD_PERSON: "Write the narration in the THIRD person, referring to the Player Character by name.",
}

_RESPONSE_LENGTH_INSTRUCTIONS = {
	TokenLimit.CAPPED: "Keep each response to about 3-4 paragraphs.",
	TokenLimit.HIGH: "Keep each response to about 4-5 paragraphs.",
	TokenLimit.MAX: "Do not impose any length restriction; write as long as the scene calls for.",
}

_CONTROL_INSTRUCTIONS = {
	ControlBehavior.CONTROL: (
		"Treat the player's message as direction for what the Player Character attempts, and write "
		"the Player Character's actions, dialogue, and reactions to carry it out, alongside the "
		"world and the non-player Characters."
	),
	ControlBehavior.DONT_CONTROL: (
		"Never write the Player Character's dialogue, actions, thoughts, or decisions. Narrate only "
		"the world, the scene, and the non-player Characters; the player alone controls the Player "
		"Character."
	),
}

_CONTINUE_INSTRUCTIONS = {
	ControlBehavior.CONTROL: (
		'When the player\'s message is only a nudge to keep going (for example just "Continue"), '
		"you may freely write the Player Character's actions and dialogue to advance the story."
	),
	ControlBehavior.DONT_CONTROL: (
		'When the player\'s message is only a nudge to keep going (for example just "Continue"), '
		"continue the scene WITHOUT writing the Player Character's actions or dialogue; advance "
		"only the world and the non-player Characters."
	),
}


@dataclass
class PromptService(IPromptService):
	def build_system_prompt(
		self,
		scene: Scene | None,
		characters: list[Character],
		user_character: Character | None = None,
		chat_settings: ChatSettings | None = None,
	) -> str:
		storytelling = chat_settings or DEFAULT_CHAT_SETTINGS
		parts: list[str] = []
		if characters:
			character_lines = [
				"# Characters",
				"These are the non-player characters that YOU (the narrator) portray. Voice and act for them.",
			]
			if storytelling.aiControlBehavior == ControlBehavior.DONT_CONTROL:
				character_lines.append("NEVER act, speak, or think for the Player Character.")
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
					f"{user_character.name} are the SAME person — there is no separate 'user'."
				),
			]
			parts.append("\n\n".join(persona_lines))
		parts.append(self._storytelling_directive(storytelling))
		parts.append(settings.SYSTEM_PROMPT.strip())
		return "\n\n".join(part for part in parts if part).strip()

	@staticmethod
	def _storytelling_directive(chat_settings: ChatSettings) -> str:
		lines = [
			"# Storytelling",
			f"- Point of view: {_PERSPECTIVE_INSTRUCTIONS[chat_settings.perspective]}",
			f"- Length: {_RESPONSE_LENGTH_INSTRUCTIONS[chat_settings.responseTokenLimit]}",
			f"- Player Character control: {_CONTROL_INSTRUCTIONS[chat_settings.aiControlBehavior]}",
			f'- On a "Continue" prompt: {_CONTINUE_INSTRUCTIONS[chat_settings.continueBehavior]}',
		]
		return "\n".join(lines)
