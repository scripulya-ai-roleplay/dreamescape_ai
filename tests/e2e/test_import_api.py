import json

import pytest


@pytest.mark.e2e
class TestImportAPI:
	def test_import_lorebook_creates_characters_and_scenes(self, client, auth_headers):
		payload = {
			"entries": {
				"0": {"comment": "Laeral Silverhand", "content": "Open Lord of Waterdeep.", "group": "Character"},
				"1": {"comment": "Amn", "content": "Wealthy mercantile nation.", "group": "location"},
				"2": {"comment": "bard", "content": "Musical magicians.", "group": "class"},
			}
		}
		files = {"file": ("lorebook.json", json.dumps(payload), "application/json")}
		data = {"is_public": "false", "import_images": "false"}

		response = client.post("/api/v1/import/lorebook", files=files, data=data, headers=auth_headers)
		assert response.status_code == 200, response.text

		result = response.json()["result"]
		assert result["characters_created"] == 1
		assert result["scenes_created"] == 1
		assert result["skipped_entries"] == 0
		assert len(result["character_ids"]) == 1
		assert len(result["scene_ids"]) == 1

		for cid in result["character_ids"]:
			client.delete(f"/api/v1/characters/{cid}", headers=auth_headers)
		for sid in result["scene_ids"]:
			client.delete(f"/api/v1/scenes/{sid}", headers=auth_headers)

	def test_import_truncated_lorebook_returns_422(self, client, auth_headers):
		files = {"file": ("broken.json", b'{"entries": {"0": {', "application/json")}
		data = {"import_images": "false"}

		response = client.post("/api/v1/import/lorebook", files=files, data=data, headers=auth_headers)
		assert response.status_code == 422
		assert response.json()["error"]["code"] == "INVALID_LOREBOOK"

	def test_preview_then_selective_import_without_linking(self, client, auth_headers):
		payload = {
			"entries": {
				"0": {"comment": "Laeral", "content": "Open Lord of Waterdeep.", "group": "Character"},
				"1": {"comment": "Khelben", "content": "Blackstaff of Waterdeep.", "group": "Character"},
				"2": {"comment": "Amn", "content": "Wealthy mercantile nation.", "group": "location"},
			}
		}
		files = {"file": ("lorebook.json", json.dumps(payload), "application/json")}

		preview_resp = client.post("/api/v1/import/lorebook/preview", files=files, headers=auth_headers)
		assert preview_resp.status_code == 200, preview_resp.text
		preview = preview_resp.json()["result"]
		assert len(preview["characters"]) == 2
		assert len(preview["scenes"]) == 1
		char_keys = {c["name"]: c["key"] for c in preview["characters"]}
		scene_key = preview["scenes"][0]["key"]

		# Import only Laeral + the scene, unlinked.
		data = {
			"is_public": "false",
			"import_images": "false",
			"link_scenes": "false",
			"selected_keys": [char_keys["Laeral"], scene_key],
		}
		import_resp = client.post("/api/v1/import/lorebook", files=files, data=data, headers=auth_headers)
		assert import_resp.status_code == 200, import_resp.text
		result = import_resp.json()["result"]
		# The file has 2 characters + 1 scene; only Laeral + the scene were
		# selected, so exactly one of each is created.
		assert result["characters_created"] == 1
		assert result["scenes_created"] == 1

		for cid in result["character_ids"]:
			client.delete(f"/api/v1/characters/{cid}", headers=auth_headers)
		for sid in result["scene_ids"]:
			client.delete(f"/api/v1/scenes/{sid}", headers=auth_headers)

	def test_import_requires_authentication(self, client):
		files = {"file": ("lorebook.json", b'{"entries": {}}', "application/json")}

		response = client.post("/api/v1/import/lorebook", files=files)
		assert response.status_code == 401

	def test_card_import_creates_character_from_card_body(self, client, auth_headers):
		payload = {
			"spec": "chara_card_v3",
			"spec_version": "3.0",
			"data": {
				"name": "E2E Card Character",
				"description": "A test description.",
				"personality": "Stoic.",
				"scenario": "Testing hall.",
				"character_book": {"entries": []},
			},
		}
		files = {"file": ("card.json", json.dumps(payload), "application/json")}

		preview_resp = client.post("/api/v1/import/lorebook/preview", files=files, headers=auth_headers)
		assert preview_resp.status_code == 200, preview_resp.text
		preview = preview_resp.json()["result"]
		assert [c["name"] for c in preview["characters"]] == ["E2E Card Character"]
		card_key = preview["characters"][0]["key"]

		data = {
			"is_public": "false",
			"import_images": "false",
			"link_scenes": "false",
			"selected_keys": [card_key],
		}
		import_resp = client.post("/api/v1/import/lorebook", files=files, data=data, headers=auth_headers)
		assert import_resp.status_code == 200, import_resp.text
		result = import_resp.json()["result"]
		assert result["characters_created"] == 1
		assert result["scenes_created"] == 0

		for cid in result["character_ids"]:
			client.delete(f"/api/v1/characters/{cid}", headers=auth_headers)

	def test_world_book_imports_as_whole_book_scene(self, client, auth_headers):
		payload = {
			"name": "E2E World Book",
			"description": "Standing directives.",
			"entries": {
				"0": {"comment": "STATE", "content": "Directive one.", "group": "Sandbox"},
				"1": {"comment": "PULSE", "content": "Directive two.", "group": "Sandbox"},
			},
		}
		files = {"file": ("worldbook.json", json.dumps(payload), "application/json")}

		preview_resp = client.post("/api/v1/import/lorebook/preview", files=files, headers=auth_headers)
		assert preview_resp.status_code == 200, preview_resp.text
		preview = preview_resp.json()["result"]
		assert preview["characters"] == []
		assert len(preview["scenes"]) == 1
		book_key = preview["scenes"][0]["key"]
		assert preview["scenes"][0]["name"] == "E2E World Book"

		data = {
			"is_public": "false",
			"import_images": "false",
			"link_scenes": "false",
			"selected_keys": [book_key],
		}
		import_resp = client.post("/api/v1/import/lorebook", files=files, data=data, headers=auth_headers)
		assert import_resp.status_code == 200, import_resp.text
		result = import_resp.json()["result"]
		assert result["scenes_created"] == 1
		assert result["characters_created"] == 0

		for sid in result["scene_ids"]:
			client.delete(f"/api/v1/scenes/{sid}", headers=auth_headers)

	def test_attach_to_existing_character_appends_prompt(self, client, auth_headers):
		# Create a character to attach to. Create returns no id, so list to find it.
		create_resp = client.post(
			"/api/v1/characters",
			json={
				"name": "E2E Attach Target",
				"system_prompt": "You are the target.",
				"is_public": False,
				"owner_id": "5dbdc924-968a-4c50-94a8-44cdd165e460",
			},
			headers=auth_headers,
		)
		assert create_resp.status_code == 200, create_resp.text
		list_resp = client.get(
			"/api/v1/characters/?limit=100&offset=0",
			headers=auth_headers,
		)
		assert list_resp.status_code == 200, list_resp.text
		character_id = next(c["id"] for c in list_resp.json()["result"]["items"] if c["name"] == "E2E Attach Target")

		payload = {
			"entries": {
				"0": {"comment": "Target lore", "content": "Wing commander.", "group": "target"},
			}
		}
		files = {"file": ("lorebook.json", json.dumps(payload), "application/json")}
		data = {
			"is_public": "false",
			"import_images": "false",
			"attach_to_character_id": character_id,
		}

		try:
			import_resp = client.post("/api/v1/import/lorebook", files=files, data=data, headers=auth_headers)
			assert import_resp.status_code == 200, import_resp.text
			result = import_resp.json()["result"]
			assert result["appended_to_character_id"] == character_id
			assert result["characters_created"] == 0
			assert result["scenes_created"] == 0

			get_resp = client.get(f"/api/v1/characters/{character_id}", headers=auth_headers)
			assert get_resp.status_code == 200, get_resp.text
			system_prompt = get_resp.json()["result"]["system_prompt"]
			assert system_prompt.startswith("You are the target.")
			assert "Wing commander." in system_prompt
		finally:
			client.delete(f"/api/v1/characters/{character_id}", headers=auth_headers)
