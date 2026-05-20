import pytest


@pytest.mark.e2e
class TestChatsAPI:
	"""End-to-end tests for chats API endpoints."""

	def test_send_message_with_testing_mock(self, client):
		"""Test sending a message with testing_mock LLM model."""
		payload = {"message": "Hello, how are you?", "llm_model": "testing_mock"}

		response = client.post("/api/v1/chats/", json=payload)

		assert response.status_code == 200
		data = response.json()
		assert "result" in data
		assert "text" in data["result"]
		assert isinstance(data["result"]["text"], str)
		assert len(data["result"]["text"]) > 0

	def test_send_message_with_invalid_model(self, client):
		"""Test sending a message with invalid LLM model."""
		payload = {"message": "Hello", "llm_model": "invalid_model"}

		response = client.post("/api/v1/chats/", json=payload)

		# Should return validation error for invalid enum value
		assert response.status_code == 422

	def test_send_message_with_empty_message(self, client):
		"""Test sending empty message."""
		payload = {"message": "", "llm_model": "testing_mock"}

		response = client.post("/api/v1/chats/", json=payload)

		# Should still work with empty message
		assert response.status_code == 200
		data = response.json()
		assert "text" in data

	def test_send_message_missing_fields(self, client):
		"""Test sending message with missing required fields."""
		# Missing llm_model
		payload = {"message": "Hello"}

		response = client.post("/api/v1/chats/", json=payload)

		# Should return validation error
		assert response.status_code == 422

	def test_send_message_with_long_message(self, client):
		"""Test sending a very long message."""
		long_message = "Hello " * 1000  # Very long message
		payload = {"message": long_message, "llm_model": "testing_mock"}

		response = client.post("/api/v1/chats/", json=payload)

		assert response.status_code == 200
		data = response.json()
		assert "text" in data
		assert isinstance(data["text"], str)
