from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException
from starlette import status

from src.application.ports import IAuthorizationService


@dataclass
class AuthorizationService(IAuthorizationService):
	def visible_to(self, *, is_public: bool, owner_id: UUID | None, actor_id: UUID | None) -> bool:
		return is_public or (owner_id is not None and owner_id == actor_id)

	def require_visible(self, *, is_public: bool, owner_id: UUID | None, actor_id: UUID | None, noun: str) -> None:
		if self.visible_to(is_public=is_public, owner_id=owner_id, actor_id=actor_id):
			return
		if actor_id is None:
			raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
		raise HTTPException(status.HTTP_403_FORBIDDEN, detail=f"Not allowed to access this {noun}")

	def require_owned(self, *, owner_id: UUID | None, actor_id: UUID, noun: str) -> None:
		if owner_id != actor_id:
			raise HTTPException(status.HTTP_403_FORBIDDEN, detail=f"Not allowed to access this {noun}")
