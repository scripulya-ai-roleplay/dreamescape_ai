from unittest.mock import AsyncMock

import pytest

from src.application.ports.llm import LLMModelType
from src.application.ports.summarization import ITextCompleter
from src.application.summarization.fact_recall import (
	FACT_EXTRACTION_PROMPT,
	FACT_VERIFICATION_PROMPT,
	AtomicFact,
	FactRecallEvaluator,
	FactRecallReport,
	FactVerdict,
	Verdict,
	parse_facts,
	parse_verdicts,
)


@pytest.mark.unit
class TestParsing:
	def test_parse_facts_tolerates_fences_and_bad_weights(self):
		reply = """```json
{"facts": [{"fact": "Arin hid the key", "weight": 3}, {"fact": "It rained", "weight": "x"},
 {"fact": "", "weight": 2}, "Mira is a guard", {"fact": "Big", "weight": 9}]}
```"""

		facts = parse_facts(reply)

		assert facts == [
			AtomicFact(fact="Arin hid the key", weight=3),
			AtomicFact(fact="It rained", weight=1),
			AtomicFact(fact="Mira is a guard", weight=1),
			AtomicFact(fact="Big", weight=3),
		]

	def test_parse_facts_without_json_raises(self):
		with pytest.raises(ValueError):
			parse_facts("no json here")

	def test_parse_verdicts_defaults_missing_ids(self):
		facts = [AtomicFact(fact="a"), AtomicFact(fact="b"), AtomicFact(fact="c")]
		reply = '{"verdicts": [{"id": 1, "verdict": "Supported"}, {"id": 3, "verdict": "contradicted"}, {"id": 2}]}'

		verdicts = parse_verdicts(reply, facts)

		assert [v.verdict for v in verdicts] == [Verdict.SUPPORTED, Verdict.MISSING, Verdict.CONTRADICTED]


@pytest.mark.unit
class TestReport:
	def test_metrics(self):
		report = FactRecallReport(
			verdicts=[
				FactVerdict(fact=AtomicFact(fact="a", weight=3), verdict=Verdict.SUPPORTED),
				FactVerdict(fact=AtomicFact(fact="b", weight=1), verdict=Verdict.MISSING),
				FactVerdict(fact=AtomicFact(fact="c", weight=1), verdict=Verdict.CONTRADICTED),
				FactVerdict(fact=AtomicFact(fact="d", weight=1), verdict=Verdict.SUPPORTED),
			]
		)

		assert report.facts_total == 4
		assert report.recall == 0.5
		assert report.weighted_recall == pytest.approx(4 / 6)
		assert report.contradiction_rate == 0.25

	def test_empty_report_is_perfect(self):
		report = FactRecallReport(verdicts=[])

		assert report.recall == 1.0
		assert report.weighted_recall == 1.0
		assert report.contradiction_rate == 0.0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_evaluator_extracts_then_verifies_in_batches():
	completer = AsyncMock(spec=ITextCompleter)
	completer.complete.side_effect = [
		'{"facts": [{"fact": "f1", "weight": 2}, {"fact": "f2", "weight": 2}, {"fact": "f3", "weight": 2}]}',
		'{"verdicts": [{"id": 1, "verdict": "supported"}, {"id": 2, "verdict": "missing"}]}',
		'{"verdicts": [{"id": 1, "verdict": "supported"}]}',
	]
	evaluator = FactRecallEvaluator(
		completer=completer, judge_model=LLMModelType.claude_sonnet, verification_batch_size=2
	)

	report = await evaluator.evaluate("source text", "summary text")

	assert report.facts_total == 3
	assert report.recall == pytest.approx(2 / 3)
	calls = completer.complete.await_args_list
	assert calls[0].args == (LLMModelType.claude_sonnet, FACT_EXTRACTION_PROMPT, "source text")
	assert calls[1].args[1] == FACT_VERIFICATION_PROMPT
	assert "1. f1\n2. f2" in calls[1].args[2]
	assert "1. f3" in calls[2].args[2]


@pytest.mark.unit
def test_parse_skips_prose_braces_and_trailing_text():
	reply = 'Sure {not json}. {"verdicts": [{"id": 1, "verdict": "supported"}]} Hope this helps {:)}'

	verdicts = parse_verdicts(reply, [AtomicFact(fact="a")])

	assert verdicts[0].verdict == Verdict.SUPPORTED
