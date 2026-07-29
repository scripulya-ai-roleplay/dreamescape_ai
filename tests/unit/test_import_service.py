import asyncio
import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.application.imports.lorebook import LorebookParser
from src.application.imports.service import _MAX_CONCURRENT_IMAGE_FETCHES, ImportService
from src.application.ports.imports import FetchedImage
from src.infrastructure.exceptions import InvalidLorebookException


def _service():
	return ImportService(
		character_service=AsyncMock(),
		scene_service=AsyncMock(),
		media_service=AsyncMock(),
		image_fetcher=AsyncMock(),
		parser=LorebookParser(),
	)


def _lorebook(entries):
	return json.dumps({"entries": entries}).encode()


@pytest.mark.unit
class TestImportService:
	@pytest.mark.asyncio
	async def test_creates_character_and_location_scene_and_attaches(self):
		svc = _service()
		cid, sid = uuid4(), uuid4()
		svc.character_service.create_character.return_value = cid
		svc.scene_service.create_scene.return_value = sid

		result = await svc.import_lorebook(
			_lorebook(
				{
					"0": {"comment": "Laeral", "content": "Open Lord.", "group": "Character"},
					"1": {"comment": "Amn", "content": "Nation.", "group": "location"},
					"2": {"comment": "bard", "content": "Musician.", "group": "class"},
				}
			),
			owner_id=uuid4(),
			is_public=True,
			import_images=False,
		)

		assert result.characters_created == 1
		assert result.scenes_created == 1
		assert result.character_ids == [cid]
		assert result.scene_ids == [sid]
		assert result.images_imported == 0
		assert result.skipped_entries == 0
		svc.character_service.create_character.assert_awaited_once()
		svc.scene_service.create_scene.assert_awaited_once()
		svc.scene_service.attach_characters.assert_awaited_once_with(sid, [cid])

	@pytest.mark.asyncio
	async def test_world_context_appended_to_scene_background(self):
		svc = _service()
		svc.character_service.create_character.return_value = uuid4()
		svc.scene_service.create_scene.return_value = uuid4()

		await svc.import_lorebook(
			_lorebook(
				{
					"0": {"comment": "Amn", "content": "Nation.", "group": "location"},
					"1": {"comment": "bard", "content": "Musician.", "group": "class"},
				}
			),
			owner_id=uuid4(),
			is_public=False,
			import_images=False,
		)

		scene = svc.scene_service.create_scene.await_args.args[0]
		assert "Nation." in scene.background_prompt
		assert "World context:" in scene.background_prompt
		assert "bard: Musician." in scene.background_prompt

	@pytest.mark.asyncio
	async def test_fallback_scene_when_no_locations(self):
		svc = _service()
		cid = uuid4()
		svc.character_service.create_character.return_value = cid
		svc.scene_service.create_scene.return_value = uuid4()

		result = await svc.import_lorebook(
			_lorebook({"0": {"comment": "Laeral", "content": "Open Lord.", "group": "Character"}}),
			owner_id=uuid4(),
			is_public=False,
			import_images=False,
		)

		assert result.characters_created == 1
		assert result.scenes_created == 1
		svc.scene_service.create_scene.assert_awaited_once()
		args = svc.scene_service.attach_characters.await_args.args
		assert args[1] == [cid]

	@pytest.mark.asyncio
	async def test_no_scene_when_no_entries(self):
		svc = _service()
		result = await svc.import_lorebook(_lorebook({}), owner_id=uuid4(), is_public=False, import_images=False)
		assert result.characters_created == 0
		assert result.scenes_created == 0
		svc.scene_service.create_scene.assert_not_awaited()

	@pytest.mark.asyncio
	async def test_character_create_failure_is_skipped_not_fatal(self):
		svc = _service()
		svc.character_service.create_character.side_effect = RuntimeError("boom")
		svc.scene_service.create_scene.return_value = uuid4()

		result = await svc.import_lorebook(
			_lorebook(
				{
					"0": {"comment": "Laeral", "content": "Open Lord.", "group": "Character"},
					"1": {"comment": "Amn", "content": "Nation.", "group": "location"},
				}
			),
			owner_id=uuid4(),
			is_public=False,
			import_images=False,
		)

		assert result.characters_created == 0
		assert result.scenes_created == 1
		assert result.skipped_entries == 1

	@pytest.mark.asyncio
	async def test_image_import_is_best_effort(self):
		svc = _service()
		svc.character_service.create_character.return_value = uuid4()
		svc.scene_service.create_scene.return_value = uuid4()
		svc.image_fetcher.fetch.side_effect = [
			FetchedImage(data=b"\x89PNG\r\n\x1a\n", content_type="image/png"),
			None,
		]

		result = await svc.import_lorebook(
			_lorebook(
				{
					"0": {
						"comment": "Laeral",
						"content": "Portrait ![](https://x.com/a.png) broken ![](https://x.com/missing.jpg)",
						"group": "Character",
					},
					"1": {"comment": "Amn", "content": "Nation.", "group": "location"},
				}
			),
			owner_id=uuid4(),
			is_public=True,
			import_images=True,
		)

		assert result.images_imported == 1
		assert result.image_failures == ["https://x.com/missing.jpg"]
		svc.media_service.upload_bytes.assert_awaited_once()

	@pytest.mark.asyncio
	async def test_image_fetches_run_with_bounded_concurrency(self):
		svc = _service()
		svc.character_service.create_character.return_value = uuid4()
		svc.scene_service.create_scene.return_value = uuid4()
		state = {"in_flight": 0, "max_seen": 0}

		async def tracking_fetch(url):
			state["in_flight"] += 1
			state["max_seen"] = max(state["max_seen"], state["in_flight"])
			await asyncio.sleep(0.01)
			state["in_flight"] -= 1
			return None

		svc.image_fetcher.fetch.side_effect = tracking_fetch
		content = " ".join(f"![](https://x.com/{i}.png)" for i in range(_MAX_CONCURRENT_IMAGE_FETCHES * 3))

		result = await svc.import_lorebook(
			_lorebook({"0": {"comment": "hero", "content": content, "group": "Character"}}),
			owner_id=uuid4(),
			is_public=False,
			import_images=True,
		)

		assert state["max_seen"] <= _MAX_CONCURRENT_IMAGE_FETCHES
		assert state["max_seen"] >= 2
		assert len(result.image_failures) == _MAX_CONCURRENT_IMAGE_FETCHES * 3

	@pytest.mark.asyncio
	async def test_import_images_false_skips_fetch_and_upload(self):
		svc = _service()
		svc.character_service.create_character.return_value = uuid4()
		svc.scene_service.create_scene.return_value = uuid4()

		await svc.import_lorebook(
			_lorebook({"0": {"comment": "Laeral", "content": "![](https://x.com/a.png)", "group": "Character"}}),
			owner_id=uuid4(),
			is_public=False,
			import_images=False,
		)

		svc.image_fetcher.fetch.assert_not_awaited()
		svc.media_service.upload_bytes.assert_not_awaited()

	@pytest.mark.asyncio
	async def test_malformed_lorebook_propagates_invalid_exception(self):
		svc = _service()
		with pytest.raises(InvalidLorebookException):
			await svc.import_lorebook(b'{"entries": {"0": {', owner_id=uuid4(), is_public=False, import_images=False)
