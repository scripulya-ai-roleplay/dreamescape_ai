from typing import Optional, Dict, Any
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer
from src.infrastructure.auth.jwt_utils import verify_token

# Security scheme for HTTP Bearer
oauth2_scheme = HTTPBearer()


async def get_current_user(credentials=Depends(oauth2_scheme)) -> Dict[str, Any]:
	"""Dependency to get current authenticated user from JWT token."""

	payload = verify_token(credentials.credentials)
	if payload is None:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Could not validate credentials",
			headers={"WWW-Authenticate": "Bearer"},
		)

	user_id = payload.get("sub")
	if user_id is None:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Could not validate credentials",
			headers={"WWW-Authenticate": "Bearer"},
		)

	return payload


async def get_optional_user(token: Optional[str] = Depends(HTTPBearer(auto_error=False))) -> Optional[Dict[str, Any]]:
	"""Optional dependency to get current user - returns None if no valid token."""
	if not token:
		return None

	payload = verify_token(token)
	return payload
