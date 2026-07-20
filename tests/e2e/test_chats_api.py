import pytest


@pytest.mark.e2e
class TestChatsAPI:
	"""End-to-end tests for chats API endpoints."""

	def test_create_chat_with_valid_data(self, client, auth_headers, cleanup_test_chats):
		"""Test creating a chat with valid data."""
		payload = {
			"title": "Test Chat",
			"user_id": "5dbdc924-968a-4c50-94a8-44cdd165e460",
			"scene_id": "5c194d75-401f-4fa2-808c-7092153135b7",
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
		assert isinstance(data["result"], dict)
		assert "id" in data["result"]

	def test_create_chat_with_minimal_data(self, client, auth_headers, cleanup_test_chats):
		"""Test creating a chat with only required fields."""
		payload = {
			"title": "Minimal Chat",
			"user_id": "5dbdc924-968a-4c50-94a8-44cdd165e460",
			"scene_id": "5c194d75-401f-4fa2-808c-7092153135b7",
		}

		response = client.post("/api/v1/chats/", json=payload, headers=auth_headers)

		assert response.status_code == 200
		data = response.json()
		assert "result" in data
		assert "correlation_id" in data

	def test_create_chat_with_user_character_id_round_trips(self, client, auth_headers, cleanup_test_chats):
		"""The chosen play-as persona is persisted on the chat and echoed on read."""
		character_id = "43341001-4ea1-4f03-b315-811d3264b6a3"  # Helpful Assistant (seeded)
		payload = {
			"title": "Persona Chat",
			"user_id": "5dbdc924-968a-4c50-94a8-44cdd165e460",
			"scene_id": "5c194d75-401f-4fa2-808c-7092153135b7",
			"user_character_id": character_id,
		}

		create_response = client.post("/api/v1/chats/", json=payload, headers=auth_headers)
		assert create_response.status_code == 200
		chat_id = create_response.json()["result"]["id"]

		detail_response = client.get(f"/api/v1/chats/{chat_id}", headers=auth_headers)
		assert detail_response.status_code == 200
		assert detail_response.json()["result"]["user_character_id"] == character_id

	HELPFUL_ASSISTANT_ID = "43341001-4ea1-4f03-b315-811d3264b6a3"

	def _create_persona_less_chat(self, client, auth_headers, title):
		payload = {
			"title": title,
			"user_id": "5dbdc924-968a-4c50-94a8-44cdd165e460",
			"scene_id": "5c194d75-401f-4fa2-808c-7092153135b7",
		}
		response = client.post("/api/v1/chats/", json=payload, headers=auth_headers)
		assert response.status_code == 200
		return response.json()["result"]["id"]

	def test_set_persona_makes_persona_less_chat_messagable(self, client, auth_headers, cleanup_test_chats):
		"""A chat created without a persona can have one set afterwards via the persona endpoint."""
		chat_id = self._create_persona_less_chat(client, auth_headers, "Persona-Less Chat")

		# Sanity: created without a persona.
		before = client.get(f"/api/v1/chats/{chat_id}", headers=auth_headers)
		assert before.status_code == 200
		assert before.json()["result"]["user_character_id"] is None

		# Set the persona and confirm it round-trips.
		set_response = client.post(
			f"/api/v1/chats/{chat_id}/persona",
			json={"user_character_id": self.HELPFUL_ASSISTANT_ID},
			headers=auth_headers,
		)
		assert set_response.status_code == 200

		after = client.get(f"/api/v1/chats/{chat_id}", headers=auth_headers)
		assert after.status_code == 200
		assert after.json()["result"]["user_character_id"] == self.HELPFUL_ASSISTANT_ID

	def test_set_persona_unknown_chat_returns_404(self, client, auth_headers):
		unknown_chat_id = "00000000-0000-0000-0000-000000000000"
		response = client.post(
			f"/api/v1/chats/{unknown_chat_id}/persona",
			json={"user_character_id": self.HELPFUL_ASSISTANT_ID},
			headers=auth_headers,
		)
		assert response.status_code == 404

	def test_set_persona_unknown_character_returns_404(self, client, auth_headers, cleanup_test_chats):
		chat_id = self._create_persona_less_chat(client, auth_headers, "Persona Bad Target Chat")
		unknown_character_id = "00000000-0000-0000-0000-000000000000"
		response = client.post(
			f"/api/v1/chats/{chat_id}/persona",
			json={"user_character_id": unknown_character_id},
			headers=auth_headers,
		)
		# A nonexistent persona must 404, not 409 via the FK constraint.
		assert response.status_code == 404

	def test_create_chat_missing_required_fields(self, client, auth_headers):
		"""Test creating a chat with missing required fields."""
		# Missing title
		payload = {
			"user_id": "5dbdc924-968a-4c50-94a8-44cdd165e460",
			"scene_id": "5c194d75-401f-4fa2-808c-7092153135b7",
		}

		response = client.post("/api/v1/chats/", json=payload, headers=auth_headers)

		assert response.status_code == 422

	def test_create_chat_missing_user_id(self, client, auth_headers):
		"""Test creating a chat without user_id."""
		payload = {
			"title": "Chat without user",
			"scene_id": "5c194d75-401f-4fa2-808c-7092153135b7",
		}

		response = client.post("/api/v1/chats/", json=payload, headers=auth_headers)

		assert response.status_code == 422

	def test_create_chat_user_id_mismatch(self, client, auth_headers):
		"""Test creating a chat with user_id that doesn't match authenticated user."""
		payload = {
			"title": "Chat with wrong user",
			"user_id": "11111111-2222-3333-4444-555555555555",  # Different from auth user
			"scene_id": "5c194d75-401f-4fa2-808c-7092153135b7",
		}

		response = client.post("/api/v1/chats/", json=payload, headers=auth_headers)

		assert response.status_code == 403
		data = response.json()
		assert "Chat user_id must match authenticated user" in data["detail"]

	def test_create_chat_without_authentication(self, client):
		"""Test creating a chat without authentication should return 401."""
		payload = {
			"title": "Unauthorized Chat",
			"user_id": "5dbdc924-968a-4c50-94a8-44cdd165e460",
			"scene_id": "5c194d75-401f-4fa2-808c-7092153135b7",
		}

		response = client.post("/api/v1/chats/", json=payload)

		assert response.status_code == 401

	def test_search_chats_without_filters(self, client, auth_headers):
		"""Test searching chats without any filters."""
		response = client.get("/api/v1/chats/", headers=auth_headers)

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

	def test_search_chats_with_pagination(self, client, auth_headers):
		"""Test searching chats with pagination parameters."""
		response = client.get("/api/v1/chats/?limit=5&offset=0", headers=auth_headers)

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

	def test_search_chats_with_invalid_pagination(self, client, auth_headers):
		response = client.get("/api/v1/chats/?limit=-1&offset=-5", headers=auth_headers)

		# Should handle gracefully, likely with 422 or defaults
		assert response.status_code in [200, 422]

	def test_get_chat_details_with_valid_uuid(self, client, auth_headers, cleanup_test_chats):
		# First create a chat to get its ID
		payload = {
			"title": "Test Chat for Details",
			"user_id": "5dbdc924-968a-4c50-94a8-44cdd165e460",
			"scene_id": "5c194d75-401f-4fa2-808c-7092153135b7",
		}
		client.post("/api/v1/chats/", json=payload, headers=auth_headers)

		# Use a known UUID for testing (this might need adjustment based on actual data)
		test_uuid = "048a7fe5-f4c2-40ef-9745-7d85d7c4c5fb"
		response = client.get(f"/api/v1/chats/{test_uuid}", headers=auth_headers)

		# 200 if the chat exists and is the caller's, 403 if it is another user's, 404 if absent.
		assert response.status_code in [200, 403, 404]

		if response.status_code == 200:
			data = response.json()
			assert "result" in data
			assert "correlation_id" in data

	def test_get_chat_details_with_invalid_uuid(self, client, auth_headers):
		response = client.get("/api/v1/chats/invalid-uuid", headers=auth_headers)

		assert response.status_code == 422

	def test_delete_chat_with_valid_uuid(self, client, auth_headers, cleanup_test_chats):
		# First create a chat to get its ID
		chat_payload = {
			"title": "Test Chat for Deletion",
			"user_id": "5dbdc924-968a-4c50-94a8-44cdd165e460",
			"scene_id": "5c194d75-401f-4fa2-808c-7092153135b7",
		}
		create_response = client.post("/api/v1/chats/", json=chat_payload, headers=auth_headers)
		assert create_response.status_code == 200
		create_data = create_response.json()
		assert "result" in create_data
		assert "correlation_id" in create_data

		# Extract the chat ID from the creation response
		created_chat = create_data["result"]
		if isinstance(created_chat, dict) and "id" in created_chat:
			test_uuid = created_chat["id"]
		else:
			test_uuid = None

		assert test_uuid is not None, f"Failed to extract chat ID from creation response. Response: {create_data}"

		# Now proceed with deletion using the extracted chat ID
		response = client.delete(f"/api/v1/chats/{test_uuid}", headers=auth_headers)
		# Should return 200 if chat exists and deleted
		assert response.status_code == 200
		data = response.json()
		assert "result" in data
		assert "correlation_id" in data
		assert isinstance(data["result"], list)

		# Create the chat back after deleting it
		chat_payload = {
			"title": "Recreated Test Chat",
			"user_id": "5dbdc924-968a-4c50-94a8-44cdd165e460",
			"scene_id": "5c194d75-401f-4fa2-808c-7092153135b7",
			# A persona is required to send messages (play a story), so attach one.
			"user_character_id": "43341001-4ea1-4f03-b315-811d3264b6a3",
		}

		create_response = client.post("/api/v1/chats/", json=chat_payload, headers=auth_headers)
		assert create_response.status_code == 200
		create_data = create_response.json()
		assert "result" in create_data
		assert "correlation_id" in create_data

		# Get the created chat ID from the response
		created_chat = create_data["result"]
		if isinstance(created_chat, list) and len(created_chat) > 0:
			chat_id = created_chat[0].get("id") if isinstance(created_chat[0], dict) else None
		elif isinstance(created_chat, dict):
			chat_id = created_chat.get("id")
		else:
			chat_id = None

		# If we have a chat ID, create messages for it
		if chat_id:
			# Create first message (user message)
			user_message_payload = {
				"message": "Hello, this is a test user message",
				"chat_id": chat_id,
				"role": "user",
			}

			user_msg_response = client.post("/api/v1/messages/", json=user_message_payload, headers=auth_headers)
			assert user_msg_response.status_code == 202
			user_msg_data = user_msg_response.json()
			assert "result" in user_msg_data
			assert "correlation_id" in user_msg_data

			# Create second message (model response)
			model_message_payload = {
				"message": "Hello! This is a test AI response message",
				"chat_id": chat_id,
				"role": "model",
			}

			model_msg_response = client.post("/api/v1/messages/", json=model_message_payload, headers=auth_headers)
			assert model_msg_response.status_code == 202
			model_msg_data = model_msg_response.json()
			assert "result" in model_msg_data
			assert "correlation_id" in model_msg_data

	def test_delete_chat_with_invalid_uuid(self, client, auth_headers):
		"""Test deleting a chat with invalid UUID format."""
		response = client.delete("/api/v1/chats/invalid-uuid", headers=auth_headers)

		assert response.status_code == 422

	def test_update_chat_with_valid_data(self, client, auth_headers):
		"""Test updating a chat with valid data."""
		test_uuid = "d99678f7-bb8c-41f4-9726-4722b44a5649"
		payload = {"chat_name": "Updated Chat Name"}

		response = client.post(f"/api/v1/chats/update/{test_uuid}", json=payload, headers=auth_headers)

		# 200 if updated, 404 if absent, 403 if it belongs to another user.
		assert response.status_code in [200, 403, 404]

		if response.status_code == 200:
			data = response.json()
			assert "result" in data
			assert "correlation_id" in data
			assert isinstance(data["result"], list)

	def test_update_chat_with_invalid_uuid(self, client, auth_headers):
		"""Test updating a chat with invalid UUID format."""
		payload = "Updated Name"

		response = client.post("/api/v1/chats/update/invalid-uuid", json=payload, headers=auth_headers)

		assert response.status_code == 422

	def test_update_chat_with_empty_body(self, client, auth_headers):
		"""Test updating a chat with empty request body."""
		test_uuid = "ad8b09b7-1723-4459-ba61-5bf3a2699c11"

		response = client.post(f"/api/v1/chats/update/{test_uuid}", json={}, headers=auth_headers)

		assert response.status_code == 422

	def test_chats_api_response_structure(self, client, auth_headers):
		"""Test that all chat endpoints return consistent response structure."""
		# Test search endpoint response structure
		response = client.get("/api/v1/chats/", headers=auth_headers)
		assert response.status_code == 200
		data = response.json()

		# All endpoints should return this structure
		assert "result" in data
		assert "correlation_id" in data
		assert data["correlation_id"] is not None


@pytest.fixture(scope="function")
def cleanup_test_chats(client, auth_headers):
	"""Fixture that cleans up test chats after each test."""
	# This runs after the test
	yield

	# Clean up any chats with test-related names
	test_name_patterns = [
		"Minimal Chat",
		"Chat without user",
		"Chat with wrong user",
		"Unauthorized Chat",
		"Test Chat for Details",
		"Persona Chat",
		"Persona-Less Chat",
		"Persona Bad Target Chat",
		"Updated Chat Name",
	]

	try:
		# Get all chats (authenticated: only the caller's own chats are visible now)
		response = client.get("/api/v1/chats/?limit=100&offset=0", headers=auth_headers)
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
							client.delete(f"/api/v1/chats/{chat_id}", headers=auth_headers)
							print(f"Cleaned up test chat: {chat_title} (ID: {chat_id})")
						break
	except Exception as e:
		print(f"Error during chat cleanup: {e}")
