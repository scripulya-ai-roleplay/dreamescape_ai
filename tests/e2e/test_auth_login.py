import datetime as dt

import jwt
import pytest

from src.conf import settings


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

	# Token-rejection edge cases through the real route dependency (get_current_user ->
	# JWTService.verify_token). Any decode/signature/expiry failure must surface as 401,
	# never 500 — these guard the verifier path that the happy-path login test doesn't.
	def test_malformed_token_rejected_401(self, client):
		response = client.get("/api/v1/chats/", headers={"Authorization": "Bearer not.a.valid.token"})
		assert response.status_code == 401

	def test_tampered_signature_rejected_401(self, client):
		login = client.post("/api/v1/auth/login", json={"username": "mobile", "password": "password"})
		assert login.status_code == 200
		token = login.json()["access_token"]
		# Flip the FIRST signature char: all 6 of its bits are significant. The LAST
		# char's low bits are non-significant base64url padding (32-byte HMAC -> 43
		# chars), so flipping only it can decode to the same signature and still verify.
		header_b64, payload_b64, sig_b64 = token.split(".")
		sig_b64 = ("X" if sig_b64[0] != "X" else "Y") + sig_b64[1:]
		tampered = f"{header_b64}.{payload_b64}.{sig_b64}"

		response = client.get("/api/v1/chats/", headers={"Authorization": f"Bearer {tampered}"})
		assert response.status_code == 401

	def test_expired_token_rejected_401(self, client):
		# Mint a token exactly as JWTService.create_token does, but with an expiry in
		# the past. The app and test process share the same JWT_SECRET_KEY (no CI
		# override), so the signature verifies and only the exp check fails -> 401.
		expired = jwt.encode(
			{
				"sub": "5dbdc924-968a-4c50-94a8-44cdd165e460",
				"user_id": "5dbdc924-968a-4c50-94a8-44cdd165e460",
				"role": "api",
				"exp": dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1),
			},
			settings.JWT_SECRET_KEY,
			algorithm=settings.JWT_ALGORITHM,
		)

		response = client.get("/api/v1/chats/", headers={"Authorization": f"Bearer {expired}"})
		assert response.status_code == 401
