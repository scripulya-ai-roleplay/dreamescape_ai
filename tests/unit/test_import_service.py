import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.application.imports.lorebook import CARD_KEY, WHOLE_BOOK_KEY, LorebookParser
from src.application.imports.service import ImportService
from src.application.ports.imports import IImageImporter
from src.domain.models import Character, MediaEntityType
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


@pytest.mark.unit
class TestCardImport:
	def _card(self) -> bytes:
		return json.dumps(
			{
				"spec": "chara_card_v3",
				"spec_version": "3.0",
				"data": {
					"name": "Azua",
					"description": "Dragon rider.",
					"personality": "Gruff.",
					"scenario": "Aerie at dawn.",
					"first_mes": "Hi.",
					"character_book": {"entries": []},
				},
			}
		).encode()

	@pytest.mark.asyncio
	async def test_card_preview_offers_card_character(self):
		svc = _service()
		preview = svc.preview_lorebook(self._card())
		assert [c.name for c in preview.characters] == ["Azua"]
		assert preview.characters[0].key == CARD_KEY
		assert preview.scenes == []
		assert "Dragon rider." in preview.characters[0].content_preview

	@pytest.mark.asyncio
	async def test_card_import_creates_character_from_card_body(self):
		svc = _service()
		cid = uuid4()
		svc.character_service.create_character.return_value = cid
		svc.scene_service.bulk_create.return_value = [uuid4()]

		result = await svc.import_lorebook(
			self._card(),
			owner_id=uuid4(),
			is_public=False,
			import_images=False,
			selected_keys=[CARD_KEY],
			link_scenes=False,
		)

		assert result.characters_created == 1
		assert result.character_ids == [cid]
		created = svc.character_service.create_character.await_args.args[0]
		assert created.name == "Azua"
		assert "Dragon rider." in created.system_prompt
		assert "Personality:" in created.system_prompt
		assert "Scenario:" in created.system_prompt

	@pytest.mark.asyncio
	async def test_world_info_file_name_is_not_mistaken_for_a_card(self):
		# A World Info file carries book metadata (name/description) at the top
		# level — that must not surface as a character candidate.
		svc = _service()
		raw = json.dumps(
			{
				"name": "My World",
				"description": "book metadata",
				"entries": {"0": {"comment": "Amn", "content": "Nation.", "group": "location"}},
			}
		).encode()
		preview = svc.preview_lorebook(raw)
		assert preview.characters == []
		assert [s.name for s in preview.scenes] == ["Amn"]


@pytest.mark.unit
class TestWholeBookScene:
	def _world_book(self) -> bytes:
		return json.dumps(
			{
				"name": "Sandbox_Lorebook",
				"description": "Standing directives.",
				"entries": {
					"0": {"comment": "SANDBOX_STATE", "content": "Directive one.", "group": "Sandbox"},
					"1": {"comment": "WORLD_PULSE", "content": "Directive two.", "group": "Sandbox"},
				},
			}
		).encode()

	@pytest.mark.asyncio
	async def test_world_book_preview_offers_whole_book_scene(self):
		svc = _service()
		preview = svc.preview_lorebook(self._world_book())
		assert preview.characters == []
		assert len(preview.scenes) == 1
		book = preview.scenes[0]
		assert book.key == WHOLE_BOOK_KEY
		assert book.name == "Sandbox_Lorebook"
		assert book.content_length > len("Directive one.")

	@pytest.mark.asyncio
	async def test_world_book_import_creates_one_scene_with_full_content(self):
		svc = _service()
		svc.scene_service.bulk_create.return_value = [uuid4()]

		result = await svc.import_lorebook(
			self._world_book(),
			owner_id=uuid4(),
			is_public=False,
			import_images=False,
			selected_keys=[WHOLE_BOOK_KEY],
			link_scenes=False,
		)

		assert result.scenes_created == 1
		scene = svc.scene_service.bulk_create.await_args.args[0][0]
		assert scene.title == "Sandbox_Lorebook"
		assert "Directive one." in scene.background_prompt
		assert "Directive two." in scene.background_prompt
		assert "SANDBOX_STATE" in scene.background_prompt
		svc.character_service.create_character.assert_not_called()

	@pytest.mark.asyncio
	async def test_whole_book_not_offered_when_selectable_entries_exist(self):
		svc = _service()
		raw = _lorebook(
			{
				"0": {"comment": "Amn", "content": "Nation.", "group": "location"},
				"1": {"comment": "bard", "content": "Musician.", "group": "class"},
			}
		)
		preview = svc.preview_lorebook(raw)
		assert [s.key for s in preview.scenes] == ["0"]
		assert all(s.key != WHOLE_BOOK_KEY for s in preview.scenes)


