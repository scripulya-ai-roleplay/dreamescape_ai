from pydantic import BaseModel

_SYSTEM_HEADERS: tuple[tuple[str, str], ...] = (
	("STORY SO FAR", "summary"),
	("KNOWN FACTS", "facts"),
	("MEMORIES", "memories"),
	("REMINDER", "reminder"),
)


class PromptSections(BaseModel):
	system: str = ""
	summary: str = ""
	facts: str = ""
	memories: str = ""
	reminder: str = ""

	def is_empty(self) -> bool:
		return not any(getattr(self, attr).strip() for attr in ("system", "summary", "facts", "memories", "reminder"))


def render_system_prompt(sections: PromptSections) -> str:
	parts: list[str] = []
	if sections.system.strip():
		parts.append(sections.system.strip())
	for header, attr in _SYSTEM_HEADERS:
		body = getattr(sections, attr).strip()
		if body:
			parts.append(f"[{header}]\n{body}")
	return "\n\n".join(parts).strip()
