import pytest
import uuid


@pytest.mark.e2e
class TestScenesAPI:
	"""End-to-end tests for scenes API endpoints."""

	def test_create_scene_with_valid_data(self, client, auth_headers):
		"""Test creating a scene with valid data."""
		payload = {
			"title": "Test Scene",
			"background_prompt": "A beautiful fantasy world with magic",
			"description": "A test scene for e2e testing",
			"owner_id": "5dbdc924-968a-4c50-94a8-44cdd165e460",
			"initial_message_text": "Welcome to this magical world! What adventure awaits you today?",
		}

		response = client.post("/api/v1/scenes/", json=payload, headers=auth_headers)

		# Debug: Print response details if not 200
		if response.status_code != 200:
			print(f"Response status: {response.status_code}")
			print(f"Response content: {response.text}")

		assert response.status_code == 200
		data = response.json()
		assert "result" in data
		assert "correlation_id" in data
		assert isinstance(data["result"], list)

	def test_create_scene_with_minimal_data(self, client, auth_headers):
		"""Test creating a scene with only required fields."""
		payload = {
			"title": "Minimal Scene",
			"background_prompt": "Simple background",
			"owner_id": "5dbdc924-968a-4c50-94a8-44cdd165e460",
			"initial_message_text": "Hello! Let's begin our conversation.",
		}

		response = client.post("/api/v1/scenes/", json=payload, headers=auth_headers)

		assert response.status_code == 200
		data = response.json()
		assert "result" in data
		assert "correlation_id" in data

	def test_create_scene_missing_required_fields(self, client, auth_headers):
		"""Test creating a scene with missing required fields."""
		# Missing title
		payload = {
			"background_prompt": "Background without title",
			"owner_id": "5dbdc924-968a-4c50-94a8-44cdd165e460",
		}

		response = client.post("/api/v1/scenes/", json=payload, headers=auth_headers)

		assert response.status_code == 422

	def test_create_scene_missing_background_prompt(self, client, auth_headers):
		"""Test creating a scene without background_prompt."""
		payload = {
			"title": "Scene without background",
			"owner_id": "5dbdc924-968a-4c50-94a8-44cdd165e460",
		}

		response = client.post("/api/v1/scenes/", json=payload, headers=auth_headers)

		assert response.status_code == 422

	def test_create_scene_with_empty_title(self, client, auth_headers):
		"""Test creating a scene with empty title."""
		payload = {
			"title": "",
			"background_prompt": "Background with empty title",
			"owner_id": "5dbdc924-968a-4c50-94a8-44cdd165e460",
			"initial_message_text": "Welcome! Ready to start our conversation?",
		}

		response = client.post("/api/v1/scenes/", json=payload, headers=auth_headers)

		# Should work with empty title (no validation constraint shown in model)
		assert response.status_code == 200

	def test_create_scene_with_long_data(self, client, auth_headers):
		"""Test creating a scene with very long data."""
		payload = {
			"title": "Very long title " * 100,
			"background_prompt": "Very long background prompt " * 200,
			"description": "Very long description " * 150,
			"owner_id": "5dbdc924-968a-4c50-94a8-44cdd165e460",
			"initial_message_text": "Very long initial message " * 100,
		}

		response = client.post("/api/v1/scenes/", json=payload, headers=auth_headers)

		assert response.status_code == 200

	def test_create_scene_without_authentication(self, client):
		"""Test creating a scene without authentication should return 401."""
		payload = {
			"title": "Test Scene",
			"background_prompt": "A beautiful fantasy world with magic",
			"description": "A test scene for e2e testing",
			"owner_id": "5dbdc924-968a-4c50-94a8-44cdd165e460",
			"initial_message_text": "Welcome to this magical world! What adventure awaits you today?",
		}

		response = client.post("/api/v1/scenes/", json=payload)

		assert response.status_code == 401

	def test_search_scenes_without_filters(self, client):
		"""Test searching scenes without any filters."""
		response = client.get("/api/v1/scenes/")

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

	def test_search_scenes_with_pagination(self, client):
		"""Test searching scenes with pagination parameters."""
		params = {"limit": 5, "offset": 0}

		response = client.get("/api/v1/scenes/", params=params)

		assert response.status_code == 200
		data = response.json()
		result = data["result"]

		assert result["limit"] == 5
		assert result["offset"] == 0
		assert len(result["items"]) <= 5

	def test_search_scenes_with_title_filter(self, client):
		"""Test searching scenes by title."""
		params = {"title": ["Test Scene"], "limit": 10}

		response = client.get("/api/v1/scenes/", params=params)

		assert response.status_code == 200
		data = response.json()
		result = data["result"]

		assert "items" in result
		assert isinstance(result["items"], list)

	def test_search_scenes_with_owner_filter(self, client):
		"""Test searching scenes by owner."""
		test_uuid = str(uuid.uuid4())
		params = {"owner": [test_uuid], "limit": 10}

		response = client.get("/api/v1/scenes/", params=params)

		assert response.status_code == 200
		data = response.json()
		result = data["result"]

		assert "items" in result
		assert isinstance(result["items"], list)

	def test_search_scenes_with_ids_filter(self, client):
		"""Test searching scenes by IDs."""
		test_uuid = str(uuid.uuid4())
		params = {"ids": [test_uuid], "limit": 10}

		response = client.get("/api/v1/scenes/", params=params)

		assert response.status_code == 200
		data = response.json()
		result = data["result"]

		assert "items" in result
		assert isinstance(result["items"], list)

	def test_search_scenes_with_characters_filter(self, client):
		"""Test searching scenes by characters."""
		test_uuid = str(uuid.uuid4())
		params = {"characters": [test_uuid], "limit": 10}

		response = client.get("/api/v1/scenes/", params=params)

		assert response.status_code == 200
		data = response.json()
		result = data["result"]

		assert "items" in result
		assert isinstance(result["items"], list)

	def test_search_scenes_by_title_search(self, client):
		"""Test searching scenes with a case-insensitive title substring."""
		params = {"title_search": "adventure", "limit": 10}

		response = client.get("/api/v1/scenes/", params=params)

		assert response.status_code == 200
		data = response.json()
		result = data["result"]

		assert "items" in result
		assert isinstance(result["items"], list)
		# every returned scene must contain the searched substring (case-insensitive)
		for scene in result["items"]:
			assert "adventure" in scene["title"].lower()

	def test_search_scenes_sort_by_messages_count(self, client):
		"""Test sorting scenes by message count (descending)."""
		params = {"sort_by": "messages_count", "sort_order": "desc", "limit": 10}

		response = client.get("/api/v1/scenes/", params=params)

		assert response.status_code == 200
		data = response.json()
		result = data["result"]

		assert "items" in result
		assert isinstance(result["items"], list)

	def test_search_scenes_sort_by_chats_count(self, client):
		"""Test sorting scenes by chat count (ascending)."""
		params = {"sort_by": "chats_count", "sort_order": "asc", "limit": 10}

		response = client.get("/api/v1/scenes/", params=params)

		assert response.status_code == 200
		data = response.json()
		result = data["result"]

		assert "items" in result
		assert isinstance(result["items"], list)

	def test_search_scenes_invalid_sort_by(self, client):
		"""An unknown sort_by value must be rejected with 422."""
		params = {"sort_by": "not_a_real_field"}

		response = client.get("/api/v1/scenes/", params=params)

		assert response.status_code == 422

	def test_search_scenes_invalid_sort_order(self, client):
		"""An unknown sort_order value must be rejected with 422."""
		params = {"sort_by": "title", "sort_order": "sideways"}

		response = client.get("/api/v1/scenes/", params=params)

		assert response.status_code == 422

	def test_search_scenes_with_invalid_uuid(self, client):
		"""Test searching scenes with invalid UUID format."""
		params = {"ids": ["not-a-uuid"], "limit": 10}

		response = client.get("/api/v1/scenes/", params=params)

		# Should return validation error for invalid UUID
		assert response.status_code == 422

	def test_search_scenes_with_negative_limit(self, client):
		"""Test searching scenes with negative limit."""
		params = {"limit": -1}

		response = client.get("/api/v1/scenes/", params=params)

		# Should handle negative limit appropriately
		assert response.status_code in [200, 400, 422]

	def test_search_scenes_with_large_offset(self, client):
		"""Test searching scenes with very large offset."""
		params = {"offset": 10000, "limit": 10}

		response = client.get("/api/v1/scenes/", params=params)

		assert response.status_code == 200
		data = response.json()
		result = data["result"]

		# Should return empty results for large offset
		assert "items" in result
		assert isinstance(result["items"], list)

	def test_get_scene_details_with_valid_uuid(self, client):
		"""Test getting scene details with valid UUID."""
		test_uuid = str(uuid.uuid4())

		response = client.get(f"/api/v1/scenes/{test_uuid}")

		# Could be 200 (found) or 404 (not found) depending on whether scene exists
		assert response.status_code in [200, 404]

		if response.status_code == 200:
			data = response.json()
			assert "result" in data
			assert "correlation_id" in data
			# Verify scene structure
			scene = data["result"]
			assert isinstance(scene, dict)
			assert "title" in scene
			assert "background_prompt" in scene

	def test_get_scene_details_with_invalid_uuid(self, client):
		"""Test getting scene details with invalid UUID format."""
		invalid_uuid = "not-a-uuid"

		response = client.get(f"/api/v1/scenes/{invalid_uuid}")

		# Should return validation error for invalid UUID
		assert response.status_code == 422

	def test_delete_scene_with_valid_uuid(self, client):
		"""Test deleting a scene with valid UUID."""
		test_uuid = str(uuid.uuid4())

		response = client.delete(f"/api/v1/scenes/{test_uuid}")

		# Could be 200 (success), 404 (not found), or 400 (deletion failed)
		assert response.status_code in [200, 404, 400]

		if response.status_code == 200:
			data = response.json()
			assert "result" in data
			assert "correlation_id" in data
			assert isinstance(data["result"], list)

	def test_delete_scene_with_invalid_uuid(self, client):
		"""Test deleting a scene with invalid UUID format."""
		invalid_uuid = "not-a-uuid"

		response = client.delete(f"/api/v1/scenes/{invalid_uuid}")

		# Should return validation error for invalid UUID
		assert response.status_code == 422

	def test_update_scene_with_valid_data(self, client):
		"""Test updating a scene with valid data."""
		test_uuid = str(uuid.uuid4())
		payload = {
			"title": "Updated Scene Title",
			"background_prompt": "Updated background prompt",
			"description": "Updated description",
			"owner_id": "5dbdc924-968a-4c50-94a8-44cdd165e460",
			"initial_message_text": "Welcome to the updated scene! How can I help you today?",
		}

		response = client.post(f"/api/v1/scenes/update/{test_uuid}", json=payload)

		# Could be 200 (success), 404 (not found), or 400 (update failed)
		assert response.status_code in [200, 404, 400]

		if response.status_code == 200:
			data = response.json()
			assert "result" in data
			assert "correlation_id" in data
			assert isinstance(data["result"], list)

	def test_update_scene_with_invalid_uuid(self, client):
		"""Test updating a scene with invalid UUID format."""
		invalid_uuid = "not-a-uuid"
		payload = {
			"title": "Updated Title",
			"background_prompt": "Updated prompt",
			"initial_message_text": "Welcome to the updated scene!",
		}

		response = client.post(f"/api/v1/scenes/update/{invalid_uuid}", json=payload)

		# Should return validation error for invalid UUID
		assert response.status_code == 422

	def test_update_scene_missing_required_fields(self, client):
		"""Test updating a scene with missing required fields."""
		test_uuid = str(uuid.uuid4())
		payload = {"description": "Only description provided"}

		response = client.post(f"/api/v1/scenes/update/{test_uuid}", json=payload)

		# Should return validation error for missing required fields
		assert response.status_code == 422

	def test_update_scene_with_empty_body(self, client):
		"""Test updating a scene with empty request body."""
		test_uuid = str(uuid.uuid4())

		response = client.post(f"/api/v1/scenes/update/{test_uuid}", json={})

		# Should return validation error for empty body
		assert response.status_code == 422

	def test_scenes_api_response_structure(self, client):
		"""Test that all scenes API responses have consistent structure."""
		# Test search endpoint response structure
		response = client.get("/api/v1/scenes/")
		assert response.status_code == 200
		data = response.json()

		# All API responses should have these fields
		assert "result" in data
		assert "correlation_id" in data
		assert isinstance(data["correlation_id"], str)
		assert len(data["correlation_id"]) > 0