@pytest.mark.unit
class TestAttachToCharacter:
	async def _prepared(self, existing_prompt: str = "You are Azua."):
		svc = _service()
		character_id, owner_id = uuid4(), uuid4()
		svc.character_service.get_one.return_value = Character(
			id=character_id,
			owner_id=owner_id,
			name="Azua",
			system_prompt=existing_prompt,
		)
		return svc, character_id, owner_id

	@pytest.mark.asyncio
	async def test_appends_selected_entries_to_existing_character(self):
		svc, character_id, owner_id = await self._prepared()
		raw = _lorebook(
			{
				"0": {"comment": "Azua lore", "content": "Wing commander.", "group": "azua"},
				"1": {"comment": "skipped", "content": "Not selected.", "group": "azua"},
			}
		)

		result = await svc.import_lorebook(
			raw,
			owner_id,
			is_public=False,
			import_images=False,
			selected_keys=["0"],
			attach_to_character_id=character_id,
		)

		assert result.appended_to_character_id == character_id
		assert result.characters_created == 0
		assert result.scenes_created == 0
		svc.character_service.create_character.assert_not_called()
		svc.scene_service.bulk_create.assert_not_awaited()

		target_id, updated, actor = svc.character_service.update.await_args.args
		assert target_id == character_id
		assert actor == owner_id
		assert updated.system_prompt.startswith("You are Azua.")
		assert "Azua lore:\nWing commander." in updated.system_prompt
		assert "Not selected." not in updated.system_prompt

	@pytest.mark.asyncio
	async def test_appends_everything_when_no_keys_selected(self):
		svc, character_id, owner_id = await self._prepared()
		raw = _lorebook({"0": {"comment": "a", "content": "one", "group": "x"}})

		await svc.import_lorebook(
			raw, owner_id, is_public=False, import_images=False, attach_to_character_id=character_id
		)

		_, updated, _ = svc.character_service.update.await_args.args
		assert "one" in updated.system_prompt

	@pytest.mark.asyncio
	async def test_attach_whole_world_book_to_character(self):
		# The primary use case: a pure world-book (whole-book scene candidate)
		# appended to a card-imported character.
		svc, character_id, owner_id = await self._prepared()
		raw = json.dumps(
			{
				"name": "Sandbox_Lorebook",
				"entries": {
					"0": {"comment": "SANDBOX_STATE", "content": "Directive one.", "group": "Sandbox"},
					"1": {"comment": "WORLD_PULSE", "content": "Directive two.", "group": "Sandbox"},
				},
			}
		).encode()

		result = await svc.import_lorebook(
			raw,
			owner_id,
			is_public=False,
			import_images=False,
			selected_keys=[WHOLE_BOOK_KEY],
			attach_to_character_id=character_id,
		)

		assert result.appended_to_character_id == character_id
		_, updated, _ = svc.character_service.update.await_args.args
		assert "Directive one." in updated.system_prompt
		assert "Directive two." in updated.system_prompt
		assert "SANDBOX_STATE" in updated.system_prompt

	@pytest.mark.asyncio
	async def test_attach_card_candidate_is_ignored(self):
		# The card candidate is a character body; attaching a card to a
		# different character must not splice one character into another.
		svc, character_id, owner_id = await self._prepared()
		raw = json.dumps(
			{
				"spec": "chara_card_v3",
				"data": {"name": "Azua", "description": "Dragon rider.", "character_book": {"entries": []}},
			}
		).encode()

		with pytest.raises(InvalidLorebookException):
			await svc.import_lorebook(
				raw,
				owner_id,
				is_public=False,
				import_images=False,
				selected_keys=[CARD_KEY],
				attach_to_character_id=character_id,
			)

	@pytest.mark.asyncio
	async def test_attach_without_usable_content_raises(self):
		svc, character_id, owner_id = await self._prepared()
		with pytest.raises(InvalidLorebookException):
			await svc.import_lorebook(
				_lorebook({}),
				owner_id,
				is_public=False,
				import_images=False,
				attach_to_character_id=character_id,
			)
