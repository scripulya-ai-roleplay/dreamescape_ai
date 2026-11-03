from src.application.ports.summarization import SummarySourceMessage
from src.domain.models import ChatRoles, MessageStatus

NARRATOR_LABEL = "Narrator"
DEFAULT_PLAYER_LABEL = "Player"

SUMMARY_SYSTEM_PROMPT = """You are the archivist of an ongoing interactive roleplay story.
You receive one chapter of the story transcript and, when it exists, the summary of the chapter before it.

Write a summary of THIS chapter only. The story must be able to continue from your summary alone, \
without the original transcript, so keep every detail that may matter later.

Preserve, in order of importance:
1. Plot events and their consequences, in chronological order.
2. Who is involved: names, roles, relationships and how they changed.
3. Concrete facts: places, objects, promises, secrets, injuries, decisions, numbers, names.
4. The state of each character at the end of the chapter: location, condition, goals, intentions.
5. Unresolved threads and open questions.

Rules:
- Write in the same language as the transcript.
- Third person, past tense, neutral and factual. No commentary, evaluation or speculation.
- The player character is {player}. Refer to them by name, never as "the user" or "the player".
- Do not repeat the previous summary unless something in it changed.
- Never invent anything that is not in the transcript.
- Stay under {target_tokens} tokens. Prefer dense facts over prose.

Output plain text with exactly these sections:
EVENTS:
CHARACTERS:
FACTS:
OPEN THREADS:"""

RECAP_HEADER = (
	"[OOC: recap of earlier story events, written by the archivist. "
	"It is context for continuing the story, not a new action.]"
)


def player_label(persona_name: str | None) -> str:
	return persona_name.strip() if persona_name and persona_name.strip() else DEFAULT_PLAYER_LABEL


def format_line(message: SummarySourceMessage, player: str) -> str:
	if message.status == MessageStatus.FAILED:
		return ""
	speaker = player if message.role == ChatRoles.USER else NARRATOR_LABEL
	return f"{speaker}: {message.content.strip()}"


def format_transcript(messages: list[SummarySourceMessage], player: str) -> str:
	return "\n\n".join(line for line in (format_line(m, player) for m in messages) if line)


def target_tokens(source_tokens: int, ratio: float, minimum: int) -> int:
	return max(int(source_tokens * ratio), minimum)


def build_system_prompt(player: str, target: int) -> str:
	return SUMMARY_SYSTEM_PROMPT.format(player=player, target_tokens=target)


def build_content(transcript: str, previous_summary: str | None) -> str:
	parts = []
	if previous_summary:
		parts.append(f"<previous_summary>\n{previous_summary.strip()}\n</previous_summary>")
	parts.append(f"<transcript>\n{transcript}\n</transcript>")
	return "\n\n".join(parts)


def format_recap(content: str) -> str:
	return f"{RECAP_HEADER}\n{content.strip()}"
