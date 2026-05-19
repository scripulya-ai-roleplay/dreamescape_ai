import pytest
import uuid


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
        """Test searching users with pagination parameters."""
        params = {
            "limit": 5,
            "offset": 0
        }
        
        response = client.get("/users/search", params=params)
        
        assert response.status_code == 200
        data = response.json()
        result = data["result"]
        
        assert result["limit"] == 5
        assert result["offset"] == 0
        assert len(result["items"]) <= 5

    def test_search_users_with_username_filter(self, client):
        """Test searching users by username."""
        params = {
            "username": "testuser",
            "limit": 10
        }
        
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
            "role": "user",  # Assuming 'user' is a valid role
            "limit": 10
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
        params = {
            "user_id": test_uuid,
            "limit": 10
        }
        
        response = client.get("/users/search", params=params)
        
        assert response.status_code == 200
        data = response.json()
        result = data["result"]
        
        assert "items" in result
        assert isinstance(result["items"], list)

    def test_search_users_with_invalid_role(self, client):
        """Test searching users with invalid role."""
        params = {
            "role": "invalid_role",
            "limit": 10
        }
        
        response = client.get("/users/search", params=params)
        
        # Should return validation error for invalid enum
        assert response.status_code == 422

    def test_search_users_with_invalid_user_id(self, client):
        """Test searching users with invalid user ID format."""
        params = {
            "user_id": "not-a-uuid",
            "limit": 10
        }
        
        response = client.get("/users/search", params=params)
        
        # Should return validation error for invalid UUID
        assert response.status_code == 422

    def test_search_users_with_negative_limit(self, client):
        """Test searching users with negative limit."""
        params = {
            "limit": -1
        }
        
        response = client.get("/users/search", params=params)
        
        # Should handle negative limit appropriately
        # The behavior depends on implementation, but should not crash
        assert response.status_code in [200, 400, 422]

    def test_search_users_with_large_offset(self, client):
        """Test searching users with very large offset."""
        params = {
            "offset": 10000,
            "limit": 10
        }
        
        response = client.get("/users/search", params=params)
        
        assert response.status_code == 200
        data = response.json()
        result = data["result"]
        
        # Should return empty results for large offset
        assert "items" in result
        assert isinstance(result["items"], list)

    def test_delete_user_with_valid_uuid(self, client):
        """Test deleting a user with valid UUID."""
        test_uuid = str(uuid.uuid4())
        
        response = client.delete(f"/users/{test_uuid}")
        
        # Could be 200 (success), 404 (not found), or 400 (deletion failed)
        # depending on whether user exists and business logic
        assert response.status_code in [200, 404, 400]
        
        if response.status_code == 200:
            data = response.json()
            assert "result" in data
            assert "correlation_id" in data
            assert "message" in data["result"]

    def test_delete_user_with_invalid_uuid(self, client):
        """Test deleting a user with invalid UUID format."""
        invalid_uuid = "not-a-uuid"
        
        response = client.delete(f"/users/{invalid_uuid}")
        
        # Should return validation error for invalid UUID
        assert response.status_code == 422

    def test_delete_user_with_empty_uuid(self, client):
        """Test deleting user with empty UUID path."""
        response = client.delete("/users/")
        
        # Should return 404 or 405 (method not allowed) for missing path parameter
        assert response.status_code in [404, 405]