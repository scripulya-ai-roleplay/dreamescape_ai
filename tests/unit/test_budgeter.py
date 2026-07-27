from uuid import uuid4

import pytest

from src.application.chats.budgeter import HeuristicTokenCounter, budget
from src.application.chats.prompt_sections import PromptSections
from src.application.ports.llm import UserMessageDTO
from src.domain.models import ChatRoles


def _msg(text: str, role=ChatRoles.USER) -> UserMessageDTO:
	return UserMessageDTO(message=text, chat_id=uuid4(), llm_model=None, role=role)


@pytest.mark.unit
class TestBudget:
	def test_limit_none_keeps_all_history(self):
		counter = HeuristicTokenCounter()
		sections = PromptSections(system="sys")
		history = [_msg(f"turn {i}") for i in range(50)]
		result = budget(sections, history, _msg("now"), limit=None, counter=counter)
		assert len(result.history) == 50

	def test_summary_is_capped(self):
		counter = HeuristicTokenCounter()
		long_summary = "word " * 5000
		sections = PromptSections(system="sys", summary=long_summary)
		result = budget(sections, [], _msg("now"), limit=10000, counter=counter, summary_cap=50)
		assert result.section_tokens["summary"] <= 50

	def test_history_trimmed_oldest_first_to_fit_limit(self):
		counter = HeuristicTokenCounter()
		sections = PromptSections(system="sys")
		history = [_msg(f"turn number {i} " * 20) for i in range(20)]
		result = budget(sections, history, _msg("now"), limit=200, counter=counter)
		assert len(result.history) < 20
		# newest preserved, oldest dropped
		assert result.history[-1].message == history[-1].message
		assert result.history[0].message != history[0].message

	def test_never_evicts_system_or_user(self):
		counter = HeuristicTokenCounter()
		sections = PromptSections(system="sys")
		result = budget(sections, [], _msg("now"), limit=1, counter=counter)
		assert result.section_tokens["system"] > 0
		assert result.section_tokens["user"] > 0

	def test_pinned_indices_always_kept(self):
		counter = HeuristicTokenCounter()
		sections = PromptSections(system="sys")
		history = [_msg(f"turn {i} " * 30) for i in range(10)]
		# pin index 0 (oldest) which would normally be trimmed first
		result = budget(sections, history, _msg("now"), limit=120, counter=counter, pinned_indices={0})
		messages = [m.message for m in result.history]
		assert history[0].message in messages
