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

	def test_import_requires_authentication(self, client):
		files = {"file": ("lorebook.json", b'{"entries": {}}', "application/json")}

		response = client.post("/api/v1/import/lorebook", files=files)
		assert response.status_code == 401
