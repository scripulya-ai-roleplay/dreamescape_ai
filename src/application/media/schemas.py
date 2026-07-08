from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.domain.models import MediaEntityType


class MediaAssetDTO(BaseModel):
	"""Client-facing representation of a media asset.

	``url`` is computed by the service: a stable public URL for public assets, a
	short-lived presigned URL for private assets, or the legacy ``file_url`` as-is
	for assets that still point at an external location. The object key / bucket
	are intentionally NOT exposed.
	"""

	model_config = ConfigDict(frozen=True)

	id: UUID
	url: str
	content_type: str
	size_bytes: int
	entity_type: MediaEntityType
	entity_id: UUID
	is_public: bool
	created_at: datetime | None = None


class MediaFilterDTO(BaseModel):
	model_config = ConfigDict(frozen=True)

	entity_type: MediaEntityType | None = None
	entity_id: UUID | None = None
	is_public: bool | None = None

	limit: int = Field(default=50, ge=0)
	offset: int = Field(default=0, ge=0)
