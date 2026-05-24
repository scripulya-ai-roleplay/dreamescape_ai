import os

import pytest
import requests

from src.infrastructure.auth.jwt_utils import create_test_token


@pytest.fixture(scope="function")
def client():
	session = requests.Session()
	session.timeout = 30.0  # 30 seconds timeout as requested
	session.base_url = os.getenv("BACKEND_HOST", "http://localhost:8000")

	# Create a wrapper class to handle base URL
	class ClientWrapper:
		def __init__(self, session, base_url):
			self.session = session
			self.base_url = base_url

		def get(self, path, **kwargs):
			return self.session.get(f"{self.base_url}{path}", timeout=30.0, **kwargs)

		def post(self, path, **kwargs):
			return self.session.post(f"{self.base_url}{path}", timeout=30.0, **kwargs)

		def delete(self, path, **kwargs):
			return self.session.delete(f"{self.base_url}{path}", timeout=30.0, **kwargs)

		def put(self, path, **kwargs):
			return self.session.put(f"{self.base_url}{path}", timeout=30.0, **kwargs)

	return ClientWrapper(session, "http://localhost:8000")


@pytest.fixture
def auth_headers():
	test_user_id = "5dbdc924-968a-4c50-94a8-44cdd165e460"

	token = create_test_token(test_user_id)

	return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="function")
def cleanup_test_characters(client):
	"""Fixture that cleans up test characters after each test."""
	# This runs after the test
	yield

	# Clean up any characters with test-related names
	test_name_patterns = [
		"Test Character",
		"Minimal Character",
		"Character without",
		"Character with wrong owner",
		"Unauthorized Character",
		"Very long character name",
		"Test Character for Details",
		"Updated Character Name",
		"Updated Name Only",
	]

	try:
		# Get all characters
		response = client.get("/api/v1/characters/?limit=100&offset=0")
		if response.status_code == 200:
			data = response.json()
			characters = data.get("result", {}).get("items", [])

			# Delete characters with test names
			for character in characters:
				character_name = character.get("name", "")
				for pattern in test_name_patterns:
					if pattern in character_name:
						character_id = character.get("id")
						if character_id:
							client.delete(f"/api/v1/characters/{character_id}")
							print(f"Cleaned up test character: {character_name} (ID: {character_id})")
						break
	except Exception as e:
		print(f"Error during character cleanup: {e}")
