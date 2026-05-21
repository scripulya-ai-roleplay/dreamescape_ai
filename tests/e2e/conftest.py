import os

import pytest
import requests


@pytest.fixture(scope="function")
def client():
	"""HTTP client for e2e tests with 30-second timeout."""
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

	return ClientWrapper(session, "http://localhost:8000")


@pytest.fixture
def auth_headers():
	"""Authentication headers with JWT token for testing."""
	from src.infrastructure.auth.jwt_utils import create_test_token

	# Use a test user ID from init.sql (admin_test)
	test_user_id = "550e8400-e29b-41d4-a716-446655440000"

	# Create a proper test token using the jwt_utils function
	token = create_test_token(test_user_id)

	return {"Authorization": f"Bearer {token}"}
