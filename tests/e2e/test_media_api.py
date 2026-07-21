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

	def test_search_media_invalid_uuid_filter_returns_422(self, client, auth_headers):
		response = client.get("/api/v1/media/?entity_id=not-a-uuid", headers=auth_headers)
		assert response.status_code == 422
