from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
	"""Body of POST /api/v1/auth/login — the credentials the client exchanges
	for an access token. The signing key never leaves the server; the client only
	ever holds this username/password and the token it receives back."""

	username: str = Field(min_length=1, max_length=100)
	password: str = Field(min_length=1, max_length=1024)


class Token(BaseModel):
	access_token: str
	token_type: str = "bearer"
