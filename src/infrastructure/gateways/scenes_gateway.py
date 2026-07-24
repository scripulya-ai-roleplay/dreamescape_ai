import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, delete, func, and_, update, asc, desc, exists
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.infrastructure.logging.logger import Logger
from src.application.ports.scenes import ISceneGateway
from src.application.ports.authorization import IVisibilityGateway
from src.application.ports.common import Page
from src.application.scene.schemas import SceneFilterDTO, SceneSortBy, SortOrder
from src.domain.models import Scene
from src.infrastructure.database.models import (
	Scene as SceneModel,
	Character as CharacterModel,
	Chat as ChatModel,
	Message as MessageModel,
	scene_likes,
	scene_bookmarks,
	character_scene,
)


@dataclass
class SceneGateway(ISceneGateway):
	session: AsyncSession
	visibility: IVisibilityGateway
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)

	async def get_one(self, uuid: UUID) -> Scene:
		self.logger.info(f"Getting scene by ID: {uuid}")

		query = select(SceneModel).options(selectinload(SceneModel.characters)).where(SceneModel.id == uuid)

		result = await self.session.execute(query)
		scene_model = result.scalar_one()
		return self._to_domain_scene(scene_model)

	async def delete(self, uuid: UUID):
		self.logger.info(f"Deleting scene: {uuid}")

		query = delete(SceneModel).where(SceneModel.id == uuid)
		await self.session.execute(query)
		self.logger.info(f"Successfully deleted scene: {uuid}")

	async def update(self, target_scene_uuid: UUID, new_scene_data: Scene):
		self.logger.info(f"Updating scene: {target_scene_uuid}")

		# Build update data with proper column names
		update_data = {
			"title": new_scene_data.title,
			"description": new_scene_data.description,
			"background_prompt": new_scene_data.background_prompt,
			"is_public": new_scene_data.is_public,
		}

		if new_scene_data.owner_id is not None:
			update_data["owner_id"] = new_scene_data.owner_id

		query = update(SceneModel).where(SceneModel.id == target_scene_uuid).values(**update_data)
		await self.session.execute(query)
		self.logger.info(f"Successfully updated scene: {target_scene_uuid}")

	async def search(self, dto: SceneFilterDTO, actor_id: UUID | None = None) -> Page[Scene]:
		self.logger.info(f"Searching scenes with filters: {dto} (actor={actor_id})")

		# Correlated scalar subqueries counting a scene's chats / messages. They
		# are only referenced when ordering by the matching count, and because
		# they live in ORDER BY (not the SELECT list) the row shape stays a plain
		# SceneModel, so selectinload(characters) and the rest are unaffected.
		chats_count_sq = select(func.count(ChatModel.id)).where(ChatModel.scene_id == SceneModel.id).scalar_subquery()
		messages_count_sq = (
			select(func.count(MessageModel.id))
			.join(ChatModel, ChatModel.id == MessageModel.chat_id)
			.where(ChatModel.scene_id == SceneModel.id)
			.scalar_subquery()
		)
		query = select(
			SceneModel,
			chats_count_sq.label("chats_count"),
			messages_count_sq.label("messages_count"),
		).options(selectinload(SceneModel.characters))

		conditions = []

		if dto.ids:
			conditions.append(SceneModel.id.in_(dto.ids))

		if dto.title:
			conditions.append(SceneModel.title.in_(dto.title))

		if dto.title_search:
			# case-insensitive substring match
			conditions.append(SceneModel.title.ilike(f"%{dto.title_search}%"))

		if dto.owner:
			conditions.append(SceneModel.owner_id.in_(dto.owner))

		# Handle character filtering with subquery
		if dto.characters:
			character_subquery = (
				select(SceneModel.id)
				.select_from(SceneModel)
				.join(SceneModel.characters)
				.where(CharacterModel.id.in_(dto.characters))
			)
			conditions.append(SceneModel.id.in_(character_subquery))

		conditions.append(self.visibility.public_or_owned(SceneModel.is_public, SceneModel.owner_id, actor_id))

		query = query.where(and_(*conditions))

		# Optional ordering by title or by per-scene chat / message counts.
		if dto.sort_by is not None:
			sort_column = {
				SceneSortBy.title: SceneModel.title,
				SceneSortBy.chats_count: chats_count_sq,
				SceneSortBy.messages_count: messages_count_sq,
			}[dto.sort_by]
			order_func = desc if dto.sort_order == SortOrder.desc else asc
			# unique tiebreaker so offset/limit pagination stays stable across pages
			query = query.order_by(order_func(sort_column), SceneModel.id)

		# Get total count
		count_query = select(func.count(SceneModel.id.distinct()))
		if dto.characters:
			count_query = count_query.select_from(SceneModel).join(SceneModel.characters, isouter=True)
		count_query = count_query.where(and_(*conditions))

		if dto.limit:
			query = query.limit(dto.limit)

		if dto.offset:
			query = query.offset(dto.offset)

		count_result = await self.session.execute(count_query)
		total_count = count_result.scalar() or 0

		# Execute query (no pagination parameters in DTO, so return all)
		result = await self.session.execute(query)
		rows = result.all()

		# Convert to domain models
		domain_scenes = [self._to_domain_scene(row[0], row[1] or 0, row[2] or 0) for row in rows]

		self.logger.info(f"Found {len(domain_scenes)} scenes out of {total_count} total")

		return Page[Scene](items=domain_scenes, count=total_count, offset=dto.offset, limit=dto.limit)

	async def create(self, scene: Scene) -> UUID:
		self.logger.info(f"Creating scene: {scene.title}")

		scene_model = SceneModel(
			title=scene.title,
			description=scene.description,
			background_prompt=scene.background_prompt,
			owner_id=scene.owner_id,
			is_public=scene.is_public,
		)

		self.session.add(scene_model)
		await self.session.flush()
		await self.session.refresh(scene_model)

		self.logger.info(f"Successfully created scene with ID: {scene_model.id}")
		return scene_model.id

	async def attach_characters(self, scene_id: UUID, character_ids: list[UUID]) -> None:
		# ON CONFLICT DO NOTHING makes POST /scenes/{id}/characters idempotent:
		# re-adding a character already in the scene is a no-op, and racing
		# attaches can't both fail on the composite PK.
		rows = [{"scene_id": scene_id, "character_id": cid} for cid in character_ids]
		stmt = pg_insert(character_scene).values(rows).on_conflict_do_nothing()
		await self.session.execute(stmt)

	async def set_like(self, scene_id: UUID, user_id: UUID) -> None:
		# ON CONFLICT DO NOTHING keeps POST /like idempotent and concurrency-safe:
		# unlike INSERT ... WHERE NOT EXISTS, two racing likes can't fail on the PK.
		stmt = pg_insert(scene_likes).values(scene_id=scene_id, user_id=user_id).on_conflict_do_nothing()
		await self.session.execute(stmt)

	async def unset_like(self, scene_id: UUID, user_id: UUID) -> None:
		stmt = delete(scene_likes).where(and_(scene_likes.c.scene_id == scene_id, scene_likes.c.user_id == user_id))
		await self.session.execute(stmt)

	async def is_liked(self, scene_id: UUID, user_id: UUID) -> bool:
		stmt = select(exists().where(and_(scene_likes.c.scene_id == scene_id, scene_likes.c.user_id == user_id)))
		return bool(await self.session.scalar(stmt))

	async def count_likes(self, scene_id: UUID) -> int:
		stmt = select(func.count()).select_from(scene_likes).where(scene_likes.c.scene_id == scene_id)
		return int(await self.session.scalar(stmt) or 0)

	async def set_bookmark(self, scene_id: UUID, user_id: UUID) -> None:
		stmt = pg_insert(scene_bookmarks).values(scene_id=scene_id, user_id=user_id).on_conflict_do_nothing()
		await self.session.execute(stmt)

	async def unset_bookmark(self, scene_id: UUID, user_id: UUID) -> None:
		stmt = delete(scene_bookmarks).where(
			and_(scene_bookmarks.c.scene_id == scene_id, scene_bookmarks.c.user_id == user_id)
		)
		await self.session.execute(stmt)

	async def is_bookmarked(self, scene_id: UUID, user_id: UUID) -> bool:
		stmt = select(
			exists().where(and_(scene_bookmarks.c.scene_id == scene_id, scene_bookmarks.c.user_id == user_id))
		)
		return bool(await self.session.scalar(stmt))

	def _to_domain_scene(self, scene_model: SceneModel, chats_count: int = 0, messages_count: int = 0) -> Scene:
		return Scene(
			id=scene_model.id,
			title=scene_model.title,
			description=scene_model.description,
			background_prompt=scene_model.background_prompt,
			owner_id=scene_model.owner_id,
			is_public=scene_model.is_public,
			chats_count=chats_count,
			messages_count=messages_count,
		)
