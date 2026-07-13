import io
import logging
from dataclasses import dataclass
from uuid import UUID, uuid4

from fastapi import HTTPException
from starlette import status

from src.application.media.schemas import MediaAssetDTO, MediaFilterDTO, MediaUploadDTO
from src.application.ports import (
	IImageReader,
	IObjectStorageGateway,
	IMediaGateway,
	IMediaService,
	IUnitOfWork,
	Page,
)
from src.domain.models import MediaAsset

logger = logging.getLogger(__name__)


@dataclass
class MediaService(IMediaService):
	storage: IObjectStorageGateway
	gateway: IMediaGateway
	reader: IImageReader
	uow: IUnitOfWork

	async def upload(self, dto: MediaUploadDTO) -> MediaAssetDTO:
		# Authorize first: the uploader must own the target entity. Fails fast
		# before reading the file, so an attacker can't attach media to another
		# user's character/scene (or to a fabricated UUID). 403 in both the
		# not-owned and not-found cases to avoid leaking which entities exist.
		entity_owner = await self.gateway.get_entity_owner(dto.entity_type, dto.entity_id)
		if entity_owner is None or entity_owner != dto.owner_id:
			logger.warning(
				"Rejected upload: user %s may not attach media to %s/%s (owner=%s)",
				dto.owner_id,
				dto.entity_type,
				dto.entity_id,
				entity_owner,
			)
			raise HTTPException(
				status_code=status.HTTP_403_FORBIDDEN,
				detail="Not allowed to attach media to this entity",
			)

		# Read + validate the uploaded image (size cap + content-type sniff).
		# Raises UnsupportedImageTypeException (415) / ImageTooLargeException (413),
		# which the global exception handler maps to HTTP responses.
		image = await self.reader.read(dto.file)

		object_key = f"{dto.entity_type.value}/{uuid4().hex}.{image.ext}"

		await self.storage.ensure_buckets()
		bucket, size = await self.storage.upload(
			object_key=object_key,
			data=io.BytesIO(image.data),
			length=image.size,
			content_type=image.content_type,
			is_public=dto.is_public,
		)

		asset = MediaAsset(
			object_key=object_key,
			bucket=bucket,
			file_url=None,
			content_type=image.content_type,
			size_bytes=size,
			entity_type=dto.entity_type,
			entity_id=dto.entity_id,
			is_public=dto.is_public,
			owner_id=dto.owner_id,
		)

		# The object is already in storage; if the DB write fails, reclaim it so
		# it can't become an unreclaimable orphan. Mirrors the delete ordering.
		try:
			async with self.uow:
				asset = await self.gateway.create(asset)
		except Exception:
			try:
				await self.storage.delete_object(bucket, object_key)
			except Exception:
				logger.exception("Failed to clean up orphaned object %s/%s", bucket, object_key)
			raise

		logger.info("Uploaded media %s for %s/%s", asset.id, dto.entity_type, dto.entity_id)
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
