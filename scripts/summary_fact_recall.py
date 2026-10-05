import argparse
import asyncio
import json
import math
import statistics
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from faststream.rabbit import RabbitBroker
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from src.application.ports.llm import LLMModelType
from src.application.ports.summarization import SummarySourceMessage
from src.application.summarization import prompts
from src.application.summarization.chapters import plan_chapters
from src.application.summarization.fact_recall import AtomicFact, FactRecallEvaluator
from src.application.summarization.service import SUMMARY_CHAT_SETTINGS
from src.conf import settings
from src.domain.models import ChatRoles, MessageStatus
from src.infrastructure.database.models import Message as MessageModel
from src.infrastructure.gateways.summarization_agent_gateway import AgentRpcTextCompleter
from src.infrastructure.gateways.token_counter import TiktokenTokenCounter


@dataclass
class ChapterScore:
	chunk_tokens: int
	model: str
	chapter_number: int
	source_tokens: int
	summary_tokens: int
	facts: int
	recall: float
	weighted_recall: float
	contradiction_rate: float
	summary: str


@dataclass
class Experiment:
	completer: AgentRpcTextCompleter
	evaluator: FactRecallEvaluator
	counter: TiktokenTokenCounter
	player: str
	target_ratio: float
	min_target_tokens: int
	facts_cache: dict[str, list[AtomicFact]] = field(default_factory=dict)

	async def facts_for(self, transcript: str) -> list[AtomicFact]:
		if transcript not in self.facts_cache:
			self.facts_cache[transcript] = await self.evaluator.extract_facts(transcript)
		return self.facts_cache[transcript]

	async def run(
		self, messages: list[SummarySourceMessage], chunk_tokens: int, model: LLMModelType, max_chapters: int | None
	) -> list[ChapterScore]:
		by_id = {m.id: m for m in messages}
		chapters = plan_chapters(
			messages, lambda m: self.counter.count(prompts.format_line(m, self.player)), chunk_tokens
		)
		if max_chapters is not None:
			chapters = chapters[:max_chapters]
		scores: list[ChapterScore] = []
		previous: str | None = None
		for chapter in chapters:
			transcript = prompts.format_transcript([by_id[i] for i in chapter.message_ids], self.player)
			target = prompts.target_tokens(chapter.tokens_count, self.target_ratio, self.min_target_tokens)
			summary = await self.completer.complete(
				model,
				prompts.build_system_prompt(self.player, target),
				prompts.build_content(transcript, previous),
			)
			report = await self.evaluator.verify(summary, await self.facts_for(transcript))
			scores.append(
				ChapterScore(
					chunk_tokens=chunk_tokens,
					model=model.name,
					chapter_number=chapter.chapter_number,
					source_tokens=chapter.tokens_count,
					summary_tokens=self.counter.count(summary),
					facts=report.facts_total,
					recall=report.recall,
					weighted_recall=report.weighted_recall,
					contradiction_rate=report.contradiction_rate,
					summary=summary,
				)
			)
			print(
				f"  {model.name} chunk={chunk_tokens} chapter={chapter.chapter_number}: "
				f"recall={report.recall:.2f} weighted={report.weighted_recall:.2f} "
				f"contradicted={report.contradiction_rate:.2f} facts={report.facts_total}",
				file=sys.stderr,
			)
			previous = summary
		return scores


def _model(value: str) -> LLMModelType:
	if value in LLMModelType.__members__:
		return LLMModelType[value]
	return LLMModelType(value)


def _percentile(values: list[float], pct: float) -> float:
	ordered = sorted(values)
	rank = max(math.ceil(pct / 100 * len(ordered)) - 1, 0)
	return ordered[rank]


def _load_transcript(path: Path) -> list[SummarySourceMessage]:
	start = datetime(2000, 1, 1, tzinfo=UTC)
	rows = json.loads(path.read_text(encoding="utf-8"))
	return [
		SummarySourceMessage(
			id=uuid4(),
			role=ChatRoles(row["role"]),
			content=row.get("text") or row.get("message") or row.get("content") or "",
			status=MessageStatus.COMPLETED,
			created_at=start + timedelta(seconds=index),
		)
		for index, row in enumerate(rows)
	]


async def _load_chat(chat_id: UUID) -> list[SummarySourceMessage]:
	engine = create_async_engine(settings.DATABASE_URL)
	try:
		async with engine.connect() as conn:
			result = await conn.execute(
				select(
					MessageModel.id,
					MessageModel.role,
					MessageModel.content,
					MessageModel.status,
					MessageModel.created_at,
				)
				.where(MessageModel.chat_id == chat_id)
				.order_by(MessageModel.created_at.asc(), MessageModel.id.asc())
			)
			return [
				SummarySourceMessage(
					id=row.id,
					role=ChatRoles(row.role),
					content=row.content,
					status=MessageStatus(row.status),
					created_at=row.created_at,
				)
				for row in result
			]
	finally:
		await engine.dispose()


