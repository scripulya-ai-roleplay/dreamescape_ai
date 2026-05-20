from pydantic import BaseModel


class LoginRequest(BaseModel):
	"""Request model for user login."""

	username: str
	password: str


class TokenResponse(BaseModel):
	"""Response model for token generation."""

	access_token: str
	token_type: str = "bearer"


class UserInfo(BaseModel):
	"""Model representing user information."""

	user_id: str
	username: str


class AuthenticatedUser(BaseModel):
	"""Model for authenticated user from token payload."""

	sub: str
	user_id: str
	exp: float

	@property
	def username(self) -> str:
		"""Get username from user_id."""
		return self.user_id
