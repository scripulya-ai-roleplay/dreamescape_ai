from __future__ import annotations

import abc
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.application.imports.schemas import (
	ImportLorebookResultDTO,
	ImportPreviewDTO,
)
from src.domain.models import MediaEntityType

if TYPE_CHECKING:
	from src.application.imports.lorebook import Lorebook, LorebookEntry, ParsedImportFile


class FetchedImage(BaseModel):
	model_config = ConfigDict(frozen=True)

	data: bytes
	content_type: str | None = None


class IImageFetcher(abc.ABC):
	@abc.abstractmethod
	async def fetch(self, url: str) -> FetchedImage | None: ...


class IImageImporter(abc.ABC):
	@abc.abstractmethod
	async def import_images(
		self,
		urls: list[str],
		entity_type: MediaEntityType,
		entity_id: UUID,
		owner_id: UUID,
		is_public: bool,
	) -> tuple[int, list[str]]: ...


class IImportService(abc.ABC):
	@abc.abstractmethod
	async def import_lorebook(
		self,
		raw: bytes,
		owner_id: UUID,
		*,
		is_public: bool,
		import_images: bool,
		selected_keys: list[str] | None = None,
		link_scenes: bool = True,
		attach_to_character_id: UUID | None = None,
	) -> ImportLorebookResultDTO: ...

	@abc.abstractmethod
	def preview_lorebook(self, raw: bytes) -> ImportPreviewDTO: ...


class ILorebookParser(abc.ABC):
	@abc.abstractmethod
	def parse(self, raw: bytes) -> Lorebook: ...

	@abc.abstractmethod
	def parse_file(self, raw: bytes) -> ParsedImportFile: ...

	@abc.abstractmethod
	def card_candidate(self, parsed: ParsedImportFile) -> LorebookEntry | None: ...

	@abc.abstractmethod
	def whole_book_scene(self, parsed: ParsedImportFile) -> LorebookEntry | None: ...

	@abc.abstractmethod
	def greeting(self, name: str, content: str) -> str: ...

	@abc.abstractmethod
	def world_context(self, entries: list[LorebookEntry]) -> str: ...
