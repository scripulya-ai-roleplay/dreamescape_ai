import json
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from src.application.ports.llm import LLMModelType
from src.application.ports.summarization import ITextCompleter

FACT_EXTRACTION_PROMPT = """You extract atomic facts from a roleplay story transcript.

An atomic fact is one short, self-contained statement that is true according to the transcript: \
a single event, attribute, relationship, location, possession, decision or state.
- Resolve pronouns to names.
- One fact per statement; never merge two facts.
- Skip pure style, mood and filler that has no bearing on the story.
- Write the facts in the language of the transcript.

Rate how much each fact matters for continuing the story:
3 = plot-critical (events, decisions, secrets, relationships)
2 = useful detail (places, objects, states)
1 = minor color

Respond with JSON only, no prose:
{"facts": [{"fact": "...", "weight": 3}]}"""

FACT_VERIFICATION_PROMPT = """You check whether facts are preserved by a summary.

For every numbered fact decide, using ONLY the summary:
- "supported": the summary states it or it clearly follows from it
- "contradicted": the summary states something incompatible with it
- "missing": the summary does not mention it

Respond with JSON only, no prose, one entry per fact with the same ids:
{"verdicts": [{"id": 1, "verdict": "supported"}]}"""


class Verdict(StrEnum):
	SUPPORTED = "supported"
	CONTRADICTED = "contradicted"
	MISSING = "missing"


class AtomicFact(BaseModel):
	model_config = ConfigDict(frozen=True)

	fact: str
	weight: int = Field(default=1, ge=1, le=3)


class FactVerdict(BaseModel):
	model_config = ConfigDict(frozen=True)

	fact: AtomicFact
	verdict: Verdict


class FactRecallReport(BaseModel):
	model_config = ConfigDict(frozen=True)

	verdicts: list[FactVerdict]

	@property
	def facts_total(self) -> int:
		return len(self.verdicts)

	def _count(self, verdict: Verdict) -> int:
		return sum(1 for v in self.verdicts if v.verdict == verdict)

	@property
	def recall(self) -> float:
		return self._count(Verdict.SUPPORTED) / self.facts_total if self.verdicts else 1.0

	@property
	def weighted_recall(self) -> float:
		total = sum(v.fact.weight for v in self.verdicts)
		if total == 0:
			return 1.0
		return sum(v.fact.weight for v in self.verdicts if v.verdict == Verdict.SUPPORTED) / total

	@property
	def contradiction_rate(self) -> float:
		return self._count(Verdict.CONTRADICTED) / self.facts_total if self.verdicts else 0.0


_DECODER = json.JSONDecoder()


def _load_json_object(text: str, key: str) -> dict:
	for start in (i for i, ch in enumerate(text) if ch == "{"):
		try:
			payload, _ = _DECODER.raw_decode(text, start)
		except json.JSONDecodeError:
			continue
		if isinstance(payload, dict) and key in payload:
			return payload
	raise ValueError(f"judge reply has no JSON object with {key!r}: {text[:300]!r}")


def parse_facts(text: str) -> list[AtomicFact]:
	payload = _load_json_object(text, "facts")
	facts = []
	for item in payload.get("facts", []):
		if isinstance(item, str):
			item = {"fact": item}
		fact = str(item.get("fact", "")).strip()
		if not fact:
			continue
		try:
			weight = min(max(int(item.get("weight", 1)), 1), 3)
		except (TypeError, ValueError):
			weight = 1
		facts.append(AtomicFact(fact=fact, weight=weight))
	return facts


def parse_verdicts(text: str, facts: list[AtomicFact]) -> list[FactVerdict]:
	payload = _load_json_object(text, "verdicts")
	by_id: dict[int, Verdict] = {}
	for item in payload.get("verdicts", []):
		try:
			by_id[int(item["id"])] = Verdict(str(item["verdict"]).strip().lower())
		except (KeyError, TypeError, ValueError):
			continue
	return [FactVerdict(fact=fact, verdict=by_id.get(i, Verdict.MISSING)) for i, fact in enumerate(facts, start=1)]


def build_verification_content(summary: str, facts: list[AtomicFact]) -> str:
	numbered = "\n".join(f"{i}. {fact.fact}" for i, fact in enumerate(facts, start=1))
	return f"SUMMARY:\n{summary.strip()}\n\nFACTS:\n{numbered}"


@dataclass
class FactRecallEvaluator:
	completer: ITextCompleter
	judge_model: LLMModelType
	verification_batch_size: int = 40

	async def extract_facts(self, source: str) -> list[AtomicFact]:
		reply = await self.completer.complete(self.judge_model, FACT_EXTRACTION_PROMPT, source)
		return parse_facts(reply)

	async def verify(self, summary: str, facts: list[AtomicFact]) -> FactRecallReport:
		verdicts: list[FactVerdict] = []
		for start in range(0, len(facts), self.verification_batch_size):
			batch = facts[start : start + self.verification_batch_size]
			reply = await self.completer.complete(
				self.judge_model, FACT_VERIFICATION_PROMPT, build_verification_content(summary, batch)
			)
			verdicts.extend(parse_verdicts(reply, batch))
		return FactRecallReport(verdicts=verdicts)

	async def evaluate(self, source: str, summary: str) -> FactRecallReport:
		return await self.verify(summary, await self.extract_facts(source))
