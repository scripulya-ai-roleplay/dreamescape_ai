import pytest


@pytest.mark.e2e
class TestAuthLogin:
	"""End-to-end for POST /api/v1/auth/login — the credential exchange that keeps
	the JWT signing key server-side.

	Requires a running backend (BACKEND_HOST) whose DB has been (re)seeded from
	scripts/init.sql, which seeds username 'mobile' with the dev password
	'password'. Run with: pytest -m e2e.
	"""

	def test_login_returns_bearer_token(self, client):
		response = client.post("/api/v1/auth/login", json={"username": "mobile", "password": "password"})

		assert response.status_code == 200
		token = response.json()
		assert token["token_type"] == "bearer"
		assert token["access_token"]

	def test_issued_token_authenticates_on_protected_route(self, client):
		# The token minted by login must satisfy a get_current_user route.
		login = client.post("/api/v1/auth/login", json={"username": "mobile", "password": "password"})
		assert login.status_code == 200
		bearer = login.json()["access_token"]

		# GET /api/v1/chats/ requires a valid bearer (401 without one).
		with_token = client.get("/api/v1/chats/", headers={"Authorization": f"Bearer {bearer}"})
		assert with_token.status_code == 200

		# Sanity: the same route really is auth-gated, so a 200 here means the
		# login token carried weight rather than the route being open.
		without_token = client.get("/api/v1/chats/")
		assert without_token.status_code == 401

	def test_wrong_password_is_401(self, client):
		response = client.post("/api/v1/auth/login", json={"username": "mobile", "password": "definitely-wrong"})

		assert response.status_code == 401
		assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"

	def test_unknown_user_is_same_401_as_wrong_password(self, client):
		# Identical response shape whether the username exists or not — no enumeration.
		unknown = client.post("/api/v1/auth/login", json={"username": "no-such-user", "password": "password"})
		wrong_pw = client.post("/api/v1/auth/login", json={"username": "mobile", "password": "definitely-wrong"})

		assert unknown.status_code == wrong_pw.status_code == 401
		assert unknown.json()["error"]["code"] == wrong_pw.json()["error"]["code"] == "INVALID_CREDENTIALS"
