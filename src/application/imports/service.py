import asyncio
import logging
from dataclasses import dataclass
from uuid import UUID

from src.application.imports.schemas import ImportLorebookResultDTO
from src.application.media.schemas import MediaUploadBytesDTO
from src.application.ports.characters import ICharacterService
from src.application.ports.imports import IImageFetcher, IImportService, ILorebookParser
from src.application.ports.media import IMediaService
from src.application.ports.scenes import ISceneService
from src.domain.models import Character, InitialMessage, MediaEntityType, Scene
from src.infrastructure.logging.logger import Logger

_MAX_CONCURRENT_IMAGE_FETCHES = 4


@dataclass
class ImportService(IImportService):
	character_service: ICharacterService
	scene_service: ISceneService
	media_service: IMediaService
	image_fetcher: IImageFetcher
	parser: ILorebookParser
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)

	async def import_lorebook(
		self, raw: bytes, owner_id: UUID, *, is_public: bool, import_images: bool
	) -> ImportLorebookResultDTO:
		lorebook = self.parser.parse(raw)
		world_context = self.parser.world_context(lorebook.entries)

		character_ids: list[UUID] = []
		scene_ids: list[UUID] = []
		images_imported = 0
		image_failures: list[str] = []
		skipped = lorebook.skipped
		image_semaphore = asyncio.Semaphore(_MAX_CONCURRENT_IMAGE_FETCHES)

		for entry in lorebook.entries:
			if not entry.is_character:
				continue
			try:
				character_id = await self.character_service.create_character(
					Character(
						name=entry.name[:254],
						system_prompt=entry.content,
						owner_id=owner_id,
						is_public=is_public,
					)
				)
			except Exception as exc:
				self.logger.error("Skipped character %r during import: %s", entry.name, exc)
				skipped += 1
				continue
			character_ids.append(character_id)
			if import_images:
				images_imported += await self._import_entry_images(
					entry.image_urls,
					MediaEntityType.CHARACTER,
					character_id,
					owner_id,
					is_public,
					image_failures,
					image_semaphore,
				)

		location_entries = [e for e in lorebook.entries if e.is_location]
		if location_entries:
			for entry in location_entries:
				scene = Scene(
					title=entry.name,
					description=None,
					background_prompt=entry.content + world_context,
					owner_id=owner_id,
					is_public=is_public,
					initial_messages=[InitialMessage(text=self.parser.greeting(entry.name, entry.content))],
				)
				try:
					scene_id = await self.scene_service.create_scene(scene)
				except Exception as exc:
					self.logger.error("Skipped scene %r during import: %s", entry.name, exc)
					skipped += 1
					continue
				scene_ids.append(scene_id)
				if character_ids:
					try:
						await self.scene_service.attach_characters(scene_id, character_ids)
					except Exception as exc:
						self.logger.error("Failed to attach characters to scene %s: %s", scene_id, exc)
				if import_images:
					images_imported += await self._import_entry_images(
						entry.image_urls,
						MediaEntityType.SCENE,
						scene_id,
						owner_id,
						is_public,
						image_failures,
						image_semaphore,
					)
		elif lorebook.entries:
			background = world_context or f"Imported lorebook containing {len(lorebook.entries)} entries."
			fallback = Scene(
				title="Imported lorebook",
				description=None,
				background_prompt=background,
				owner_id=owner_id,
				is_public=is_public,
				initial_messages=[InitialMessage(text="The story begins.")],
			)
			try:
				scene_id = await self.scene_service.create_scene(fallback)
				scene_ids.append(scene_id)
				if character_ids:
					try:
						await self.scene_service.attach_characters(scene_id, character_ids)
					except Exception as exc:
						self.logger.error("Failed to attach characters to fallback scene %s: %s", scene_id, exc)
			except Exception as exc:
				self.logger.error("Skipped fallback scene during import: %s", exc)
				skipped += 1

		return ImportLorebookResultDTO(
			characters_created=len(character_ids),
			scenes_created=len(scene_ids),
			images_imported=images_imported,
			image_failures=image_failures,
			character_ids=character_ids,
			scene_ids=scene_ids,
			skipped_entries=skipped,
		)

	async def _import_entry_images(
		self,
		urls: list[str],
		entity_type: MediaEntityType,
		entity_id: UUID,
		owner_id: UUID,
		is_public: bool,
		failures: list[str],
		semaphore: asyncio.Semaphore,
	) -> int:
		if not urls:
			return 0

		async def _fetch_one(url: str) -> int:
			async with semaphore:
				fetched = await self.image_fetcher.fetch(url)
				if fetched is None or not fetched.data:
					failures.append(url)
					return 0
				try:
					await self.media_service.upload_bytes(
						MediaUploadBytesDTO(
							data=fetched.data,
							content_type=fetched.content_type,
							entity_type=entity_type,
							entity_id=entity_id,
							owner_id=owner_id,
							is_public=is_public,
						)
					)
					return 1
				except Exception as exc:
					self.logger.warning("Image import failed for %s: %s", url, exc)
					failures.append(url)
					return 0

		results = await asyncio.gather(*(_fetch_one(url) for url in urls))
		return sum(results)
