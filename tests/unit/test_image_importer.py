import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.application.imports.image_importer import (
	_MAX_CONCURRENT_IMAGE_FETCHES,
	ImageImporter,
)
from src.application.ports.imports import FetchedImage
from src.domain.models import MediaEntityType


def _importer() -> ImageImporter:
	return ImageImporter(media_service=AsyncMock(), image_fetcher=AsyncMock())


@pytest.mark.unit
class TestImageImporter:
	@pytest.mark.asyncio
	async def test_empty_urls_is_a_noop(self):
		importer = _importer()

		imported, failures = await importer.import_images(
			[], MediaEntityType.CHARACTER, uuid4(), uuid4(), is_public=True
		)

		assert (imported, failures) == (0, [])
		importer.image_fetcher.fetch.assert_not_awaited()
		importer.media_service.upload_bytes.assert_not_awaited()

	@pytest.mark.asyncio
	async def test_best_effort_records_success_and_failures(self):
		importer = _importer()

		async def fetch(url):
			if url.endswith("missing.jpg"):
				return None
			return FetchedImage(data=b"\x89PNG\r\n\x1a\n", content_type="image/png")

		importer.image_fetcher.fetch.side_effect = fetch

		imported, failures = await importer.import_images(
			["https://x.com/a.png", "https://x.com/missing.jpg"],
			MediaEntityType.CHARACTER,
			uuid4(),
			uuid4(),
			is_public=True,
		)

		assert imported == 1
		assert failures == ["https://x.com/missing.jpg"]
		importer.media_service.upload_bytes.assert_awaited_once()

	@pytest.mark.asyncio
	async def test_upload_error_is_recorded_not_raised(self):
		importer = _importer()
		importer.image_fetcher.fetch.return_value = FetchedImage(data=b"bytes", content_type="image/png")
		importer.media_service.upload_bytes.side_effect = RuntimeError("boom")

		imported, failures = await importer.import_images(
			["https://x.com/a.png"], MediaEntityType.SCENE, uuid4(), uuid4(), is_public=False
		)

		assert imported == 0
		assert failures == ["https://x.com/a.png"]

	@pytest.mark.asyncio
	async def test_fetches_run_with_bounded_concurrency(self):
		importer = _importer()
		state = {"in_flight": 0, "max_seen": 0}

		async def tracking_fetch(url):
			state["in_flight"] += 1
			state["max_seen"] = max(state["max_seen"], state["in_flight"])
			await asyncio.sleep(0.01)
			state["in_flight"] -= 1
			return None

		importer.image_fetcher.fetch.side_effect = tracking_fetch
		urls = [f"https://x.com/{i}.png" for i in range(_MAX_CONCURRENT_IMAGE_FETCHES * 3)]

		imported, failures = await importer.import_images(
			urls, MediaEntityType.CHARACTER, uuid4(), uuid4(), is_public=False
		)

		assert state["max_seen"] <= _MAX_CONCURRENT_IMAGE_FETCHES
		assert state["max_seen"] >= 2
		assert imported == 0
		assert len(failures) == len(urls)
