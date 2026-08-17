import json
import re
from dataclasses import dataclass, field

from src.application.ports.imports import ILorebookParser
from src.infrastructure.exceptions import InvalidLorebookException

_CHARACTER_GROUP = "character"
_LOCATION_GROUP = "location"

_GREETING_CONTENT_LIMIT = 300
_WORLD_CONTEXT_PER_ENTRY = 400
_MAX_WORLD_CONTEXT_CHARS = 8000

# Sentinel candidate keys. Entry keys in a SillyTavern file are the raw
# `entries` object keys (or list indices), which are always digits — these
# literals can never collide with real entry keys.
CARD_KEY = "__card__"
WHOLE_BOOK_KEY = "__whole_book__"

_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\((https?://[^\s)]+?)(?:\s+\"[^\"]*\")?\)")
_BARE_IMAGE_RE = re.compile(
	r"https?://[^\s)\"']+\.(?:png|jpe?g|webp|gif|bmp|tiff|ico)(?:[?#][^\s)\"']*)?",
	re.IGNORECASE,
)


@dataclass(frozen=True)
class LorebookEntry:
	key: str
	uid: int | str | None
	name: str
	content: str
	group: str
	image_urls: list[str] = field(default_factory=list)

	@property
	def is_character(self) -> bool:
		return self.group.strip().lower() == _CHARACTER_GROUP

	@property
	def is_location(self) -> bool:
		return self.group.strip().lower() == _LOCATION_GROUP


@dataclass(frozen=True)
class Lorebook:
	entries: list[LorebookEntry]
	skipped: int = 0
	name: str | None = None
	card_description: str | None = None


@dataclass(frozen=True)
class ParsedImportFile:
	entries: list[LorebookEntry]
	skipped: int = 0
	card_name: str | None = None
	card_description: str | None = None
	file_title: str | None = None

	@property
	def has_card(self) -> bool:
		return bool(self.card_name and self.card_description)


class LorebookParser(ILorebookParser):
	def parse(self, raw: bytes) -> Lorebook:
		parsed = self.parse_file(raw)
		return Lorebook(
			entries=parsed.entries,
			skipped=parsed.skipped,
			name=parsed.file_title,
			card_description=parsed.card_description if parsed.card_name else None,
		)

	def parse_file(self, raw: bytes) -> ParsedImportFile:
		try:
			payload = json.loads(raw.decode("utf-8"))
		except (UnicodeDecodeError, json.JSONDecodeError) as exc:
			raise InvalidLorebookException(message=f"Lorebook is not valid JSON: {exc}")

		card_name, card_description = self._extract_card(payload)
		file_title = self._as_text(payload.get("name")) if isinstance(payload, dict) else None

		entries_obj = self._extract_entries(payload)
		if entries_obj is None:
			if card_name and card_description:
				return ParsedImportFile(
					entries=[],
					card_name=card_name,
					card_description=card_description,
					file_title=file_title,
				)
			raise InvalidLorebookException(message="Lorebook JSON has no 'entries' object or array")

		if isinstance(entries_obj, dict):
			raw_items = [(str(k), v) for k, v in entries_obj.items()]
		elif isinstance(entries_obj, list):
			raw_items = [(str(i), v) for i, v in enumerate(entries_obj)]
		else:
			raise InvalidLorebookException(message="'entries' must be an object or array")

		entries: list[LorebookEntry] = []
		skipped = 0
		for key, item in raw_items:
			if not isinstance(item, dict):
				skipped += 1
				continue
			entry = self._to_entry(key, item)
			if entry is None:
				skipped += 1
				continue
			entries.append(entry)

		return ParsedImportFile(
			entries=entries,
			skipped=skipped,
			card_name=card_name,
			card_description=card_description,
			file_title=file_title,
		)

	def greeting(self, name: str, content: str) -> str:
		snippet = content[:_GREETING_CONTENT_LIMIT].strip()
		return f"You find yourself in {name}.\n\n{snippet}".rstrip()

	def world_context(self, entries: list[LorebookEntry]) -> str:
		lines: list[str] = []
		total = 0
		for entry in entries:
			if entry.is_character or entry.is_location:
				continue
			line = f"{entry.name}: {entry.content[:_WORLD_CONTEXT_PER_ENTRY]}"
			if total + len(line) > _MAX_WORLD_CONTEXT_CHARS:
				break
			lines.append(line)
			total += len(line)
		if not lines:
			return ""
		return "\n\nWorld context:\n" + "\n".join(lines)

	def card_candidate(self, parsed: ParsedImportFile) -> LorebookEntry | None:
		if not (parsed.card_name and parsed.card_description):
			return None
		image_urls = self._extract_image_urls(f"{parsed.card_name}\n{parsed.card_description}")
		return LorebookEntry(
			key=CARD_KEY,
			uid=None,
			name=parsed.card_name,
			content=parsed.card_description,
			group=_CHARACTER_GROUP,
			image_urls=image_urls,
		)

	def whole_book_scene(self, parsed: ParsedImportFile) -> LorebookEntry | None:
		if not parsed.entries:
			return None
		if any(e.is_character or e.is_location for e in parsed.entries):
			return None
		title = parsed.file_title or parsed.entries[0].name
		image_urls = self._extract_image_urls(f"{title}\n" + "\n".join(e.content for e in parsed.entries))
		return LorebookEntry(
			key=WHOLE_BOOK_KEY,
			uid=None,
			name=title,
			content="\n\n---\n\n".join(f"{e.name}:\n{e.content}" if e.name else e.content for e in parsed.entries),
			group=_LOCATION_GROUP,
			image_urls=image_urls,
		)

	def _extract_entries(self, payload: object) -> dict | list | None:
		if not isinstance(payload, dict):
			return None
		entries = payload.get("entries")
		if isinstance(entries, (dict, list)):
			return entries
		data = payload.get("data")
		if isinstance(data, dict):
			book = data.get("character_book")
			if isinstance(book, dict):
				entries = book.get("entries")
				if isinstance(entries, (dict, list)):
					return entries
		return None

	def _extract_card(self, payload: object) -> tuple[str | None, str | None]:
		if not isinstance(payload, dict):
			return None, None
		data = payload.get("data")
		if isinstance(data, dict):
			source: dict | None = data
		elif self._looks_like_v1_card(payload):
			source = payload
		else:
			return None, None
		name = self._as_text(source.get("name"))
		if not name:
			return None, None
		description = self._as_text(source.get("description"))
		if not description:
			return None, None
		sections: list[tuple[str, str]] = [("Description", description)]
		personality = self._as_text(source.get("personality"))
		if personality:
			sections.append(("Personality", personality))
		scenario = self._as_text(source.get("scenario"))
		if scenario:
			sections.append(("Scenario", scenario))
		body = "\n\n".join(f"{title}:\n{text}" for title, text in sections)
		return name, body

	@classmethod
	def _looks_like_v1_card(cls, payload: dict) -> bool:
		entries = payload.get("entries")
		if isinstance(entries, (dict, list)):
			return False
		return any(
			isinstance(payload.get(field), str) and payload.get(field)
			for field in ("first_mes", "mes_example", "personality", "scenario")
		)

	def _to_entry(self, key: str, raw_entry: dict) -> LorebookEntry | None:
		name = self._as_text(raw_entry.get("comment")) or self._as_text(raw_entry.get("name"))
		content = self._as_text(raw_entry.get("content"))
		if not name or not content:
			return None
		group = self._as_text(raw_entry.get("group"))
		uid = raw_entry.get("uid")
		if not isinstance(uid, (int, str)):
			uid = None
		image_urls = self._extract_image_urls(f"{name}\n{content}")
		return LorebookEntry(
			key=key,
			uid=uid,
			name=name,
			content=content,
			group=group,
			image_urls=image_urls,
		)

	@staticmethod
	def _as_text(value: object) -> str:
		if isinstance(value, str):
			return value.strip()
		return ""

	def _extract_image_urls(self, text: str) -> list[str]:
		found: list[str] = []
		for pattern in (_MD_IMAGE_RE, _BARE_IMAGE_RE):
			for match in pattern.findall(text):
				url = match if isinstance(match, str) else match[0]
				url = url.rstrip(".,;:!\"'")
				if url and url not in found:
					found.append(url)
		return found
