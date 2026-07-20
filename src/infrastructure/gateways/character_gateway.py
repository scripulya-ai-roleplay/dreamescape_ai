import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, delete, func, and_, update, exists
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.infrastructure.logging.logger import Logger
from src.application.character.schemas import CharacterFilterDTO
from src.application.ports import ICharacterGateway, IVisibilityGateway, Page
from src.domain.models import Character
from src.infrastructure.database.models import (
	Character as CharacterModel,
	Scene as SceneModel,
	character_likes,
	character_bookmarks,
)


@dataclass
class CharacterGateway(ICharacterGateway):
	session: AsyncSession
	visibility: IVisibilityGateway
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)

	async def get_one(self, character_uuid: UUID) -> Character:
		self.logger.info(f"Getting character by ID: {character_uuid}")

		query = (
			select(CharacterModel)
			.options(selectinload(CharacterModel.scenes))
			.where(CharacterModel.id == character_uuid)
		)

		result = await self.session.execute(query)
		character_model = result.scalar_one()
		return self._to_domain_character(character_model)

	async def get_for_scene(self, scene_id: UUID) -> list[Character]:
		self.logger.info(f"Getting characters for scene: {scene_id}")

		query = select(CharacterModel).join(CharacterModel.scenes).where(SceneModel.id == scene_id)

		result = await self.session.execute(query)
		character_models = result.scalars().all()
		return [self._to_domain_character(character_model) for character_model in character_models]

	async def delete(self, character_uuid: UUID):
		self.logger.info(f"Deleting character: {character_uuid}")

		query = delete(CharacterModel).where(CharacterModel.id == character_uuid)
		await self.session.execute(query)
		self.logger.info(f"Successfully deleted character: {character_uuid}")

	async def update(self, target_character_uuid: UUID, new_character_data: Character):
		self.logger.info(f"Updating character: {target_character_uuid}")

		# Build update data with proper column names
		update_data = {
			"name": new_character_data.name,
			"system_prompt": new_character_data.system_prompt,
			"is_public": new_character_data.is_public,
		}

		if new_character_data.owner_id is not None:
			update_data["owner_id"] = new_character_data.owner_id

		query = update(CharacterModel).where(CharacterModel.id == target_character_uuid).values(**update_data)
		await self.session.execute(query)
		self.logger.info(f"Successfully updated character: {target_character_uuid}")

	async def search(self, dto: CharacterFilterDTO, actor_id: UUID | None = None) -> Page[Character]:
		self.logger.info(f"Searching characters with filters: {dto} (actor={actor_id})")

		# Build query with joins for scene filtering
		query = select(CharacterModel).options(selectinload(CharacterModel.scenes))

		conditions = []

		if dto.ids:
			conditions.append(CharacterModel.id.in_(dto.ids))

		if dto.names:
			conditions.append(CharacterModel.name.in_(dto.names))

		if dto.owner_ids:
			conditions.append(CharacterModel.owner_id.in_(dto.owner_ids))

		if dto.bookmarked_by:
			# EXISTS, not a JOIN: a character saved by several of these users would
			# otherwise produce one row per bookmark and show up duplicated.
			conditions.append(
				exists().where(
					and_(
						character_bookmarks.c.character_id == CharacterModel.id,
						character_bookmarks.c.user_id.in_(dto.bookmarked_by),
					)
				)
			)

		conditions.append(self.visibility.public_or_owned(CharacterModel.is_public, CharacterModel.owner_id, actor_id))

		query = query.where(and_(*conditions))

		if dto.limit > 0:
			query = query.limit(dto.limit)

		if dto.offset >= 0:
			query = query.offset(dto.offset)

		count_query = select(func.count(CharacterModel.id.distinct())).where(and_(*conditions))

		count_result = await self.session.execute(count_query)
		total_count = count_result.scalar() or 0

		result = await self.session.execute(query)
		character_models = result.scalars().all()

		domain_characters = [self._to_domain_character(character_model) for character_model in character_models]

		self.logger.info(f"Found {len(domain_characters)} characters out of {total_count} total")

		return Page[Character](items=domain_characters, count=total_count, offset=dto.offset, limit=dto.limit)

	async def create(self, character: Character) -> UUID:
		self.logger.info(f"Creating character: {character.name}")

		character_model = CharacterModel(
			name=character.name,
			system_prompt=character.system_prompt,
			is_public=character.is_public,
			owner_id=character.owner_id,
		)

		self.session.add(character_model)
		await self.session.flush()
		await self.session.refresh(character_model)

		self.logger.info(f"Successfully created character with ID: {character_model.id}")
		return character_model.id

	async def set_like(self, character_id: UUID, user_id: UUID) -> None:
		# ON CONFLICT DO NOTHING keeps POST /like idempotent and concurrency-safe:
		# unlike INSERT ... WHERE NOT EXISTS, two racing likes can't fail on the PK.
		stmt = pg_insert(character_likes).values(character_id=character_id, user_id=user_id).on_conflict_do_nothing()
		await self.session.execute(stmt)

	async def unset_like(self, character_id: UUID, user_id: UUID) -> None:
		stmt = delete(character_likes).where(
			and_(character_likes.c.character_id == character_id, character_likes.c.user_id == user_id)
		)
		await self.session.execute(stmt)

	async def is_liked(self, character_id: UUID, user_id: UUID) -> bool:
		stmt = select(
			exists().where(
				and_(
					character_likes.c.character_id == character_id,
					character_likes.c.user_id == user_id,
				)
			)
		)
		return bool(await self.session.scalar(stmt))

	async def count_likes(self, character_id: UUID) -> int:
		stmt = select(func.count()).select_from(character_likes).where(character_likes.c.character_id == character_id)
		return int(await self.session.scalar(stmt) or 0)

	async def set_bookmark(self, character_id: UUID, user_id: UUID) -> None:
		stmt = (
			pg_insert(character_bookmarks).values(character_id=character_id, user_id=user_id).on_conflict_do_nothing()
		)
		await self.session.execute(stmt)

	async def unset_bookmark(self, character_id: UUID, user_id: UUID) -> None:
		stmt = delete(character_bookmarks).where(
			and_(character_bookmarks.c.character_id == character_id, character_bookmarks.c.user_id == user_id)
		)
		await self.session.execute(stmt)

	async def is_bookmarked(self, character_id: UUID, user_id: UUID) -> bool:
		stmt = select(
			exists().where(
				and_(
					character_bookmarks.c.character_id == character_id,
					character_bookmarks.c.user_id == user_id,
				)
			)
		)
		return bool(await self.session.scalar(stmt))

	def _to_domain_character(self, character_model: CharacterModel) -> Character:
		return Character(
			id=character_model.id,
			name=character_model.name,
			system_prompt=character_model.system_prompt,
			is_public=character_model.is_public,
			owner_id=character_model.owner_id,
		)
