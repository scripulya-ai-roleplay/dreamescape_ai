from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import ColumnElement, or_

from src.application.ports.authorization import IVisibilityGateway


@dataclass
class VisibilityGateway(IVisibilityGateway):
	def public_or_owned(
		self,
		is_public_col: ColumnElement[bool],
		owner_col: ColumnElement[UUID],
		actor_id: UUID | None,
	) -> ColumnElement[bool]:
		if actor_id is None:
			return is_public_col.is_(True)
		return or_(is_public_col.is_(True), owner_col == actor_id)
