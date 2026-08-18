from uuid import uuid4

import pytest

# Auth headers authenticate as admin (5dbdc924-...), who owns these seeded entities.
ADMIN_CHARACTER_ID = "43341001-4ea1-4f03-b315-811d3264b6a3"  # "Helpful Assistant"
# A character owned by another user (Code Mentor, owner f5ac5447-...).
OTHER_CHARACTER_ID = "1a0fca84-996c-43b5-976a-0c676c61dde5"
# Seeded public, object-backed scene asset (anonymous-readable).
PUBLIC_SCENE_MEDIA_ID = "1c93f02d-e19a-4304-9eaa-bcf9edc6d24f"
UNKNOWN_MEDIA_ID = "00000000-0000-0000-0000-000000000000"

# A real 1x1 image is not required: ImageReader._sniff_image_type only checks that
# the bytes' magic number matches the declared content_type, so the PNG signature
# plus a body is enough to pass validation (see src/infrastructure/gateways/image_reader.py).
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _upload(client, headers, entity_id=ADMIN_CHARACTER_ID, entity_type="character", is_public=True):
	"""POST a PNG to /media under the given entity. Returns the response."""
	return client.post(
		"/api/v1/media/",
		files={"file": ("avatar.png", PNG_BYTES, "image/png")},
		data={
			"entity_type": entity_type,
			"entity_id": entity_id,
			"is_public": "true" if is_public else "false",
		},
		headers=headers,
	)


