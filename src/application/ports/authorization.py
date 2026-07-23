"""THIS IS AUTHORIZATION MODULE. NOT AUTHENTICATION"""

import abc
from uuid import UUID

from sqlalchemy import ColumnElement


class IAuthorizationService(abc.ABC):
	@abc.abstractmethod
	def visible_to(self, *, is_public: bool, owner_id: UUID | None, actor_id: UUID | None) -> bool: ...

	@abc.abstractmethod
	def require_visible(self, *, is_public: bool, owner_id: UUID | None, actor_id: UUID | None, noun: str) -> None: ...

	@abc.abstractmethod
	def require_owned(self, *, owner_id: UUID | None, actor_id: UUID, noun: str) -> None: ...


class IVisibilityGateway(abc.ABC):
	@abc.abstractmethod
	def public_or_owned(
		self,
		is_public_col: ColumnElement[bool],
		owner_col: ColumnElement[UUID],
		actor_id: UUID | None,
	) -> ColumnElement[bool]: ...
