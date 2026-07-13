from datetime import datetime
from uuid import UUID

from fastapi import UploadFile
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

	# limit==0 means "no items" (the search returns an empty page, not the whole
	# table); capped to keep a single request from dumping the entire result set.
	limit: int = Field(default=50, ge=0, le=200)
	offset: int = Field(default=0, ge=0)


class MediaUploadDTO(BaseModel):
	"""Application-level input for a single media upload.

	Assembled by the controller from the multipart form plus the authenticated
	user, then consumed by the service as a single argument. ``owner_id`` is
	authoritative (sourced from the auth token, never the client body). This DTO
	is NOT parsed straight off the request: file uploads require multipart, which
	FastAPI only advertises for a direct UploadFile parameter, so the controller
	groups the form fields via the ``upload_form`` dependency and builds this.
	"""

	model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

	file: UploadFile
	entity_type: MediaEntityType
	entity_id: UUID
	is_public: bool = False
	owner_id: UUID
