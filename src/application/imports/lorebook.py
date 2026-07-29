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

_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\((https?://[^\s)]+?)(?:\s+\"[^\"]*\")?\)")
_BARE_IMAGE_RE = re.compile(
	r"https?://[^\s)\"']+\.(?:png|jpe?g|webp|gif|bmp|tiff|ico)(?:[?#][^\s)\"']*)?",
	re.IGNORECASE,
)


@dataclass(frozen=True)
class LorebookEntry:
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


class LorebookParser(ILorebookParser):
	def parse(self, raw: bytes) -> Lorebook:
		try:
			payload = json.loads(raw.decode("utf-8"))
		except (UnicodeDecodeError, json.JSONDecodeError) as exc:
			raise InvalidLorebookException(message=f"Lorebook is not valid JSON: {exc}")

		entries_obj = self._extract_entries(payload)
		if entries_obj is None:
			raise InvalidLorebookException(message="Lorebook JSON has no 'entries' object or array")

		if isinstance(entries_obj, dict):
			raw_items = list(entries_obj.values())
		elif isinstance(entries_obj, list):
			raw_items = entries_obj
		else:
			raise InvalidLorebookException(message="'entries' must be an object or array")

		entries: list[LorebookEntry] = []
		skipped = 0
		for item in raw_items:
			if not isinstance(item, dict):
				skipped += 1
				continue
			entry = self._to_entry(item)
			if entry is None:
				skipped += 1
				continue
			entries.append(entry)

		return Lorebook(entries=entries, skipped=skipped)

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

	def _to_entry(self, raw_entry: dict) -> LorebookEntry | None:
		name = (raw_entry.get("comment") or raw_entry.get("name") or "").strip()
		content = (raw_entry.get("content") or "").strip()
		if not name or not content:
			return None
		group = (raw_entry.get("group") or "").strip()
		image_urls = self._extract_image_urls(f"{name}\n{content}")
		return LorebookEntry(uid=raw_entry.get("uid"), name=name, content=content, group=group, image_urls=image_urls)

	def _extract_image_urls(self, text: str) -> list[str]:
		found: list[str] = []
		for pattern in (_MD_IMAGE_RE, _BARE_IMAGE_RE):
			for match in pattern.findall(text):
				url = match if isinstance(match, str) else match[0]
				url = url.rstrip(".,;:!\"'")
				if url and url not in found:
					found.append(url)
		return found
