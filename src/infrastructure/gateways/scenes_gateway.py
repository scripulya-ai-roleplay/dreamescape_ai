import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, delete, func, and_, update, asc, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.application.ports import ISceneGateway, Page
from src.application.scene.schemas import SceneFilterDTO, SceneSortBy, SortOrder
from src.domain.models import Scene
from src.infrastructure.database.models import (
	Scene as SceneModel,
	Character as CharacterModel,
	Chat as ChatModel,
	Message as MessageModel,
)


logger = logging.getLogger(__name__)


@dataclass
class SceneGateway(ISceneGateway):
	session: AsyncSession

	async def get_one(self, uuid: UUID) -> Scene:
		logger.info(f"Getting scene by ID: {uuid}")

		query = select(SceneModel).options(selectinload(SceneModel.characters)).where(SceneModel.id == uuid)

		result = await self.session.execute(query)
		scene_model = result.scalar_one()
		return self._to_domain_scene(scene_model)

	async def delete(self, uuid: UUID):
		logger.info(f"Deleting scene: {uuid}")

		query = delete(SceneModel).where(SceneModel.id == uuid)
		await self.session.execute(query)
		logger.info(f"Successfully deleted scene: {uuid}")

	async def update(self, target_scene_uuid: UUID, new_scene_data: Scene):
		logger.info(f"Updating scene: {target_scene_uuid}")

		# Build update data with proper column names
		update_data = {
			"title": new_scene_data.title,
			"description": new_scene_data.description,
			"background_prompt": new_scene_data.background_prompt,
			"initial_message_text": new_scene_data.initial_message_text,
			"is_public": new_scene_data.is_public,
		}

		if new_scene_data.owner_id is not None:
			update_data["owner_id"] = new_scene_data.owner_id

		query = update(SceneModel).where(SceneModel.id == target_scene_uuid).values(**update_data)
		await self.session.execute(query)
		logger.info(f"Successfully updated scene: {target_scene_uuid}")

	async def search(self, dto: SceneFilterDTO) -> Page[Scene]:
		logger.info(f"Searching scenes with filters: {dto}")

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

		# Build query with joins for character filtering
		query = select(SceneModel).options(selectinload(SceneModel.characters))

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

		if conditions:
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

		if conditions:
			count_query = count_query.where(and_(*conditions))

		if dto.limit:
			query = query.limit(dto.limit)

		if dto.offset:
			query = query.offset(dto.offset)

		count_result = await self.session.execute(count_query)
		total_count = count_result.scalar() or 0

		# Execute query (no pagination parameters in DTO, so return all)
		result = await self.session.execute(query)
		scene_models = result.scalars().all()

		# Convert to domain models
		domain_scenes = [self._to_domain_scene(scene_model) for scene_model in scene_models]

		logger.info(f"Found {len(domain_scenes)} scenes out of {total_count} total")

		return Page[Scene](items=domain_scenes, count=total_count, offset=dto.offset, limit=len(domain_scenes))

	async def create(self, scene: Scene) -> UUID:
		logger.info(f"Creating scene: {scene.title}")

		scene_model = SceneModel(
			title=scene.title,
			description=scene.description,
			background_prompt=scene.background_prompt,
			owner_id=scene.owner_id,
			initial_message_text=scene.initial_message_text,
			is_public=scene.is_public,
		)

		self.session.add(scene_model)
		await self.session.flush()
		await self.session.refresh(scene_model)

		logger.info(f"Successfully created scene with ID: {scene_model.id}")
		return scene_model.id

	def _to_domain_scene(self, scene_model: SceneModel) -> Scene:
		return Scene(
			id=scene_model.id,
			title=scene_model.title,
			description=scene_model.description,
			background_prompt=scene_model.background_prompt,
			owner_id=scene_model.owner_id,
			initial_message_text=scene_model.initial_message_text,
			is_public=scene_model.is_public,
		)
