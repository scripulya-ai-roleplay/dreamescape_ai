import pytest


@pytest.mark.e2e
class TestChatsAPI:
	"""End-to-end tests for chats API endpoints."""

	def test_create_chat_with_valid_data(self, client, auth_headers, cleanup_test_chats):
		"""Test creating a chat with valid data."""
		payload = {
			"title": "Test Chat",
			"user_id": "550e8400-e29b-41d4-a716-446655440000",
			"scene_id": "550e8400-e29b-41d4-a716-446655440001",
		}

		response = client.post("/api/v1/chats/", json=payload, headers=auth_headers)

		# Debug: Print response details if not 200
		if response.status_code != 200:
			print(f"Response status: {response.status_code}")
			print(f"Response content: {response.text}")

		assert response.status_code == 200
		data = response.json()
		assert "result" in data
		assert "correlation_id" in data
		assert isinstance(data["result"], list)

	def test_create_chat_with_minimal_data(self, client, auth_headers, cleanup_test_chats):
		"""Test creating a chat with only required fields."""
		payload = {
			"title": "Minimal Chat",
			"user_id": "550e8400-e29b-41d4-a716-446655440000",
			"scene_id": "550e8400-e29b-41d4-a716-446655440001",
		}

		response = client.post("/api/v1/chats/", json=payload, headers=auth_headers)

		assert response.status_code == 200
		data = response.json()
		assert "result" in data
		assert "correlation_id" in data

	def test_create_chat_missing_required_fields(self, client, auth_headers):
		"""Test creating a chat with missing required fields."""
		# Missing title
		payload = {
			"user_id": "550e8400-e29b-41d4-a716-446655440000",
			"scene_id": "550e8400-e29b-41d4-a716-446655440001",
		}

		response = client.post("/api/v1/chats/", json=payload, headers=auth_headers)

		assert response.status_code == 422

	def test_create_chat_missing_user_id(self, client, auth_headers):
		"""Test creating a chat without user_id."""
		payload = {
			"title": "Chat without user",
			"scene_id": "550e8400-e29b-41d4-a716-446655440001",
		}

		response = client.post("/api/v1/chats/", json=payload, headers=auth_headers)

		assert response.status_code == 422

	def test_create_chat_user_id_mismatch(self, client, auth_headers):
		"""Test creating a chat with user_id that doesn't match authenticated user."""
		payload = {
			"title": "Chat with wrong user",
			"user_id": "11111111-2222-3333-4444-555555555555",  # Different from auth user
			"scene_id": "550e8400-e29b-41d4-a716-446655440001",
		}

		response = client.post("/api/v1/chats/", json=payload, headers=auth_headers)

		assert response.status_code == 403
		data = response.json()
		assert "Chat user_id must match authenticated user" in data["detail"]

	def test_create_chat_without_authentication(self, client):
		"""Test creating a chat without authentication should return 401."""
		payload = {
			"title": "Unauthorized Chat",
			"user_id": "550e8400-e29b-41d4-a716-446655440000",
			"scene_id": "550e8400-e29b-41d4-a716-446655440001",
		}

		response = client.post("/api/v1/chats/", json=payload)

		assert response.status_code == 401

	def test_search_chats_without_filters(self, client):
		"""Test searching chats without any filters."""
		response = client.get("/api/v1/chats/")

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

	def test_search_chats_with_pagination(self, client):
		"""Test searching chats with pagination parameters."""
		response = client.get("/api/v1/chats/?limit=5&offset=0")

		assert response.status_code == 200
		data = response.json()
		result = data["result"]

		# Verify response structure
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

		# Verify pagination parameters
		assert result["limit"] > 0
		assert len(result["items"]) <= result["count"] if result["count"] > 0 else len(result["items"]) == 0

	def test_search_chats_with_invalid_pagination(self, client):
		response = client.get("/api/v1/chats/?limit=-1&offset=-5")

		# Should handle gracefully, likely with 422 or defaults
		assert response.status_code in [200, 422]

	def test_get_chat_details_with_valid_uuid(self, client, auth_headers, cleanup_test_chats):
		# First create a chat to get its ID
		payload = {
			"title": "Test Chat for Details",
			"user_id": "550e8400-e29b-41d4-a716-446655440000",
			"scene_id": "550e8400-e29b-41d4-a716-446655440001",
		}
		client.post("/api/v1/chats/", json=payload, headers=auth_headers)

		# Use a known UUID for testing (this might need adjustment based on actual data)
		test_uuid = "550e8400-e29b-41d4-a716-446655440002"
		response = client.get(f"/api/v1/chats/{test_uuid}")

		# Should return 200 if chat exists, 404 if not
		assert response.status_code in [200, 404]

		if response.status_code == 200:
			data = response.json()
			assert "result" in data
			assert "correlation_id" in data

	def test_get_chat_details_with_invalid_uuid(self, client):
		response = client.get("/api/v1/chats/invalid-uuid")

		assert response.status_code == 422

	def test_delete_chat_with_valid_uuid(self, client):
		test_uuid = "550e8400-e29b-41d4-a716-446655440003"
		response = client.delete(f"/api/v1/chats/{test_uuid}")

		# Should return 200 if chat exists and deleted, 404 if not found
		assert response.status_code in [200, 404]

		if response.status_code == 200:
			data = response.json()
			assert "result" in data
			assert "correlation_id" in data
			assert isinstance(data["result"], list)

	def test_delete_chat_with_invalid_uuid(self, client):
		"""Test deleting a chat with invalid UUID format."""
		response = client.delete("/api/v1/chats/invalid-uuid")

		assert response.status_code == 422

	def test_update_chat_with_valid_data(self, client):
		"""Test updating a chat with valid data."""
		test_uuid = "550e8400-e29b-41d4-a716-446655440004"
		payload = "Updated Chat Name"

		response = client.post(f"/api/v1/chats/update/{test_uuid}", json=payload)

		# Should return 200 if chat exists and updated, 404 if not found
		assert response.status_code in [200, 404]

		if response.status_code == 200:
			data = response.json()
			assert "result" in data
			assert "correlation_id" in data
			assert isinstance(data["result"], list)

	def test_update_chat_with_invalid_uuid(self, client):
		"""Test updating a chat with invalid UUID format."""
		payload = "Updated Name"

		response = client.post("/api/v1/chats/update/invalid-uuid", json=payload)

		assert response.status_code == 422

	def test_update_chat_with_empty_body(self, client):
		"""Test updating a chat with empty request body."""
		test_uuid = "550e8400-e29b-41d4-a716-446655440005"

		response = client.post(f"/api/v1/chats/update/{test_uuid}", json={})

		assert response.status_code == 422

	def test_chats_api_response_structure(self, client):
		"""Test that all chat endpoints return consistent response structure."""
		# Test search endpoint response structure
		response = client.get("/api/v1/chats/")
		assert response.status_code == 200
		data = response.json()

		# All endpoints should return this structure
		assert "result" in data
		assert "correlation_id" in data
		assert data["correlation_id"] is not None


@pytest.fixture(scope="function")
def cleanup_test_chats(client):
	"""Fixture that cleans up test chats after each test."""
	# This runs after the test
	yield

	# Clean up any chats with test-related names
	test_name_patterns = [
		"Test Chat",
		"Minimal Chat",
		"Chat without user",
		"Chat with wrong user",
		"Unauthorized Chat",
		"Test Chat for Details",
		"Updated Chat Name",
	]

	try:
		# Get all chats
		response = client.get("/api/v1/chats/?limit=100&offset=0")
		if response.status_code == 200:
			data = response.json()
			chats = data.get("result", {}).get("items", [])

			# Delete chats with test names
			for chat in chats:
				chat_title = chat.get("title", "")
				for pattern in test_name_patterns:
					if pattern in chat_title:
						chat_id = chat.get("id")
						if chat_id:
							client.delete(f"/api/v1/chats/{chat_id}")
							print(f"Cleaned up test chat: {chat_title} (ID: {chat_id})")
						break
	except Exception as e:
		print(f"Error during chat cleanup: {e}")
