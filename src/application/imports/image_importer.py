import asyncio
import logging
from dataclasses import dataclass
from uuid import UUID

from src.application.media.schemas import MediaUploadBytesDTO
from src.application.ports.imports import IImageFetcher, IImageImporter
from src.application.ports.media import IMediaService
from src.domain.models import MediaEntityType
from src.infrastructure.logging.logger import Logger

_MAX_CONCURRENT_IMAGE_FETCHES = 4


@dataclass
class ImageImporter(IImageImporter):
	media_service: IMediaService
	image_fetcher: IImageFetcher
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)

	async def import_images(
		self,
		urls: list[str],
		entity_type: MediaEntityType,
		entity_id: UUID,
		owner_id: UUID,
		is_public: bool,
	) -> tuple[int, list[str]]:
		if not urls:
			return 0, []

		semaphore = asyncio.Semaphore(_MAX_CONCURRENT_IMAGE_FETCHES)
		failures: list[str] = []

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

		imported = sum(await asyncio.gather(*(_fetch_one(url) for url in urls)))
		return imported, failures
