import logging
from dataclasses import dataclass
from uuid import UUID

from src.application.imports.lorebook import (
	CARD_KEY,
	WHOLE_BOOK_KEY,
	LorebookEntry,
	ParsedImportFile,
)
from src.application.imports.schemas import (
	ImportCandidateDTO,
	ImportLorebookResultDTO,
	ImportPreviewDTO,
)
from src.application.ports.characters import ICharacterService
from src.application.ports.imports import IImageImporter, IImportService, ILorebookParser
from src.application.ports.scenes import ISceneService
from src.domain.models import Character, InitialMessage, MediaEntityType, Scene
from src.infrastructure.exceptions import InvalidLorebookException
from src.infrastructure.logging.logger import Logger

_PREVIEW_CONTENT_LIMIT = 300
_CHARACTER_NAME_LIMIT = 254


@dataclass
class ImportService(IImportService):
	"""Orchestrates turning a SillyTavern lorebook into Characters & Scenes.

	This service only orchestrates: it maps lorebook entries to domain objects,
	persists them via the character/scene services, and delegates image fetching
	to [IImageImporter]. The import-vs-link policy (world context, fallback
	scene, character attachment) lives here because it's import policy, not
	domain logic of scenes or characters.
	"""

	character_service: ICharacterService
	scene_service: ISceneService
	image_importer: IImageImporter
	parser: ILorebookParser
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)

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
	) -> ImportLorebookResultDTO:
		parsed = self.parser.parse_file(raw)
		entries = self._selected_entries(parsed, selected_keys)

		if attach_to_character_id is not None:
			return await self._append_to_character(parsed, entries, attach_to_character_id, owner_id)

		image_failures: list[str] = []

		character_ids, char_images, char_skipped = await self._create_characters(
			[e for e in entries if e.is_character],
			owner_id=owner_id,
			is_public=is_public,
			import_images=import_images,
			image_failures=image_failures,
		)
		scene_ids, scene_images, scene_skipped = await self._create_scenes(
			location_entries=[e for e in entries if e.is_location],
			all_entries=entries,
			character_ids=character_ids,
			owner_id=owner_id,
			is_public=is_public,
			import_images=import_images,
			link_scenes=link_scenes,
			image_failures=image_failures,
		)

		return ImportLorebookResultDTO(
			characters_created=len(character_ids),
			scenes_created=len(scene_ids),
			images_imported=char_images + scene_images,
			image_failures=image_failures,
			character_ids=character_ids,
			scene_ids=scene_ids,
			skipped_entries=parsed.skipped + char_skipped + scene_skipped,
		)

	async def _append_to_character(
		self,
		parsed: ParsedImportFile,
		entries: list[LorebookEntry],
		character_id: UUID,
		owner_id: UUID,
	) -> ImportLorebookResultDTO:
		"""Append the selected lorebook content to an existing character's prompt.

		No new characters or scenes are created — the caller explicitly chose a
		target character for this content (e.g. a character-lore lorebook that
		belongs to a card-imported character). The append is a single-column
		atomic SQL concatenation (see [ICharacterService.append_to_system_prompt]),
		so a concurrent edit or a racing attach is never clobbered.
		"""
		addition = self._entries_prompt(parsed, entries)
		if not addition:
			raise InvalidLorebookException(message="Nothing to import: no usable entries in this lorebook")

		# append_to_system_prompt checks ownership and 404s on a missing id.
		await self.character_service.append_to_system_prompt(character_id, addition, owner_id)

		return ImportLorebookResultDTO(
			characters_created=0,
			scenes_created=0,
			images_imported=0,
			image_failures=[],
			character_ids=[character_id],
			scene_ids=[],
			skipped_entries=parsed.skipped,
			appended_to_character_id=character_id,
		)

	def _entries_prompt(self, parsed: ParsedImportFile, entries: list[LorebookEntry]) -> str:
		"""The selected lorebook content as a single prompt-sized text block.

		Whatever the user kept is attached — no group-based filtering (the
		whole-book candidate synthesizes to group "location", and character-lore
		entries use per-character groups). Contents are kept whole: these
		lorebooks are standing directives, not trivia; the world-context
		truncation would break them.
		"""
		blocks: list[str] = []
		for entry in entries:
			if entry.key == CARD_KEY:
				# The card candidate is the character body itself; it has its own
				# import path and doesn't belong on another character's prompt.
				continue
			if entry.name:
				blocks.append(f"{entry.name}:\n{entry.content}")
			else:
				blocks.append(entry.content)
		return "\n\n---\n\n".join(blocks)

	async def _create_characters(
		self,
		entries: list[LorebookEntry],
		*,
		owner_id: UUID,
		is_public: bool,
		import_images: bool,
		image_failures: list[str],
	) -> tuple[list[UUID], int, int]:
		ids: list[UUID] = []
		images = 0
		skipped = 0
		for entry in entries:
			try:
				character_id = await self.character_service.create_character(
					Character(
						name=entry.name[:_CHARACTER_NAME_LIMIT],
						system_prompt=entry.content,
						owner_id=owner_id,
						is_public=is_public,
					)
				)
			except Exception as exc:
				self.logger.error("Skipped character %r during import: %s", entry.name, exc)
				skipped += 1
				continue
			ids.append(character_id)
			images += await self._import_images(
				entry.image_urls,
				MediaEntityType.CHARACTER,
				character_id,
				owner_id,
				is_public,
				import_images,
				image_failures,
			)
		return ids, images, skipped

	async def _create_scenes(
		self,
		*,
		location_entries: list[LorebookEntry],
		all_entries: list[LorebookEntry],
		character_ids: list[UUID],
		owner_id: UUID,
		is_public: bool,
		import_images: bool,
		link_scenes: bool,
		image_failures: list[str],
	) -> tuple[list[UUID], int, int]:
		if link_scenes:
			return await self._create_linked_scenes(
				location_entries=location_entries,
				all_entries=all_entries,
				character_ids=character_ids,
				owner_id=owner_id,
				is_public=is_public,
				import_images=import_images,
				image_failures=image_failures,
			)
		return await self._create_standalone_scenes(
			location_entries=location_entries,
			owner_id=owner_id,
			is_public=is_public,
			import_images=import_images,
			image_failures=image_failures,
		)

	async def _create_linked_scenes(
		self,
		*,
		location_entries: list[LorebookEntry],
		all_entries: list[LorebookEntry],
		character_ids: list[UUID],
		owner_id: UUID,
		is_public: bool,
		import_images: bool,
		image_failures: list[str],
	) -> tuple[list[UUID], int, int]:
		world_context = self.parser.world_context(all_entries)

		if location_entries:
			scenes = [
				self._scene(entry, background=entry.content + world_context, owner_id=owner_id, is_public=is_public)
				for entry in location_entries
			]
			scene_ids, skipped = await self._bulk_create(scenes)
			images = 0
			for entry, scene_id in zip(location_entries, scene_ids):
				await self._attach_characters(scene_id, character_ids)
				images += await self._import_images(
					entry.image_urls,
					MediaEntityType.SCENE,
					scene_id,
					owner_id,
					is_public,
					import_images,
					image_failures,
				)
			return scene_ids, images, skipped

		if all_entries:
			# The generic fallback scene is for real lorebook content only: when
			# the selection is synthetic-only (e.g. import-all on a bare card,
			# whose only entry is the card character), a "Imported lorebook"
			# scene with an empty background would be junk.
			has_real_entries = any(e.key not in (CARD_KEY, WHOLE_BOOK_KEY) for e in all_entries)
			if not has_real_entries:
				return [], 0, 0
			background = world_context or f"Imported lorebook containing {len(all_entries)} entries."
			fallback = Scene(
				title="Imported lorebook",
				description=None,
				background_prompt=background,
				owner_id=owner_id,
				is_public=is_public,
				initial_messages=[InitialMessage(text="The story begins.")],
			)
			scene_ids, skipped = await self._bulk_create([fallback])
			if scene_ids:
				await self._attach_characters(scene_ids[0], character_ids)
			return scene_ids, 0, skipped

		return [], 0, 0

	async def _create_standalone_scenes(
		self,
		*,
		location_entries: list[LorebookEntry],
		owner_id: UUID,
		is_public: bool,
		import_images: bool,
		image_failures: list[str],
	) -> tuple[list[UUID], int, int]:
		if not location_entries:
			return [], 0, 0
		scenes = [
			self._scene(entry, background=entry.content, owner_id=owner_id, is_public=is_public)
			for entry in location_entries
		]
		scene_ids, skipped = await self._bulk_create(scenes)
		images = 0
		for entry, scene_id in zip(location_entries, scene_ids):
			images += await self._import_images(
				entry.image_urls,
				MediaEntityType.SCENE,
				scene_id,
				owner_id,
				is_public,
				import_images,
				image_failures,
			)
		return scene_ids, images, skipped

	def preview_lorebook(self, raw: bytes) -> ImportPreviewDTO:
		parsed = self.parser.parse_file(raw)
		characters: list[ImportCandidateDTO] = []
		scenes: list[ImportCandidateDTO] = []
		other = 0
		for entry in parsed.entries:
			if entry.is_character:
				characters.append(self._candidate(entry))
			elif entry.is_location:
				scenes.append(self._candidate(entry))
			else:
				other += 1
		# A bare character card (no embedded lorebook) imports as its card
		# character; a pure world-book (no character/location groups) imports as
		# one whole-book scene. Both are opt-in candidates the user can deselect.
		card = self.parser.card_candidate(parsed)
		if card is not None:
			characters.append(self._candidate(card))
		whole_book = self.parser.whole_book_scene(parsed)
		if whole_book is not None:
			scenes.append(self._candidate(whole_book))
		return ImportPreviewDTO(
			characters=characters,
			scenes=scenes,
			other_entries=other,
			skipped_entries=parsed.skipped,
			world_context_preview=self.parser.world_context(parsed.entries),
		)

	def _selected_entries(self, parsed: ParsedImportFile, selected_keys: list[str] | None) -> list[LorebookEntry]:
		"""The entries the user kept, with synthetic candidates expanded.

		The card and whole-book candidates don't exist in [ParsedImportFile.entries];
		selecting them materializes the synthesized entry so downstream creation
		paths treat it like any other. The no-selection ("import all") path
		must materialize them too: the preview contract offers them, so
		import-all delivers exactly what preview promised — a bare card imports
		its card character, a pure world book imports its whole-book scene.
		"""
		entries = list(parsed.entries)
		card = self.parser.card_candidate(parsed)
		whole_book = self.parser.whole_book_scene(parsed)

		if selected_keys:
			wanted = set(selected_keys)
			kept: list[LorebookEntry] = [e for e in entries if e.key in wanted]
			if CARD_KEY in wanted and card is not None:
				kept.append(card)
			if WHOLE_BOOK_KEY in wanted and whole_book is not None:
				kept.append(whole_book)
			return kept

		# Import all: every real entry plus the synthetic candidates the
		# preview offered (card + whole-book are None unless applicable).
		return entries + [e for e in (card, whole_book) if e is not None]

	def _scene(self, entry: LorebookEntry, *, background: str, owner_id: UUID, is_public: bool) -> Scene:
		return Scene(
			title=entry.name,
			description=None,
			background_prompt=background,
			owner_id=owner_id,
			is_public=is_public,
			initial_messages=[InitialMessage(text=self.parser.greeting(entry.name, entry.content))],
		)

	async def _bulk_create(self, scenes: list[Scene]) -> tuple[list[UUID], int]:
		try:
			return await self.scene_service.bulk_create(scenes), 0
		except Exception as exc:
			self.logger.error("Skipped %d scene(s) during import: %s", len(scenes), exc)
			return [], len(scenes)

	async def _attach_characters(self, scene_id: UUID, character_ids: list[UUID]) -> None:
		if not character_ids:
			return
		try:
			await self.scene_service.attach_characters(scene_id, character_ids)
		except Exception as exc:
			self.logger.error("Failed to attach characters to scene %s: %s", scene_id, exc)

	async def _import_images(
		self,
		urls: list[str],
		entity_type: MediaEntityType,
		entity_id: UUID,
		owner_id: UUID,
		is_public: bool,
		import_images: bool,
		image_failures: list[str],
	) -> int:
		if not import_images or not urls:
			return 0
		imported, failed = await self.image_importer.import_images(urls, entity_type, entity_id, owner_id, is_public)
		image_failures.extend(failed)
		return imported

	@staticmethod
	def _candidate(entry: LorebookEntry) -> ImportCandidateDTO:
		return ImportCandidateDTO(
			key=entry.key,
			uid=entry.uid,
			name=entry.name,
			group=entry.group,
			content_preview=entry.content[:_PREVIEW_CONTENT_LIMIT],
			content_length=len(entry.content),
			image_count=len(entry.image_urls),
		)