def _aggregate(scores: list[ChapterScore]) -> list[dict]:
	groups: dict[tuple[str, int], list[ChapterScore]] = {}
	for score in scores:
		groups.setdefault((score.model, score.chunk_tokens), []).append(score)
	rows = []
	for (model, chunk), items in sorted(groups.items()):
		recalls = [s.weighted_recall for s in items]
		rows.append(
			{
				"model": model,
				"chunk_tokens": chunk,
				"chapters": len(items),
				"median_weighted_recall": statistics.median(recalls),
				"p10_weighted_recall": _percentile(recalls, 10),
				"mean_recall": statistics.fmean(s.recall for s in items),
				"mean_contradiction_rate": statistics.fmean(s.contradiction_rate for s in items),
				"compression": sum(s.summary_tokens for s in items) / max(sum(s.source_tokens for s in items), 1),
			}
		)
	return rows


def _print_table(rows: list[dict], threshold: float, floor: float) -> None:
	header = f"{'model':<22}{'chunk':>7}{'n':>4}{'median':>9}{'p10':>7}{'recall':>8}{'contra':>8}{'compr':>7}  ok"
	print(header)
	print("-" * len(header))
	for row in rows:
		ok = row["median_weighted_recall"] >= threshold and row["p10_weighted_recall"] >= floor
		print(
			f"{row['model']:<22}{row['chunk_tokens']:>7}{row['chapters']:>4}"
			f"{row['median_weighted_recall']:>9.2f}{row['p10_weighted_recall']:>7.2f}"
			f"{row['mean_recall']:>8.2f}{row['mean_contradiction_rate']:>8.2f}{row['compression']:>7.2f}"
			f"  {'yes' if ok else 'no'}"
		)


async def main() -> int:
	parser = argparse.ArgumentParser(
		description="Measure atomic fact recall of chapter summaries across chunk sizes and models."
	)
	source = parser.add_mutually_exclusive_group(required=True)
	source.add_argument("--transcript", type=Path, help='JSON list of {"role": "user|model", "text": "..."}')
	source.add_argument("--chat-id", type=UUID, help="read every message of this chat from DATABASE_URL")
	parser.add_argument("--chunk-sizes", default="2000,3500,5000,7500,10000")
	parser.add_argument("--models", default="gemini_flash_preview", help="comma separated LLMModelType names or values")
	parser.add_argument("--judge", default="claude_sonnet", help="LLMModelType used to extract and verify facts")
	parser.add_argument("--player", default=None, help="name of the player character in the transcript")
	parser.add_argument("--target-ratio", type=float, default=settings.SUMMARY_TARGET_RATIO)
	parser.add_argument("--min-target-tokens", type=int, default=settings.SUMMARY_MIN_TARGET_TOKENS)
	parser.add_argument("--max-chapters", type=int, default=None, help="evaluate only the first N chapters per run")
	parser.add_argument("--threshold", type=float, default=0.85, help="required median weighted recall")
	parser.add_argument("--floor", type=float, default=0.75, help="required 10th percentile weighted recall")
	parser.add_argument("--timeout", type=float, default=float(settings.SUMMARY_PENDING_TIMEOUT_SECONDS))
	parser.add_argument("--out", type=Path, default=None, help="write per-chapter scores and summaries as JSON")
	args = parser.parse_args()

	messages = _load_transcript(args.transcript) if args.transcript else await _load_chat(args.chat_id)
	if not messages:
		print("no messages to evaluate", file=sys.stderr)
		return 1

	broker = RabbitBroker(settings.RABBIT_URL)
	await broker.start()
	try:
		summarizer = AgentRpcTextCompleter(
			broker=broker,
			request_queue=settings.SUMMARY_AGENT_REQUEST_QUEUE,
			timeout=args.timeout,
			chat_settings=SUMMARY_CHAT_SETTINGS,
		)
		experiment = Experiment(
			completer=summarizer,
			evaluator=FactRecallEvaluator(completer=summarizer, judge_model=_model(args.judge)),
			counter=TiktokenTokenCounter(),
			player=prompts.player_label(args.player),
			target_ratio=args.target_ratio,
			min_target_tokens=args.min_target_tokens,
		)
		scores: list[ChapterScore] = []
		for chunk in (int(c) for c in args.chunk_sizes.split(",")):
			for model in (_model(m.strip()) for m in args.models.split(",")):
				try:
					scores.extend(await experiment.run(messages, chunk, model, args.max_chapters))
				except Exception as exc:
					print(f"  {model.name} chunk={chunk}: skipped, {exc}", file=sys.stderr)
	finally:
		await broker.stop()

	rows = _aggregate(scores)
	_print_table(rows, args.threshold, args.floor)
	if args.out is not None:
		args.out.write_text(
			json.dumps(
				{"aggregate": rows, "chapters": [s.__dict__ for s in scores]},
				ensure_ascii=False,
				indent=2,
			),
			encoding="utf-8",
		)
	return 0


if __name__ == "__main__":
	sys.exit(asyncio.run(main()))