@pytest.mark.e2e
class TestMediaAPI:
	"""End-to-end tests for the media API (upload/read/search/delete + auth/ownership)."""

	# ── Upload lifecycle (exercises MinIO: ensure_buckets + put_object) ──────────

	def test_upload_then_get_then_delete_lifecycle(self, client, auth_headers):
		"""Upload a real image, read it back, delete it, then confirm it is gone."""
		uploaded = _upload(client, auth_headers, is_public=True)
		assert uploaded.status_code == 200, uploaded.text
		asset = uploaded.json()["result"]
		media_id = asset["id"]

		try:
			assert asset["content_type"] == "image/png"
			assert asset["entity_type"] == "character"
			assert asset["entity_id"] == ADMIN_CHARACTER_ID
			assert asset["is_public"] is True
			assert asset["size_bytes"] == len(PNG_BYTES)
			assert asset["url"]

			fetched = client.get(f"/api/v1/media/{media_id}", headers=auth_headers)
			assert fetched.status_code == 200
			assert fetched.json()["result"]["id"] == media_id

			deleted = client.delete(f"/api/v1/media/{media_id}", headers=auth_headers)
			assert deleted.status_code == 200

			after = client.get(f"/api/v1/media/{media_id}", headers=auth_headers)
			assert after.status_code == 404
		finally:
			# Idempotent cleanup: a 404 here means the test already deleted it.
			client.delete(f"/api/v1/media/{media_id}", headers=auth_headers)

	# ── Authentication surface (route dep runs before storage) ──────────────────

	def test_upload_without_auth_returns_401(self, client):
		response = _upload(client, headers=None)
		assert response.status_code == 401

	def test_search_without_auth_returns_401(self, client):
		response = client.get("/api/v1/media/")
		assert response.status_code == 401

	def test_delete_without_auth_returns_401(self, client):
		response = client.delete(f"/api/v1/media/{PUBLIC_SCENE_MEDIA_ID}")
		assert response.status_code == 401

	# ── Ownership (checked in the service before any storage read/write) ────────

	def test_upload_to_unowned_entity_returns_403(self, client, auth_headers):
		"""Attaching media to an entity the caller does not own is rejected before
		the file is read or any object is stored."""
		response = _upload(client, auth_headers, entity_id=OTHER_CHARACTER_ID)
		assert response.status_code == 403
		assert "Not allowed to attach media to this entity" in response.json().get("detail", "")

	def test_other_user_cannot_delete_media(self, client, auth_headers, other_auth_headers):
		"""Media owned by one user cannot be deleted by another."""
		uploaded = _upload(client, auth_headers)
		assert uploaded.status_code == 200, uploaded.text
		media_id = uploaded.json()["result"]["id"]

		try:
			response = client.delete(f"/api/v1/media/{media_id}", headers=other_auth_headers)
			assert response.status_code == 403
		finally:
			client.delete(f"/api/v1/media/{media_id}", headers=auth_headers)

	# ── Reads of seeded media (DB + offline URL signing; no MinIO needed) ───────

	def test_search_media_returns_page(self, client, auth_headers):
		response = client.get("/api/v1/media/", headers=auth_headers)

		assert response.status_code == 200
		result = response.json()["result"]
		assert "items" in result
		assert "count" in result
		assert "limit" in result
		assert "offset" in result
		assert isinstance(result["items"], list)

	def test_search_media_filter_by_entity_type(self, client, auth_headers):
		response = client.get("/api/v1/media/?entity_type=character", headers=auth_headers)

		assert response.status_code == 200
		for item in response.json()["result"]["items"]:
			assert item["entity_type"] == "character"

	def test_get_public_media_anonymous_200(self, client):
		"""A public asset is readable without authentication."""
		response = client.get(f"/api/v1/media/{PUBLIC_SCENE_MEDIA_ID}")

		assert response.status_code == 200
		asset = response.json()["result"]
		assert asset["id"] == PUBLIC_SCENE_MEDIA_ID
		assert asset["url"]

	def test_get_unknown_media_returns_404(self, client, auth_headers):
		response = client.get(f"/api/v1/media/{UNKNOWN_MEDIA_ID}", headers=auth_headers)
		assert response.status_code == 404

	def test_get_media_for_character_entity(self, client, auth_headers):
		"""GET /media/entity/{type}/{id} returns the character's assets, newest first."""
		response = client.get(f"/api/v1/media/entity/character/{ADMIN_CHARACTER_ID}", headers=auth_headers)

		assert response.status_code == 200
		items = response.json()["result"]
		assert isinstance(items, list)
		assert items, "seeded character should have at least one portrait"
		for item in items:
			assert item["entity_type"] == "character"
			assert item["entity_id"] == ADMIN_CHARACTER_ID
			assert item["url"]

	def test_upload_then_entity_listing_newest_first(self, client, auth_headers):
		"""After an upload, the fresh asset must come back first for the entity."""
		uploaded = _upload(client, auth_headers, is_public=True)
		assert uploaded.status_code == 200, uploaded.text
		media_id = uploaded.json()["result"]["id"]

		try:
			after = client.get(f"/api/v1/media/entity/character/{ADMIN_CHARACTER_ID}", headers=auth_headers)
			assert after.status_code == 200
			assert after.json()["result"][0]["id"] == media_id
		finally:
			client.delete(f"/api/v1/media/{media_id}", headers=auth_headers)

	def test_entity_listing_hides_private_media_of_others(self, client, auth_headers, other_auth_headers):
		"""A private upload is invisible to anyone but its owner via the entity listing."""
		uploaded = _upload(client, auth_headers, is_public=False)
		assert uploaded.status_code == 200, uploaded.text
		media_id = uploaded.json()["result"]["id"]

		try:
			mine = client.get(f"/api/v1/media/entity/character/{ADMIN_CHARACTER_ID}", headers=auth_headers)
			assert mine.status_code == 200
			assert media_id in [item["id"] for item in mine.json()["result"]]

			theirs = client.get(f"/api/v1/media/entity/character/{ADMIN_CHARACTER_ID}", headers=other_auth_headers)
			assert theirs.status_code == 200
			assert media_id not in [item["id"] for item in theirs.json()["result"]]
		finally:
			client.delete(f"/api/v1/media/{media_id}", headers=auth_headers)

	def test_entity_listing_anonymous_sees_only_public(self, client, auth_headers):
		uploaded = _upload(client, auth_headers, is_public=False)
		assert uploaded.status_code == 200, uploaded.text
		media_id = uploaded.json()["result"]["id"]

		try:
			response = client.get(f"/api/v1/media/entity/character/{ADMIN_CHARACTER_ID}")

			assert response.status_code == 200
			ids = [item["id"] for item in response.json()["result"]]
			assert media_id not in ids
			for item in response.json()["result"]:
				assert item["is_public"] is True
		finally:
			client.delete(f"/api/v1/media/{media_id}", headers=auth_headers)

	def test_search_media_invalid_uuid_filter_returns_422(self, client, auth_headers):
		response = client.get("/api/v1/media/?entity_id=not-a-uuid", headers=auth_headers)
		assert response.status_code == 422

	# ── PATCH metadata (caption / layer / sort_order) ────────────────────────────

	def test_patch_updates_caption_layer_order(self, client, auth_headers):
		"""PATCH sets metadata; omitted fields stay unchanged; empty caption clears."""
		uploaded = _upload(client, auth_headers)
		assert uploaded.status_code == 200, uploaded.text
		media_id = uploaded.json()["result"]["id"]

		try:
			patched = client.patch(
				f"/api/v1/media/{media_id}",
				json={"caption": "hero", "layer": "foreground", "sort_order": 3},
				headers=auth_headers,
			)
			assert patched.status_code == 200, patched.text
			asset = patched.json()["result"]
			assert asset["caption"] == "hero"
			assert asset["layer"] == "foreground"
			assert asset["sort_order"] == 3

			fetched = client.get(f"/api/v1/media/{media_id}", headers=auth_headers)
			assert fetched.status_code == 200
			assert fetched.json()["result"]["caption"] == "hero"

			# Omitted fields are left alone; caption="" clears to null.
			cleared = client.patch(f"/api/v1/media/{media_id}", json={"caption": ""}, headers=auth_headers)
			assert cleared.status_code == 200, cleared.text
			asset = cleared.json()["result"]
			assert asset["caption"] is None
			assert asset["layer"] == "foreground"
			assert asset["sort_order"] == 3

			# A body with every field omitted is a valid no-op.
			noop = client.patch(f"/api/v1/media/{media_id}", json={}, headers=auth_headers)
			assert noop.status_code == 200
			assert noop.json()["result"]["layer"] == "foreground"
		finally:
			client.delete(f"/api/v1/media/{media_id}", headers=auth_headers)

	def test_patch_defaults_on_upload(self, client, auth_headers):
		"""Fresh uploads default to sort_order=0 / caption=null / layer=background."""
		uploaded = _upload(client, auth_headers)
		assert uploaded.status_code == 200, uploaded.text
		media_id = uploaded.json()["result"]["id"]

		try:
			asset = uploaded.json()["result"]
			assert asset["sort_order"] == 0
			assert asset["caption"] is None
			assert asset["layer"] == "background"
		finally:
			client.delete(f"/api/v1/media/{media_id}", headers=auth_headers)

	def test_patch_validation_errors(self, client, auth_headers):
		"""caption>200 chars, unknown layer and negative sort_order are 422s."""
		uploaded = _upload(client, auth_headers)
		assert uploaded.status_code == 200, uploaded.text
		media_id = uploaded.json()["result"]["id"]

		try:
			bad_caption = client.patch(f"/api/v1/media/{media_id}", json={"caption": "x" * 201}, headers=auth_headers)
			assert bad_caption.status_code == 422

			bad_layer = client.patch(f"/api/v1/media/{media_id}", json={"layer": "middle"}, headers=auth_headers)
			assert bad_layer.status_code == 422

			bad_order = client.patch(f"/api/v1/media/{media_id}", json={"sort_order": -1}, headers=auth_headers)
			assert bad_order.status_code == 422
		finally:
			client.delete(f"/api/v1/media/{media_id}", headers=auth_headers)

	def test_patch_requires_auth(self, client):
		response = client.patch(f"/api/v1/media/{PUBLIC_SCENE_MEDIA_ID}", json={"caption": "x"})
		assert response.status_code == 401

	def test_patch_requires_owner(self, client, auth_headers, other_auth_headers):
		uploaded = _upload(client, auth_headers)
		assert uploaded.status_code == 200, uploaded.text
		media_id = uploaded.json()["result"]["id"]

		try:
			response = client.patch(f"/api/v1/media/{media_id}", json={"caption": "mine"}, headers=other_auth_headers)
			assert response.status_code == 403
		finally:
			client.delete(f"/api/v1/media/{media_id}", headers=auth_headers)

	def test_patch_unknown_media_404(self, client, auth_headers):
		response = client.patch(f"/api/v1/media/{UNKNOWN_MEDIA_ID}", json={"caption": "x"}, headers=auth_headers)
		assert response.status_code == 404

	def test_entity_listing_respects_sort_order(self, client, auth_headers):
		"""sort_order outranks recency; assets left at 0 stay newest-first among themselves."""
		ADMIN_USER_ID = "5dbdc924-968a-4c50-94a8-44cdd165e460"
		created = []
		try:
			for _ in range(3):
				uploaded = _upload(client, auth_headers, entity_type="user", entity_id=ADMIN_USER_ID)
				assert uploaded.status_code == 200, uploaded.text
				created.append(uploaded.json()["result"]["id"])

			first, second, third = created  # upload order == recency order (newest last)
			# third -> position 0, first -> position 2; second stays at default 0.
			for media_id, order in ((third, 0), (first, 2)):
				response = client.patch(f"/api/v1/media/{media_id}", json={"sort_order": order}, headers=auth_headers)
				assert response.status_code == 200, response.text

			listing = client.get(f"/api/v1/media/entity/user/{ADMIN_USER_ID}", headers=auth_headers)
			assert listing.status_code == 200
			ids = [item["id"] for item in listing.json()["result"]]

			assert ids.index(third) < ids.index(second) < ids.index(first)
		finally:
			for media_id in created:
				client.delete(f"/api/v1/media/{media_id}", headers=auth_headers)

	def test_scene_characters_ordered_by_attachment(self, client, auth_headers):
		"""GET /scenes/{id}/characters returns characters in attachment order."""
		suffix = uuid4().hex[:8]
		character_names = tuple(f"Attach Order {label} {suffix}" for label in ("A", "B"))
		scene_title = f"Attach Order Scene {suffix}"
		created_characters = []
		scene_id = None
		try:
			for name in character_names:
				response = client.post(
					"/api/v1/characters/",
					json={
						"name": name,
						"system_prompt": "test prompt",
						"owner_id": "5dbdc924-968a-4c50-94a8-44cdd165e460",
					},
					headers=auth_headers,
				)
				assert response.status_code in (200, 201), response.text

			scene = client.post(
				"/api/v1/scenes/",
				json={
					"title": scene_title,
					"background_prompt": "test",
					"owner_id": "5dbdc924-968a-4c50-94a8-44cdd165e460",
					"initial_messages": [{"text": "The scene opens."}],
				},
				headers=auth_headers,
			)
			assert scene.status_code in (200, 201), scene.text

			# Create endpoints return no id: recover both via search (same as the app).
			found = client.get(
				"/api/v1/characters/",
				params={"names": list(character_names)},
				headers=auth_headers,
			)
			assert found.status_code == 200, found.text
			items = found.json()["result"]["items"]
			created_characters = [item["id"] for name in character_names for item in items if item["name"] == name]
			assert len(created_characters) == 2, "both test characters should be found"

			found_scene = client.get(
				"/api/v1/scenes/?owner=5dbdc924-968a-4c50-94a8-44cdd165e460&title_search=" + scene_title,
				headers=auth_headers,
			)
			assert found_scene.status_code == 200, found_scene.text
			scene_items = found_scene.json()["result"]["items"]
			scene_id = next((item["id"] for item in scene_items if item["title"] == scene_title), None)
			assert scene_id is not None, "created scene should be found"

			# Attach in two separate calls so attached_at differs deterministically.
			for character_id in created_characters:
				response = client.post(
					f"/api/v1/scenes/{scene_id}/characters",
					json={"character_ids": [character_id]},
					headers=auth_headers,
				)
				assert response.status_code in (200, 201), response.text

			listing = client.get(f"/api/v1/scenes/{scene_id}/characters", headers=auth_headers)
			assert listing.status_code == 200, listing.text
			ids = [item["id"] for item in listing.json()["result"]]
			assert ids == created_characters
		finally:
			if scene_id:
				client.delete(f"/api/v1/scenes/{scene_id}", headers=auth_headers)
			for character_id in created_characters:
				client.delete(f"/api/v1/characters/{character_id}", headers=auth_headers)
