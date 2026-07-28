from __future__ import annotations

import abc
from dataclasses import dataclass, field

from src.application.chats.prompt_sections import PromptSections
from src.application.ports.llm import UserMessageDTO
from src.conf import settings

_PER_MESSAGE_OVERHEAD = 4
_CHARS_PER_TOKEN = 4


class TokenCounter(abc.ABC):
	@abc.abstractmethod
	def count(self, text: str) -> int: ...

	def count_message(self, msg: UserMessageDTO) -> int:
		return self.count(msg.message) + _PER_MESSAGE_OVERHEAD


class HeuristicTokenCounter(TokenCounter):
	def count(self, text: str) -> int:
		return max(1, len(text) // _CHARS_PER_TOKEN)


class TiktokenCounter(TokenCounter):
	def __init__(self) -> None:
		import tiktoken

		self._enc = tiktoken.get_encoding("cl100k_base")

	def count(self, text: str) -> int:
		return len(self._enc.encode(text))


@dataclass
class BudgetResult:
	sections: PromptSections
	history: list[UserMessageDTO]
	used_tokens: int
	section_tokens: dict[str, int] = field(default_factory=dict)


def _cap_section(text: str, cap: int, counter: TokenCounter) -> str:
	body = text.strip()
	if not body or counter.count(body) <= cap:
		return body
	candidate = body[: cap * _CHARS_PER_TOKEN]
	for delim in (". ", "! ", "? ", ".\n", "\n\n"):
		idx = candidate.rfind(delim)
		if idx > 0:
			candidate = candidate[: idx + 1]
			break
	while counter.count(candidate) > cap and len(candidate) > 1:
		candidate = candidate[:-1]
	return candidate.rstrip()


def budget(
	sections: PromptSections,
	history: list[UserMessageDTO],
	user_msg: UserMessageDTO,
	limit: int | None,
	counter: TokenCounter,
	*,
	summary_cap: int = settings.SUMMARY_TOKEN_CAP,
	memories_cap: int = settings.MEMORIES_TOKEN_CAP,
	pinned_indices: set[int] | None = None,
) -> BudgetResult:
	pinned_indices = pinned_indices or set()

	capped_summary = _cap_section(sections.summary, summary_cap, counter)
	capped_memories = _cap_section(sections.memories, memories_cap, counter)

	system_tokens = counter.count(sections.system)
	reminder_tokens = counter.count(sections.reminder)
	summary_tokens = counter.count(capped_summary)
	memories_tokens = counter.count(capped_memories)
	user_tokens = counter.count_message(user_msg)
	fixed = system_tokens + reminder_tokens + summary_tokens + memories_tokens + user_tokens

	counts = [counter.count_message(m) for m in history]
	if limit is None:
		kept = [True] * len(history)
	else:
		budget_left = max(0, limit - fixed)
		kept = [False] * len(history)
		for i in range(len(history) - 1, -1, -1):
			cost = counts[i]
			if i in pinned_indices or cost <= budget_left:
				kept[i] = True
				budget_left -= cost

	trimmed = [history[i] for i in range(len(history)) if kept[i]]
	history_tokens = sum(counts[i] for i in range(len(history)) if kept[i])

	capped_sections = PromptSections(
		system=sections.system,
		summary=capped_summary,
		facts=sections.facts,
		memories=capped_memories,
		reminder=sections.reminder,
	)
	section_tokens = {
		"system": system_tokens,
		"summary": summary_tokens,
		"memories": memories_tokens,
		"reminder": reminder_tokens,
		"history": history_tokens,
		"user": user_tokens,
	}
	used_tokens = fixed + history_tokens

	return BudgetResult(
		sections=capped_sections,
		history=trimmed,
		used_tokens=used_tokens,
		section_tokens=section_tokens,
	)
