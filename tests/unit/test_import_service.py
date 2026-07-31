import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.application.imports.lorebook import LorebookParser
from src.application.imports.service import ImportService
from src.application.ports.imports import IImageImporter
from src.domain.models import MediaEntityType
from src.infrastructure.exceptions import InvalidLorebookException


def _service() -> ImportService:
	return ImportService(
		character_service=AsyncMock(),
		scene_service=AsyncMock(),
		image_importer=AsyncMock(spec=IImageImporter),
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
		svc.scene_service.bulk_create.return_value = [sid]

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
		assert result.skipped_entries == 0
		svc.character_service.create_character.assert_awaited_once()
		svc.scene_service.bulk_create.assert_awaited_once()
		svc.scene_service.attach_characters.assert_awaited_once_with(sid, [cid])

	@pytest.mark.asyncio
	async def test_world_context_appended_to_scene_background(self):
		svc = _service()
		svc.scene_service.bulk_create.return_value = [uuid4()]

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

		scene = svc.scene_service.bulk_create.await_args.args[0][0]
		assert "Nation." in scene.background_prompt
		assert "World context:" in scene.background_prompt
		assert "bard: Musician." in scene.background_prompt

	@pytest.mark.asyncio
	async def test_fallback_scene_when_no_locations(self):
		svc = _service()
		cid = uuid4()
		svc.character_service.create_character.return_value = cid
		svc.scene_service.bulk_create.return_value = [uuid4()]

		result = await svc.import_lorebook(
			_lorebook({"0": {"comment": "Laeral", "content": "Open Lord.", "group": "Character"}}),
			owner_id=uuid4(),
			is_public=False,
			import_images=False,
		)

		assert result.characters_created == 1
		assert result.scenes_created == 1
		svc.scene_service.bulk_create.assert_awaited_once()
		args = svc.scene_service.attach_characters.await_args.args
		assert args[1] == [cid]

	@pytest.mark.asyncio
	async def test_no_scene_when_no_entries(self):
		svc = _service()
		result = await svc.import_lorebook(_lorebook({}), owner_id=uuid4(), is_public=False, import_images=False)
		assert result.characters_created == 0
		assert result.scenes_created == 0
		svc.scene_service.bulk_create.assert_not_awaited()

	@pytest.mark.asyncio
	async def test_character_create_failure_is_skipped_not_fatal(self):
		svc = _service()
		svc.character_service.create_character.side_effect = RuntimeError("boom")
		svc.scene_service.bulk_create.return_value = [uuid4()]

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
	async def test_import_images_delegated_to_image_importer(self):
		svc = _service()
		svc.character_service.create_character.return_value = uuid4()
		svc.scene_service.bulk_create.return_value = [uuid4()]
		# (imported, failed) per call; the character call also surfaces a failure.
		svc.image_importer.import_images.side_effect = [(1, []), (2, ["https://x.com/missing.jpg"])]

		result = await svc.import_lorebook(
			_lorebook(
				{
					"0": {
						"comment": "Laeral",
						"content": "Portrait ![](https://x.com/a.png)",
						"group": "Character",
					},
					"1": {"comment": "Amn", "content": "Nation. ![](https://x.com/b.png)", "group": "location"},
				}
			),
			owner_id=uuid4(),
			is_public=True,
			import_images=True,
		)

		assert result.images_imported == 3
		assert result.image_failures == ["https://x.com/missing.jpg"]
		entity_types = {call.args[1] for call in svc.image_importer.import_images.await_args_list}
		assert MediaEntityType.CHARACTER in entity_types
		assert MediaEntityType.SCENE in entity_types

	@pytest.mark.asyncio
	async def test_import_images_false_skips_image_importer(self):
		svc = _service()
		svc.character_service.create_character.return_value = uuid4()

		await svc.import_lorebook(
			_lorebook({"0": {"comment": "Laeral", "content": "![](https://x.com/a.png)", "group": "Character"}}),
			owner_id=uuid4(),
			is_public=False,
			import_images=False,
		)

		svc.image_importer.import_images.assert_not_awaited()

	@pytest.mark.asyncio
	async def test_malformed_lorebook_propagates_invalid_exception(self):
		svc = _service()
		with pytest.raises(InvalidLorebookException):
			await svc.import_lorebook(b'{"entries": {"0": {', owner_id=uuid4(), is_public=False, import_images=False)

	@pytest.mark.asyncio
	async def test_preview_classifies_characters_scenes_and_other(self):
		svc = _service()
		preview = svc.preview_lorebook(
			_lorebook(
				{
					"0": {"comment": "Laeral", "content": "Open Lord.", "group": "Character"},
					"1": {"comment": "Amn", "content": "Nation.", "group": "location"},
					"2": {"comment": "bard", "content": "Musician.", "group": "class"},
				}
			)
		)
		assert [c.name for c in preview.characters] == ["Laeral"]
		assert [s.name for s in preview.scenes] == ["Amn"]
		assert preview.other_entries == 1
		assert preview.skipped_entries == 0
		assert preview.characters[0].key == "0"
		assert preview.characters[0].content_length == len("Open Lord.")
		assert "World context:" in preview.world_context_preview
		# Preview is parse-only: it must not touch any service.
		svc.character_service.create_character.assert_not_called()
		svc.scene_service.bulk_create.assert_not_called()

	@pytest.mark.asyncio
	async def test_selected_keys_imports_only_chosen_entries(self):
		svc = _service()
		svc.character_service.create_character.return_value = uuid4()

		result = await svc.import_lorebook(
			_lorebook(
				{
					"0": {"comment": "Laeral", "content": "Open Lord.", "group": "Character"},
					"1": {"comment": "Khelben", "content": "Blackstaff.", "group": "Character"},
					"2": {"comment": "Amn", "content": "Nation.", "group": "location"},
				}
			),
			owner_id=uuid4(),
			is_public=False,
			import_images=False,
			selected_keys=["1"],  # only the second character; scene left out
			link_scenes=False,
		)

		assert result.characters_created == 1
		assert result.scenes_created == 0
		created = svc.character_service.create_character.await_args.args[0]
		assert created.name == "Khelben"
		svc.scene_service.bulk_create.assert_not_awaited()

	@pytest.mark.asyncio
	async def test_link_scenes_false_creates_scenes_without_attaching_or_world_context(self):
		svc = _service()
		svc.character_service.create_character.return_value = uuid4()
		svc.scene_service.bulk_create.return_value = [uuid4()]

		result = await svc.import_lorebook(
			_lorebook(
				{
					"0": {"comment": "Laeral", "content": "Open Lord.", "group": "Character"},
					"1": {"comment": "Amn", "content": "Nation.", "group": "location"},
					"2": {"comment": "bard", "content": "Musician.", "group": "class"},
				}
			),
			owner_id=uuid4(),
			is_public=False,
			import_images=False,
			link_scenes=False,
		)

		assert result.characters_created == 1
		assert result.scenes_created == 1
		svc.scene_service.attach_characters.assert_not_awaited()
		scene = svc.scene_service.bulk_create.await_args.args[0][0]
		assert scene.background_prompt == "Nation."  # raw content, no world context folded in
		assert "World context:" not in scene.background_prompt

	@pytest.mark.asyncio
	async def test_link_scenes_false_does_not_synthesize_fallback_scene(self):
		svc = _service()
		svc.character_service.create_character.return_value = uuid4()

		result = await svc.import_lorebook(
			_lorebook({"0": {"comment": "Laeral", "content": "Open Lord.", "group": "Character"}}),
			owner_id=uuid4(),
			is_public=False,
			import_images=False,
			link_scenes=False,
		)

		assert result.characters_created == 1
		assert result.scenes_created == 0
		svc.scene_service.bulk_create.assert_not_awaited()
		svc.scene_service.attach_characters.assert_not_awaited()
