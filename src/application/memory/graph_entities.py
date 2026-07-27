from typing import Any

from graphiti_core.edges import EntityEdge
from graphiti_core.nodes import EntityNode


class Character(EntityNode):
	role: str | None = None
	relationship_to_user: str | None = None
	current_status: str | None = None


class PlotEvent(EntityNode):
	summary: str | None = None
	outcome: str | None = None


class Promise(EntityNode):
	terms: str | None = None
	state: str | None = None


class Relationship(EntityEdge):
	strength: str | None = None
	attributes: dict[str, Any] = {}


ENTITY_TYPES: dict[str, type[EntityNode]] = {
	"Character": Character,
	"PlotEvent": PlotEvent,
	"Promise": Promise,
}
