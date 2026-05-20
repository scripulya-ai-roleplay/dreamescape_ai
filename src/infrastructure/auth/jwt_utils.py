from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import json
import base64
import hashlib
import hmac
from src.conf import settings


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
	"""Create a simple JWT-like access token with the given data."""
	to_encode = data.copy()

	if expires_delta:
		expire = datetime.utcnow() + expires_delta
	else:
		expire = datetime.utcnow() + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

	to_encode.update({"exp": expire.timestamp()})

	# Create header
	header = {"alg": "HS256", "typ": "JWT"}

	# Encode header and payload
	encoded_header = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
	encoded_payload = base64.urlsafe_b64encode(json.dumps(to_encode).encode()).decode().rstrip("=")

	# Create signature
	message = f"{encoded_header}.{encoded_payload}"
	signature = hmac.new(settings.JWT_SECRET_KEY.encode(), message.encode(), hashlib.sha256).digest()
	encoded_signature = base64.urlsafe_b64encode(signature).decode().rstrip("=")

	return f"{encoded_header}.{encoded_payload}.{encoded_signature}"


def verify_token(token: str) -> Optional[Dict[str, Any]]:
	"""Verify and decode a JWT-like token."""
	try:
		parts = token.split(".")
		if len(parts) != 3:
			return None

		encoded_header, encoded_payload, encoded_signature = parts

		# Verify signature
		message = f"{encoded_header}.{encoded_payload}"
		expected_signature = hmac.new(settings.JWT_SECRET_KEY.encode(), message.encode(), hashlib.sha256).digest()
		expected_encoded_signature = base64.urlsafe_b64encode(expected_signature).decode().rstrip("=")

		if encoded_signature != expected_encoded_signature:
			return None

		# Decode payload
		padded_payload = encoded_payload + "=" * (4 - len(encoded_payload) % 4)
		payload = json.loads(base64.urlsafe_b64decode(padded_payload).decode())

		# Check expiration
		if payload.get("exp", 0) < datetime.utcnow().timestamp():
			return None

		return payload
	except Exception:
		return None


def create_test_token(user_id: str = "test_user") -> str:
	"""Create a test token for testing purposes."""
	return create_access_token({"sub": user_id, "user_id": user_id})
