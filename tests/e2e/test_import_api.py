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
