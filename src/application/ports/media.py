import abc
from typing import BinaryIO
from uuid import UUID

from fastapi import UploadFile
from pydantic import BaseModel, ConfigDict

from src.application.media.schemas import MediaAssetDTO, MediaFilterDTO, MediaUploadDTO
from src.application.ports.common import Page
from src.domain.models import MediaAsset, MediaEntityType


class UploadedImage(BaseModel):
	model_config = ConfigDict(frozen=True)

	content_type: str
	ext: str
	data: bytes
	size: int


class IImageReader(abc.ABC):
	@abc.abstractmethod
	async def read(self, file: UploadFile) -> UploadedImage: ...


class IObjectStorageGateway(abc.ABC):
	@abc.abstractmethod
	async def ensure_buckets(self) -> None: ...

	@abc.abstractmethod
	async def upload(
		self,
		object_key: str,
		data: BinaryIO,
		length: int,
		content_type: str,
		is_public: bool,
	) -> tuple[str, int]: ...

	@abc.abstractmethod
	async def presigned_get_url(self, bucket: str, object_key: str) -> str: ...

	@abc.abstractmethod
	def public_url(self, bucket: str, object_key: str) -> str: ...

	@abc.abstractmethod
	async def delete_object(self, bucket: str, object_key: str) -> None: ...


class IMediaGateway(abc.ABC):
	@abc.abstractmethod
	async def create(self, asset: MediaAsset) -> MediaAsset: ...

	@abc.abstractmethod
	async def get_one(self, media_id: UUID) -> MediaAsset: ...

	@abc.abstractmethod
	async def get_entity_owner(self, entity_type: MediaEntityType, entity_id: UUID) -> UUID | None: ...

	@abc.abstractmethod
	async def get_for_entity(self, entity_type: MediaEntityType, entity_id: UUID) -> list[MediaAsset]: ...

	@abc.abstractmethod
	async def search(self, dto: MediaFilterDTO, actor_id: UUID | None = None) -> Page[MediaAsset]: ...

	@abc.abstractmethod
	async def delete(self, media_id: UUID) -> None: ...


class IMediaService(abc.ABC):
	@abc.abstractmethod
	async def upload(self, dto: MediaUploadDTO) -> MediaAssetDTO: ...

	@abc.abstractmethod
	async def get_one(self, media_id: UUID, actor_id: UUID | None) -> MediaAssetDTO: ...

	@abc.abstractmethod
	async def search(self, dto: MediaFilterDTO, actor_id: UUID | None) -> Page[MediaAssetDTO]: ...

	@abc.abstractmethod
	async def delete(self, media_id: UUID, actor_id: UUID) -> None: ...
