import pytest


@pytest.mark.e2e
class TestCharactersAPI:
	"""End-to-end tests for characters API endpoints."""

	def test_create_character_with_valid_data(self, client, auth_headers, cleanup_test_characters):
		"""Test creating a character with valid data."""
		payload = {
			"name": "Test Character",
			"system_prompt": "You are a helpful assistant character for testing",
			"owner_id": "5dbdc924-968a-4c50-94a8-44cdd165e460",
			"is_public": False,
		}

		response = client.post("/api/v1/characters/", json=payload, headers=auth_headers)

		# Debug: Print response details if not 200
		if response.status_code != 200:
			print(f"Response status: {response.status_code}")
			print(f"Response content: {response.text}")

		assert response.status_code == 200
		data = response.json()
		assert "result" in data
		assert "correlation_id" in data
		assert isinstance(data["result"], list)

	def test_create_character_with_minimal_data(self, client, auth_headers, cleanup_test_characters):
		"""Test creating a character with only required fields."""
		payload = {
			"name": "Minimal Character",
			"system_prompt": "Simple character prompt",
			"owner_id": "5dbdc924-968a-4c50-94a8-44cdd165e460",
		}

		response = client.post("/api/v1/characters/", json=payload, headers=auth_headers)

		assert response.status_code == 200
		data = response.json()
		assert "result" in data
		assert "correlation_id" in data

	def test_create_character_missing_required_fields(self, client, auth_headers):
		"""Test creating a character with missing required fields."""
		# Missing name
		payload = {
			"system_prompt": "Character without name",
			"owner_id": "5dbdc924-968a-4c50-94a8-44cdd165e460",
		}

		response = client.post("/api/v1/characters/", json=payload, headers=auth_headers)

		assert response.status_code == 422

	def test_create_character_missing_system_prompt(self, client, auth_headers):
		"""Test creating a character without system_prompt."""
		payload = {
			"name": "Character without prompt",
			"owner_id": "5dbdc924-968a-4c50-94a8-44cdd165e460",
		}

		response = client.post("/api/v1/characters/", json=payload, headers=auth_headers)

		assert response.status_code == 422

	def test_create_character_owner_id_mismatch(self, client, auth_headers):
		"""Test creating a character with owner_id that doesn't match authenticated user."""
		payload = {
			"name": "Character with wrong owner",
			"system_prompt": "Test character with mismatched owner",
			"owner_id": "11111111-2222-3333-4444-555555555555",  # Different from auth user
		}

		response = client.post("/api/v1/characters/", json=payload, headers=auth_headers)

		assert response.status_code == 403
		data = response.json()
		assert "Character owner_id must match authenticated user" in data["detail"]

	def test_create_character_without_authentication(self, client):
		"""Test creating a character without authentication should return 401."""
		payload = {
			"name": "Unauthorized Character",
			"system_prompt": "Character created without auth",
			"owner_id": "5dbdc924-968a-4c50-94a8-44cdd165e460",
		}

		response = client.post("/api/v1/characters/", json=payload)

		assert response.status_code == 401

	def test_create_character_with_long_data(self, client, auth_headers, cleanup_test_characters):
		"""Test creating a character with very long data."""
		payload = {
			"name": "Very long character name " * 50,
			"system_prompt": "Very long system prompt " * 200,
			"owner_id": "5dbdc924-968a-4c50-94a8-44cdd165e460",
			"is_public": True,
		}

		response = client.post("/api/v1/characters/", json=payload, headers=auth_headers)

		assert response.status_code == 422

	def test_search_characters_without_filters(self, client):
		"""Test searching characters without any filters."""
		response = client.get("/api/v1/characters/")

		assert response.status_code == 200
		data = response.json()

		# Verify response structure
		assert "result" in data
		assert "correlation_id" in data
		assert isinstance(data["result"], dict)

		# Verify page structure
		result = data["result"]
		assert "items" in result
		assert "count" in result
		assert "limit" in result
		assert "offset" in result
		assert isinstance(result["items"], list)
		assert isinstance(result["count"], int)

	def test_search_characters_with_pagination(self, client):
		"""Test searching characters with pagination parameters."""
		response = client.get("/api/v1/characters/?limit=5&offset=0")

		assert response.status_code == 200
		data = response.json()
		result = data["result"]

		# Verify response structure - this is what we're really testing
		assert "items" in result
		assert "count" in result
		assert "limit" in result
		assert "offset" in result
		assert isinstance(result["items"], list)
		assert isinstance(result["count"], int)
		assert isinstance(result["limit"], int)
		assert isinstance(result["offset"], int)

		# Verify offset is correctly returned
		assert result["offset"] == 0

		# Verify that pagination is working - the number of items returned should be reasonable
		# and the limit should be a positive number (the API may return actual count or requested limit)
		assert result["limit"] > 0
		assert len(result["items"]) <= result["count"] if result["count"] > 0 else len(result["items"]) == 0

	def test_search_characters_with_invalid_pagination(self, client):
		response = client.get("/api/v1/characters/?limit=-1&offset=-5")

		# Should handle gracefully, likely with 422 or defaults
		assert response.status_code in [200, 422]

	def test_get_character_details_with_valid_uuid(self, client, auth_headers, cleanup_test_characters):
		# First create a character to get its ID
		payload = {
			"name": "Test Character for Details",
			"system_prompt": "Character for testing details endpoint",
			"owner_id": "5dbdc924-968a-4c50-94a8-44cdd165e460",
		}
		client.post("/api/v1/characters/", json=payload, headers=auth_headers)

		# Use a known UUID for testing (this might need adjustment based on actual data)
		test_uuid = "43341001-4ea1-4f03-b315-811d3264b6a3"
		response = client.get(f"/api/v1/characters/{test_uuid}", headers=auth_headers)

		# Should return 200 if character exists, 404 if not
		assert response.status_code in [200, 404]

		if response.status_code == 200:
			data = response.json()
			assert "result" in data
			assert "correlation_id" in data

	def test_get_character_details_with_invalid_uuid(self, client):
		response = client.get("/api/v1/characters/invalid-uuid")

		assert response.status_code == 422

	def test_delete_character_with_valid_uuid(self, client, auth_headers):
		test_uuid = "048a7fe5-f4c2-40ef-9745-7d85d7c4c5fb"
		response = client.delete(f"/api/v1/characters/{test_uuid}", headers=auth_headers)

		# 200 if deleted, 404 if absent, 403 if it exists but belongs to another user.
		assert response.status_code in [200, 403, 404]

		if response.status_code == 200:
			data = response.json()
			assert "result" in data
			assert "correlation_id" in data
			assert isinstance(data["result"], list)

	def test_delete_character_with_invalid_uuid(self, client, auth_headers):
		"""Test deleting a character with invalid UUID format."""
		response = client.delete("/api/v1/characters/invalid-uuid", headers=auth_headers)

		assert response.status_code == 422

	def test_update_character_with_valid_data(self, client, auth_headers):
		"""Test updating a character with valid data."""
		test_uuid = "90d27426-7b7a-4a4d-ba17-6f98b7c29c5e"
		payload = {
			"name": "Updated Character Name",
			"system_prompt": "Updated system prompt for character",
			"owner_id": "5dbdc924-968a-4c50-94a8-44cdd165e460",
			"is_public": True,
		}

		response = client.post(f"/api/v1/characters/update/{test_uuid}", json=payload, headers=auth_headers)

		# 200 if updated, 404 if absent, 403 if it belongs to another user.
		assert response.status_code in [200, 403, 404]

		if response.status_code == 200:
			data = response.json()
			assert "result" in data
			assert "correlation_id" in data
			assert isinstance(data["result"], list)

	def test_update_character_with_invalid_uuid(self, client, auth_headers):
		"""Test updating a character with invalid UUID format."""
		payload = {
			"name": "Updated Name",
			"system_prompt": "Updated prompt",
			"owner_id": "5dbdc924-968a-4c50-94a8-44cdd165e460",
		}

		response = client.post("/api/v1/characters/update/invalid-uuid", json=payload, headers=auth_headers)

		assert response.status_code == 422

	def test_update_character_missing_required_fields(self, client, auth_headers):
		"""Test updating a character with missing required fields."""
		test_uuid = "d99678f7-bb8c-41f4-9726-4722b44a5649"
		payload = {
			"name": "Updated Name Only",
			# Missing system_prompt and owner_id
		}

		response = client.post(f"/api/v1/characters/update/{test_uuid}", json=payload, headers=auth_headers)

		assert response.status_code == 422

	def test_update_character_with_empty_body(self, client, auth_headers):
		"""Test updating a character with empty request body."""
		test_uuid = "ad8b09b7-1723-4459-ba61-5bf3a2699c11"

		response = client.post(f"/api/v1/characters/update/{test_uuid}", json={}, headers=auth_headers)

		assert response.status_code == 422

	# Deterministic cross-user guards: assert 403 outright (the [200, 403, 404] tests
	# above would still pass if ownership enforcement were dropped). CHARACTER_ID is the
	# seeded admin-owned character defined below.
	def test_other_user_cannot_delete_character(self, client, other_auth_headers):
		response = client.delete(f"/api/v1/characters/{self.CHARACTER_ID}", headers=other_auth_headers)
		assert response.status_code == 403

	def test_other_user_cannot_update_character(self, client, other_auth_headers):
		payload = {
			"name": "Hijacked Character Name",
			"system_prompt": "Hijacked system prompt",
			"owner_id": "5dbdc924-968a-4c50-94a8-44cdd165e460",
			"is_public": True,
		}

		response = client.post(
			f"/api/v1/characters/update/{self.CHARACTER_ID}", json=payload, headers=other_auth_headers
		)

		assert response.status_code == 403

	def test_characters_api_response_structure(self, client):
		"""Test that all character endpoints return consistent response structure."""
		# Test search endpoint response structure
		response = client.get("/api/v1/characters/")
		assert response.status_code == 200
		data = response.json()

		# All endpoints should return this structure
		assert "result" in data
		assert "correlation_id" in data
		assert data["correlation_id"] is not None

	# Seeded "Helpful Assistant", owned by admin_test (the auth_headers user).
	CHARACTER_ID = "43341001-4ea1-4f03-b315-811d3264b6a3"

	def test_like_character_flow(self, client, auth_headers):
		"""Like, re-like (idempotent), read state, then unlike — restores baseline count."""
		before = client.get(f"/api/v1/characters/{self.CHARACTER_ID}/like", headers=auth_headers)
		assert before.status_code == 200
		baseline = before.json()["result"]["likes_count"]

		liked = client.post(f"/api/v1/characters/{self.CHARACTER_ID}/like", headers=auth_headers)
		assert liked.status_code == 200
		assert liked.json()["result"]["liked"] is True
		assert liked.json()["result"]["likes_count"] == baseline + 1

		# Re-liking is idempotent: the count must not grow again.
		again = client.post(f"/api/v1/characters/{self.CHARACTER_ID}/like", headers=auth_headers)
		assert again.status_code == 200
		assert again.json()["result"]["likes_count"] == baseline + 1

		state = client.get(f"/api/v1/characters/{self.CHARACTER_ID}/like", headers=auth_headers)
		assert state.status_code == 200
		assert state.json()["result"]["liked"] is True

		# Cleanup: unlike restores the baseline count.
		unliked = client.delete(f"/api/v1/characters/{self.CHARACTER_ID}/like", headers=auth_headers)
		assert unliked.status_code == 200
		assert unliked.json()["result"]["liked"] is False
		assert unliked.json()["result"]["likes_count"] == baseline

	def test_bookmark_character_flow(self, client, auth_headers):
		"""Bookmark, read state, then unbookmark a character."""
		bookmarked = client.post(f"/api/v1/characters/{self.CHARACTER_ID}/bookmark", headers=auth_headers)
		assert bookmarked.status_code == 200
		assert bookmarked.json()["result"]["bookmarked"] is True

		state = client.get(f"/api/v1/characters/{self.CHARACTER_ID}/bookmark", headers=auth_headers)
		assert state.status_code == 200
		assert state.json()["result"]["bookmarked"] is True

		removed = client.delete(f"/api/v1/characters/{self.CHARACTER_ID}/bookmark", headers=auth_headers)
		assert removed.status_code == 200
		assert removed.json()["result"]["bookmarked"] is False

	def test_like_character_requires_auth(self, client):
		"""Liking without authentication must be rejected."""
		response = client.post(f"/api/v1/characters/{self.CHARACTER_ID}/like")
		assert response.status_code == 401

	def test_like_character_invalid_uuid(self, client, auth_headers):
		"""An invalid character UUID in the like path must be rejected with 422."""
		response = client.post("/api/v1/characters/not-a-uuid/like", headers=auth_headers)
		assert response.status_code == 422

	# A valid-but-nonexistent id: every like/bookmark verb must 404 (not 409 on the
	# writes via the FK, nor a silent 200 with likes_count: 0 on the reads).
	UNKNOWN_CHARACTER_ID = "00000000-0000-0000-0000-000000000000"

	def test_like_bookmark_unknown_character_returns_404(self, client, auth_headers):
		like_verbs = [
			("post", f"/api/v1/characters/{self.UNKNOWN_CHARACTER_ID}/like"),
			("get", f"/api/v1/characters/{self.UNKNOWN_CHARACTER_ID}/like"),
			("delete", f"/api/v1/characters/{self.UNKNOWN_CHARACTER_ID}/like"),
			("post", f"/api/v1/characters/{self.UNKNOWN_CHARACTER_ID}/bookmark"),
			("get", f"/api/v1/characters/{self.UNKNOWN_CHARACTER_ID}/bookmark"),
			("delete", f"/api/v1/characters/{self.UNKNOWN_CHARACTER_ID}/bookmark"),
		]
		for method, path in like_verbs:
			response = getattr(client, method)(path, headers=auth_headers)
			assert response.status_code == 404, f"{method.upper()} {path} -> {response.status_code}"
