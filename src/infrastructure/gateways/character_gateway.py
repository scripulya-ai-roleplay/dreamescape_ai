import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, delete, func, and_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.application.character.schemas import CharacterFilterDTO
from src.application.ports import ICharacterGateway, Page
from src.domain.models import Character
from src.infrastructure.database.models import Character as CharacterModel

logger = logging.getLogger(__name__)


@dataclass
class CharacterGateway(ICharacterGateway):
	session: AsyncSession

	async def get_one(self, character_uuid: UUID) -> Character:
		logger.info(f"Getting character by ID: {character_uuid}")

		query = (
			select(CharacterModel)
			.options(selectinload(CharacterModel.scenes))
			.where(CharacterModel.id == character_uuid)
		)

		result = await self.session.execute(query)
		character_model = result.scalar_one()
		return self._to_domain_character(character_model)

	async def delete(self, character_uuid: UUID):
		logger.info(f"Deleting character: {character_uuid}")

		query = delete(CharacterModel).where(CharacterModel.id == character_uuid)
		await self.session.execute(query)
		logger.info(f"Successfully deleted character: {character_uuid}")

	async def update(self, target_character_uuid: UUID, new_character_data: Character):
		logger.info(f"Updating character: {target_character_uuid}")

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
		logger.info(f"Successfully updated character: {target_character_uuid}")

	async def search(self, dto: CharacterFilterDTO) -> Page[Character]:
		logger.info(f"Searching characters with filters: {dto}")

		# Build query with joins for scene filtering
		query = select(CharacterModel).options(selectinload(CharacterModel.scenes))

		conditions = []

		if dto.ids:
			conditions.append(CharacterModel.id.in_(dto.ids))

		if dto.names:
			conditions.append(CharacterModel.name.in_(dto.names))

		if dto.owner_ids:
			conditions.append(CharacterModel.owner_id.in_(dto.owner_ids))

		if conditions:
			query = query.where(and_(*conditions))

		if dto.limit > 0:
			query = query.limit(dto.limit)

		if dto.offset >= 0:
			query = query.offset(dto.offset)

		# Get total count
		count_query = select(func.count(CharacterModel.id.distinct()))

		if conditions:
			count_query = count_query.where(and_(*conditions))

		count_result = await self.session.execute(count_query)
		total_count = count_result.scalar() or 0

		# Execute query
		result = await self.session.execute(query)
		character_models = result.scalars().all()

		# Convert to domain models
		domain_characters = [self._to_domain_character(character_model) for character_model in character_models]

		logger.info(f"Found {len(domain_characters)} characters out of {total_count} total")

		return Page[Character](items=domain_characters, count=total_count, offset=dto.offset, limit=dto.limit)

	async def create(self, character: Character) -> UUID:
		logger.info(f"Creating character: {character.name}")

		character_model = CharacterModel(
			name=character.name,
			system_prompt=character.system_prompt,
			is_public=character.is_public,
			owner_id=character.owner_id,
		)

		self.session.add(character_model)
		await self.session.flush()
		await self.session.refresh(character_model)

		logger.info(f"Successfully created character with ID: {character_model.id}")
		return character_model.id

	def _to_domain_character(self, character_model: CharacterModel) -> Character:
		return Character(
			id=character_model.id,
			name=character_model.name,
			system_prompt=character_model.system_prompt,
			is_public=character_model.is_public,
			owner_id=character_model.owner_id,
		)
