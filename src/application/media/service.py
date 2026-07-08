import io
import logging
from dataclasses import dataclass
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile
from starlette import status

from src.application.media.schemas import MediaAssetDTO, MediaFilterDTO
from src.application.ports import IObjectStorageGateway, IMediaGateway, IMediaService, IUnitOfWork, Page
from src.conf import settings
from src.domain.models import MediaAsset, MediaEntityType

logger = logging.getLogger(__name__)

# Image content types accepted on upload. The extension is derived from the
# content type (not the client-supplied filename) and doubles as the allowlist.
_CONTENT_TYPE_EXT: dict[str, str] = {
	"image/png": "png",
	"image/jpeg": "jpg",
	"image/webp": "webp",
	"image/gif": "gif",
	"image/svg+xml": "svg",
	"image/bmp": "bmp",
	"image/tiff": "tiff",
	"image/x-icon": "ico",
}

_READ_CHUNK = 64 * 1024


@dataclass
class MediaService(IMediaService):
	storage: IObjectStorageGateway
	gateway: IMediaGateway
	uow: IUnitOfWork

	async def upload(
		self,
		file: UploadFile,
		entity_type: MediaEntityType,
		entity_id: UUID,
		is_public: bool,
		owner_id: UUID,
	) -> MediaAssetDTO:
		content_type = (file.content_type or "").lower()
		if content_type not in _CONTENT_TYPE_EXT:
			logger.warning("Rejected upload: unsupported content_type=%s", content_type)
			raise HTTPException(
				status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
				detail=f"Unsupported image content type: {content_type or 'unknown'}",
			)

		# Stream into memory with a hard cap so a huge upload cannot OOM the process.
		max_bytes = settings.MEDIA_MAX_UPLOAD_BYTES
		buf = bytearray()
		while True:
			chunk = await file.read(_READ_CHUNK)
			if not chunk:
				break
			buf += chunk
			if len(buf) > max_bytes:
				logger.warning("Rejected upload: size exceeds %s bytes", max_bytes)
				raise HTTPException(
					status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
					detail=f"Image exceeds the {max_bytes}-byte limit",
				)

		ext = _CONTENT_TYPE_EXT[content_type]
		object_key = f"{entity_type.value}/{uuid4().hex}.{ext}"

		await self.storage.ensure_buckets()
		bucket, size = await self.storage.upload(
			object_key=object_key,
			data=io.BytesIO(bytes(buf)),
			length=len(buf),
			content_type=content_type,
			is_public=is_public,
		)

		asset = MediaAsset(
			object_key=object_key,
			bucket=bucket,
			file_url=None,
			content_type=content_type,
			size_bytes=size,
			entity_type=entity_type,
			entity_id=entity_id,
			is_public=is_public,
			owner_id=owner_id,
		)

		async with self.uow:
			asset = await self.gateway.create(asset)

		logger.info("Uploaded media %s for %s/%s", asset.id, entity_type, entity_id)
		return await self._to_dto(asset)

	async def get_one(self, media_id: UUID, actor_id: UUID | None) -> MediaAssetDTO:
		asset = await self.gateway.get_one(media_id)  # NoResultFound -> 404 (global handler)

		if not asset.is_public:
			if actor_id is None:
				raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
			if asset.owner_id is None or actor_id != asset.owner_id:
				raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to view this media")

		return await self._to_dto(asset)

	async def search(self, dto: MediaFilterDTO, actor_id: UUID | None) -> Page[MediaAssetDTO]:
		page = await self.gateway.search(dto, actor_id=actor_id)
		return Page[MediaAssetDTO](
			items=[await self._to_dto(item) for item in page.items],
			count=page.count,
			offset=page.offset,
			limit=page.limit,
		)

	async def delete(self, media_id: UUID, actor_id: UUID) -> None:
		asset = await self.gateway.get_one(media_id)  # NoResultFound -> 404

		if asset.owner_id is None or actor_id != asset.owner_id:
			raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to delete this media")

		async with self.uow:
			# Best-effort object removal: a failure here must not keep the row alive.
			if asset.bucket and asset.object_key:
				try:
					await self.storage.delete_object(asset.bucket, asset.object_key)
				except Exception:
					logger.exception("Failed to delete object %s/%s", asset.bucket, asset.object_key)
			await self.gateway.delete(media_id)

	async def _url_for(self, asset: MediaAsset) -> str:
		# Legacy / external URL: return as-is.
		if asset.file_url:
			return asset.file_url
		if not (asset.bucket and asset.object_key):
			logger.warning("Media %s has neither file_url nor object location", asset.id)
			return ""
		if asset.is_public:
			return self.storage.public_url(asset.bucket, asset.object_key)
		return await self.storage.presigned_get_url(asset.bucket, asset.object_key)

	async def _to_dto(self, asset: MediaAsset) -> MediaAssetDTO:
		return MediaAssetDTO(
			id=asset.id,  # type: ignore[arg-type]
			url=await self._url_for(asset),
			content_type=asset.content_type,
			size_bytes=asset.size_bytes,
			entity_type=asset.entity_type,
			entity_id=asset.entity_id,
			is_public=asset.is_public,
			created_at=asset.created_at,
		)
