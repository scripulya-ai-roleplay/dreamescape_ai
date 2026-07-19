from datetime import datetime
from uuid import UUID

from fastapi import UploadFile
from pydantic import BaseModel, ConfigDict, Field

from src.domain.models import MediaEntityType


class MediaAssetDTO(BaseModel):
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
	model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

	file: UploadFile
	entity_type: MediaEntityType
	entity_id: UUID
	is_public: bool = False
	owner_id: UUID
