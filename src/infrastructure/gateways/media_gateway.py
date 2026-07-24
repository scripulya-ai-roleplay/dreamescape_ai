import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.media.schemas import MediaFilterDTO
from src.application.ports.authorization import IVisibilityGateway
from src.application.ports.common import Page
from src.application.ports.media import IMediaGateway
from src.domain.models import MediaAsset, MediaEntityType
from src.infrastructure.database.models import (
	Character as CharacterModel,
)
from src.infrastructure.database.models import (
	MediaAsset as MediaAssetModel,
)
from src.infrastructure.database.models import (
	Scene as SceneModel,
)
from src.infrastructure.database.models import (
	User as UserModel,
)
from src.infrastructure.logging.logger import Logger

# Maps an entity kind to (table, owner-column) for ownership checks. Characters
# and scenes are owned via owner_id; a user "owns" itself (its own id).
_ENTITY_OWNER_COLUMN: dict[MediaEntityType, tuple[type, object]] = {
	MediaEntityType.CHARACTER: (CharacterModel, CharacterModel.owner_id),
	MediaEntityType.SCENE: (SceneModel, SceneModel.owner_id),
	MediaEntityType.USER: (UserModel, UserModel.id),
}


@dataclass
class MediaGateway(IMediaGateway):
	session: AsyncSession
	visibility: IVisibilityGateway
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)

	async def create(self, asset: MediaAsset) -> MediaAsset:
		self.logger.info("Creating media asset for %s/%s", asset.entity_type, asset.entity_id)

		model = MediaAssetModel(
			object_key=asset.object_key,
			bucket=asset.bucket,
			file_url=asset.file_url,
			content_type=asset.content_type,
			size_bytes=asset.size_bytes,
			entity_type=asset.entity_type.value,
			entity_id=asset.entity_id,
			is_public=asset.is_public,
			owner_id=asset.owner_id,
		)
		self.session.add(model)
		await self.session.flush()
		await self.session.refresh(model)

		self.logger.info("Created media asset with ID: %s", model.id)
		return self._to_domain(model)

	async def get_one(self, media_id: UUID) -> MediaAsset:
		self.logger.info("Getting media asset: %s", media_id)

		result = await self.session.execute(select(MediaAssetModel).where(MediaAssetModel.id == media_id))
		model = result.scalar_one()
		return self._to_domain(model)

	async def get_entity_owner(self, entity_type: MediaEntityType, entity_id: UUID) -> UUID | None:
		self.logger.info("Resolving owner of %s/%s", entity_type, entity_id)

		mapping = _ENTITY_OWNER_COLUMN.get(entity_type)
		if mapping is None:
			return None
		model, owner_col = mapping
		result = await self.session.execute(select(owner_col).where(model.id == entity_id))
		return result.scalar_one_or_none()

	async def get_for_entity(self, entity_type: MediaEntityType, entity_id: UUID) -> list[MediaAsset]:
		self.logger.info("Getting media for %s/%s", entity_type, entity_id)

		result = await self.session.execute(
			select(MediaAssetModel).where(
				MediaAssetModel.entity_type == entity_type.value,
				MediaAssetModel.entity_id == entity_id,
			)
		)
		return [self._to_domain(model) for model in result.scalars().all()]

	async def search(self, dto: MediaFilterDTO, actor_id: UUID | None = None) -> Page[MediaAsset]:
		self.logger.info("Searching media with filters: %s (actor=%s)", dto, actor_id)

		conditions = []
		if dto.entity_type is not None:
			conditions.append(MediaAssetModel.entity_type == dto.entity_type.value)
		if dto.entity_id is not None:
			conditions.append(MediaAssetModel.entity_id == dto.entity_id)
		if dto.is_public is not None:
			conditions.append(MediaAssetModel.is_public == dto.is_public)

		conditions.append(
			self.visibility.public_or_owned(MediaAssetModel.is_public, MediaAssetModel.owner_id, actor_id)
		)

		where_clause = and_(*conditions)

		count_query = select(func.count(MediaAssetModel.id)).where(where_clause)
		total = (await self.session.execute(count_query)).scalar() or 0

		# limit==0 means "no items": skip the items query so we never run an
		# unbounded SELECT. The total is still reported for pagination.
		if dto.limit == 0:
			self.logger.info("limit=0 -> returning no items out of %s total", total)
			return Page[MediaAsset](items=[], count=total, offset=dto.offset, limit=dto.limit)

		query = select(MediaAssetModel).where(where_clause).limit(dto.limit)
		if dto.offset > 0:
			query = query.offset(dto.offset)

		result = await self.session.execute(query)
		items = [self._to_domain(model) for model in result.scalars().all()]

		self.logger.info("Found %s media assets out of %s total", len(items), total)
		return Page[MediaAsset](items=items, count=total, offset=dto.offset, limit=dto.limit)

	async def delete(self, media_id: UUID) -> None:
		self.logger.info("Deleting media asset: %s", media_id)
		await self.session.execute(delete(MediaAssetModel).where(MediaAssetModel.id == media_id))
		self.logger.info("Deleted media asset: %s", media_id)

	def _to_domain(self, model: MediaAssetModel) -> MediaAsset:
		return MediaAsset(
			id=model.id,
			object_key=model.object_key,
			bucket=model.bucket,
			file_url=model.file_url,
			content_type=model.content_type,
			size_bytes=model.size_bytes,
			entity_type=MediaEntityType(model.entity_type),
			entity_id=model.entity_id,
			is_public=model.is_public,
			owner_id=model.owner_id,
			created_at=model.created_at,
		)
