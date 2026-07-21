import pytest


@pytest.mark.e2e
class TestAuthLogin:
	def test_login_returns_bearer_token(self, client):
		response = client.post("/api/v1/auth/login", json={"username": "mobile", "password": "password"})

		assert response.status_code == 200
		token = response.json()
		assert token["token_type"] == "bearer"
		assert token["access_token"]

	def test_issued_token_authenticates_on_protected_route(self, client):
		login = client.post("/api/v1/auth/login", json={"username": "mobile", "password": "password"})
		assert login.status_code == 200
		bearer = login.json()["access_token"]

		with_token = client.get("/api/v1/chats/", headers={"Authorization": f"Bearer {bearer}"})
		assert with_token.status_code == 200

		without_token = client.get("/api/v1/chats/")
		assert without_token.status_code == 401

	def test_wrong_password_is_401(self, client):
		response = client.post("/api/v1/auth/login", json={"username": "mobile", "password": "definitely-wrong"})

		assert response.status_code == 401
		assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"

	def test_unknown_user_is_same_401_as_wrong_password(self, client):
		unknown = client.post("/api/v1/auth/login", json={"username": "no-such-user", "password": "password"})
		wrong_pw = client.post("/api/v1/auth/login", json={"username": "mobile", "password": "definitely-wrong"})

		assert unknown.status_code == wrong_pw.status_code == 401
		assert unknown.json()["error"]["code"] == wrong_pw.json()["error"]["code"] == "INVALID_CREDENTIALS"
