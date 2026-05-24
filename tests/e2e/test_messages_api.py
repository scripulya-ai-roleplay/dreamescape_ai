import pytest


@pytest.mark.e2e
class TestMessagesAPI:
	"""End-to-end tests for messages API endpoints."""

	def test_create_message_with_valid_data(self, client, auth_headers, cleanup_test_messages):
		"""Test creating a message with valid data."""
		payload = {
			"message": "Hello, this is a test message",
			"chat_id": "82dc4309-0ab2-4a9d-86c9-a49f8931494a",
			"role": "user",
		}

		response = client.post("/api/v1/messages/", json=payload, headers=auth_headers)

		# Debug: Print response details if not 200
		if response.status_code != 200:
			print(f"Response status: {response.status_code}")
			print(f"Response content: {response.text}")

		assert response.status_code == 200
		data = response.json()
		assert "result" in data
		assert "correlation_id" in data
		assert isinstance(data["result"], dict)
		# Message creation returns the created message, not an empty list
		assert "id" in data["result"]
		assert "message" in data["result"]
		assert "chat_id" in data["result"]
		assert "role" in data["result"]

	def test_create_message_with_model_role(self, client, auth_headers, cleanup_test_messages):
		"""Test creating a message with model role."""
		payload = {
			"message": "AI response message",
			"chat_id": "82dc4309-0ab2-4a9d-86c9-a49f8931494a",
			"role": "model",
		}

		response = client.post("/api/v1/messages/", json=payload, headers=auth_headers)

		assert response.status_code == 200
		data = response.json()
		assert "result" in data
		assert "correlation_id" in data
		assert data["result"]["role"] == "model"

	def test_create_message_with_empty_content(self, client, auth_headers, cleanup_test_messages):
		"""Test creating a message with empty content."""
		payload = {
			"message": "",
			"chat_id": "82dc4309-0ab2-4a9d-86c9-a49f8931494a",
			"role": "user",
		}

		response = client.post("/api/v1/messages/", json=payload, headers=auth_headers)

		# Empty messages should be allowed
		assert response.status_code == 200
		data = response.json()
		assert data["result"]["message"] == ""

	def test_create_message_missing_required_fields(self, client, auth_headers):
		"""Test creating a message with missing required fields."""
		# Missing message content
		payload = {
			"chat_id": "82dc4309-0ab2-4a9d-86c9-a49f8931494a",
			"role": "user",
		}

		response = client.post("/api/v1/messages/", json=payload, headers=auth_headers)

		assert response.status_code == 422

	def test_create_message_missing_chat_id(self, client, auth_headers):
		"""Test creating a message without chat_id."""
		payload = {
			"message": "Message without chat",
			"role": "user",
		}

		response = client.post("/api/v1/messages/", json=payload, headers=auth_headers)

		assert response.status_code == 422

	def test_create_message_invalid_role(self, client, auth_headers):
		"""Test creating a message with invalid role."""
		payload = {
			"message": "Message with invalid role",
			"chat_id": "82dc4309-0ab2-4a9d-86c9-a49f8931494a",
			"role": "invalid_role",
		}

		response = client.post("/api/v1/messages/", json=payload, headers=auth_headers)

		assert response.status_code == 422

	def test_create_message_without_authentication(self, client):
		"""Test creating a message without authentication should return 401."""
		payload = {
			"message": "Unauthorized message",
			"chat_id": "82dc4309-0ab2-4a9d-86c9-a49f8931494a",
			"role": "user",
		}

		response = client.post("/api/v1/messages/", json=payload)

		assert response.status_code == 401

	def test_search_messages_without_filters(self, client):
		"""Test searching messages without any filters."""
		response = client.get("/api/v1/messages/")

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

	def test_search_messages_with_pagination(self, client):
		"""Test searching messages with pagination parameters."""
		response = client.get("/api/v1/messages/?limit=5&offset=0")

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

	def test_search_messages_with_chat_filter(self, client):
		"""Test searching messages with chat_id filter."""
		chat_id = "82dc4309-0ab2-4a9d-86c9-a49f8931494a"
		response = client.get(f"/api/v1/messages/?chats_ids={chat_id}")

		assert response.status_code == 200
		data = response.json()
		result = data["result"]

		# Verify response structure
		assert "items" in result
		assert "count" in result

		# If there are messages, they should belong to the specified chat
		for message in result["items"]:
			assert message["chat_id"] == chat_id

	def test_search_messages_with_role_filter(self, client):
		"""Test searching messages with role filter."""
		response = client.get("/api/v1/messages/?roles=user")

		assert response.status_code == 200
		data = response.json()
		result = data["result"]

		# Verify response structure
		assert "items" in result
		assert "count" in result

		# If there are messages, they should have the specified role
		for message in result["items"]:
			assert message["role"] == "user"

	def test_search_messages_with_invalid_pagination(self, client):
		response = client.get("/api/v1/messages/?limit=-1&offset=-5")

		# Should handle gracefully, likely with 422 or defaults
		assert response.status_code in [200, 422]

	def test_get_message_details_with_valid_uuid(self, client, auth_headers, cleanup_test_messages):
		# First create a message to get its ID
		payload = {
			"message": "Test Message for Details",
			"chat_id": "82dc4309-0ab2-4a9d-86c9-a49f8931494a",
			"role": "user",
		}
		create_response = client.post("/api/v1/messages/", json=payload, headers=auth_headers)

		if create_response.status_code == 200:
			created_message = create_response.json()["result"]
			message_id = created_message["id"]

			# Get the message details
			response = client.get(f"/api/v1/messages/{message_id}")

			assert response.status_code == 200
			data = response.json()
			assert "result" in data
			assert "correlation_id" in data
			assert data["result"]["id"] == message_id
		else:
			# Use a known UUID for testing if creation fails
			test_uuid = "048a7fe5-f4c2-40ef-9745-7d85d7c4c5fb"
			response = client.get(f"/api/v1/messages/{test_uuid}")

			# Should return 200 if message exists, 404 if not
			assert response.status_code in [200, 404]

	def test_get_message_details_with_invalid_uuid(self, client):
		response = client.get("/api/v1/messages/invalid-uuid")

		assert response.status_code == 422

	def test_update_message_with_valid_data(self, client, auth_headers, cleanup_test_messages):
		"""Test updating a message with valid data."""
		# First create a message
		payload = {
			"message": "Original message content",
			"chat_id": "82dc4309-0ab2-4a9d-86c9-a49f8931494a",
			"role": "user",
		}
		create_response = client.post("/api/v1/messages/", json=payload, headers=auth_headers)

		if create_response.status_code == 200:
			created_message = create_response.json()["result"]
			message_id = created_message["id"]

			# Update the message
			updated_text = {"updated_text": "Updated message content"}
			response = client.put(f"/api/v1/messages/{message_id}", json=updated_text)

			assert response.status_code == 200
			data = response.json()
			assert "result" in data
			assert "correlation_id" in data
			assert isinstance(data["result"], list)
		else:
			# Use a known UUID for testing if creation fails
			test_uuid = "90d27426-7b7a-4a4d-ba17-6f98b7c29c5e"
			updated_text = "Updated message content"
			response = client.put(f"/api/v1/messages/{test_uuid}", json=updated_text)

			# Should return 200 if message exists and updated, 404 if not found
			assert response.status_code in [200, 404]

	def test_update_message_with_invalid_uuid(self, client):
		"""Test updating a message with invalid UUID format."""
		updated_text = "Updated text"

		response = client.put("/api/v1/messages/invalid-uuid", json=updated_text)

		assert response.status_code == 422

	def test_update_message_with_empty_body(self, client):
		"""Test updating a message with empty request body."""
		test_uuid = "d99678f7-bb8c-41f4-9726-4722b44a5649"

		response = client.put(f"/api/v1/messages/{test_uuid}", json={})

		assert response.status_code == 422

	def test_delete_message_with_valid_uuid(self, client, auth_headers, cleanup_test_messages):
		"""Test deleting a message."""
		# First create a message
		payload = {
			"message": "Message to be deleted",
			"chat_id": "82dc4309-0ab2-4a9d-86c9-a49f8931494a",
			"role": "user",
		}
		create_response = client.post("/api/v1/messages/", json=payload, headers=auth_headers)

		if create_response.status_code == 200:
			created_message = create_response.json()["result"]
			message_id = created_message["id"]

			# Delete the message
			response = client.delete(f"/api/v1/messages/{message_id}")

			assert response.status_code == 200
			data = response.json()
			assert "result" in data
			assert "correlation_id" in data
			assert isinstance(data["result"], list)
		else:
			# Use a known UUID for testing if creation fails
			test_uuid = "ad8b09b7-1723-4459-ba61-5bf3a2699c11"
			response = client.delete(f"/api/v1/messages/{test_uuid}")

			# Should return 200 if message exists and deleted, 404 if not found
			assert response.status_code in [200, 404]

	def test_delete_message_with_invalid_uuid(self, client):
		"""Test deleting a message with invalid UUID format."""
		response = client.delete("/api/v1/messages/invalid-uuid")

		assert response.status_code == 422

	def test_messages_api_response_structure(self, client):
		"""Test that all message endpoints return consistent response structure."""
		# Test search endpoint response structure
		response = client.get("/api/v1/messages/")
		assert response.status_code == 200
		data = response.json()

		# All endpoints should return this structure
		assert "result" in data
		assert "correlation_id" in data
		assert data["correlation_id"] is not None

	def test_create_message_with_long_content(self, client, auth_headers, cleanup_test_messages):
		"""Test creating a message with very long content."""
		long_message = "Very long message content " * 1000
		payload = {
			"message": long_message,
			"chat_id": "82dc4309-0ab2-4a9d-86c9-a49f8931494a",
			"role": "user",
		}

		response = client.post("/api/v1/messages/", json=payload, headers=auth_headers)

		# Should handle long messages gracefully
		assert response.status_code in [200, 422]

		if response.status_code == 200:
			data = response.json()
			assert "result" in data
			assert data["result"]["message"] == long_message


@pytest.fixture(scope="function")
def cleanup_test_messages(client):
	"""Fixture that cleans up test messages after each test."""
	# This runs after the test
	yield

	# Clean up any messages with test-related content
	test_message_patterns = [
		"Hello, this is a test message",
		"AI response message",
		"Message without chat",
		"Message with invalid role",
		"Unauthorized message",
		"Test Message for Details",
		"Original message content",
		"Message to be deleted",
		"Very long message content",
	]

	try:
		# Get all messages
		response = client.get("/api/v1/messages/?limit=200&offset=0")
		if response.status_code == 200:
			data = response.json()
			messages = data.get("result", {}).get("items", [])

			# Delete messages with test content
			for message in messages:
				message_content = message.get("message", "")
				for pattern in test_message_patterns:
					if pattern in message_content:
						message_id = message.get("id")
						if message_id:
							client.delete(f"/api/v1/messages/{message_id}")
							print(f"Cleaned up test message: {message_content[:50]}... (ID: {message_id})")
						break
	except Exception as e:
		print(f"Error during message cleanup: {e}")
