import uuid

import pytest


@pytest.mark.e2e
class TestUsersAPI:
	"""End-to-end tests for users API endpoints."""

	def test_search_users_without_filters(self, client):
		"""Test searching users without any filters."""
		response = client.get("/users/search")

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

	def test_search_users_with_pagination(self, client):
		params = {"limit": 5, "offset": 0}

		response = client.get("/users/search", params=params)

		assert response.status_code == 200
		data = response.json()
		result = data["result"]

		assert result["limit"] == 5
		assert result["offset"] == 0
		assert len(result["items"]) <= 5

	def test_search_users_with_username_filter(self, client):
		"""Test searching users by username."""
		params = {"usernames": ["testuser"], "limit": 10}

		response = client.get("/users/search", params=params)

		assert response.status_code == 200
		data = response.json()
		result = data["result"]

		# Should return results (even if empty)
		assert "items" in result
		assert isinstance(result["items"], list)

	def test_search_users_with_role_filter(self, client):
		"""Test searching users by role."""
		params = {
			"roles": ["api"],  # Using valid role enum value
			"limit": 10,
		}

		response = client.get("/users/search", params=params)

		assert response.status_code == 200
		data = response.json()
		result = data["result"]

		assert "items" in result
		assert isinstance(result["items"], list)

	def test_search_users_with_user_id_filter(self, client):
		"""Test searching users by user ID."""
		test_uuid = str(uuid.uuid4())
		params = {"user_ids": [test_uuid], "limit": 10}

		response = client.get("/users/search", params=params)

		assert response.status_code == 200
		data = response.json()
		result = data["result"]

		assert "items" in result
		assert isinstance(result["items"], list)

	def test_search_users_with_invalid_role(self, client):
		"""Test searching users with invalid role."""
		params = {"role": "invalid_role", "limit": 10}

		response = client.get("/users/search", params=params)

		# Should return validation error for invalid enum
		assert response.status_code == 422

	def test_search_users_with_invalid_user_id(self, client):
		"""Test searching users with invalid user ID format."""
		params = {"user_id": "not-a-uuid", "limit": 10}

		response = client.get("/users/search", params=params)

		# Should return validation error for invalid UUID
		assert response.status_code == 422

	def test_search_users_with_negative_limit(self, client):
		"""Test searching users with negative limit."""
		params = {"limit": -1}

		response = client.get("/users/search", params=params)

		# Should handle negative limit appropriately
		# The behavior depends on implementation, but should not crash
		assert response.status_code in [200, 400, 422]

	def test_search_users_with_large_offset(self, client):
		"""Test searching users with very large offset."""
		params = {"offset": 10000, "limit": 10}

		response = client.get("/users/search", params=params)

		assert response.status_code == 200
		data = response.json()
		result = data["result"]

		# Should return empty results for large offset
		assert "items" in result
		assert isinstance(result["items"], list)

	def test_delete_user_without_authentication_returns_401(self, client):
		"""An anonymous caller must not be able to delete a user (auth required)."""
		test_uuid = str(uuid.uuid4())

		response = client.delete(f"/users/{test_uuid}")

		# No Authorization header -> 401 before any deletion can happen.
		assert response.status_code == 401

	def test_delete_user_authenticated_deleting_other_user_returns_403(self, client, auth_headers):
		"""An authenticated user may not delete an account they do not own."""
		# Seeded user that is NOT the account auth_headers authenticates as.
		other_user_id = "f5ac5447-d562-4d7b-91fb-dc4d5bcc4395"

		response = client.delete(f"/users/{other_user_id}", headers=auth_headers)

		# Self-deletion only: deleting another user is forbidden.
		assert response.status_code == 403
		assert "Not allowed to access this user" in response.json().get("detail", "")

	def test_delete_user_with_invalid_uuid(self, client, auth_headers):
		"""Test deleting a user with invalid UUID format."""
		invalid_uuid = "not-a-uuid"

		response = client.delete(f"/users/{invalid_uuid}", headers=auth_headers)

		# Auth resolves before path-param coercion, so authenticate first; the
		# UUID parse then rejects "not-a-uuid" with 422.
		assert response.status_code == 422

	def test_delete_user_with_empty_uuid(self, client):
		"""Test deleting user with empty UUID path."""
		response = client.delete("/users/")

		# Should return 404 or 405 (method not allowed) for missing path parameter
		assert response.status_code in [404, 405]
