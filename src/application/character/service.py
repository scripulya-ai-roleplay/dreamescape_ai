import logging
from dataclasses import dataclass
from uuid import UUID

from src.application.character.schemas import CharacterFilterDTO
from src.application.ports import ICharacterService, Page, IUnitOfWork, ICharacterGateway
from src.domain.models import Character

logger = logging.getLogger(__name__)


@dataclass
class CharacterService(ICharacterService):
	uow: IUnitOfWork
	gateway: ICharacterGateway

	async def create_character(self, character: Character) -> UUID:
		logger.info(f"Creating character: {character.name}")

		async with self.uow:
			try:
				character_id = await self.gateway.create(character)
				logger.info(f"Successfully created character with ID: {character_id}")
				return character_id
			except Exception as e:
				logger.error(f"Failed to create character: {e}")
				raise

	async def get_one(self, character_uuid: UUID) -> Character:
		logger.info(f"Getting character: {character_uuid}")

		try:
			character = await self.gateway.get_one(character_uuid)
			logger.info(f"Successfully retrieved character: {character_uuid}")
			return character
		except Exception as e:
			logger.error(f"Failed to get character {character_uuid}: {e}")
			raise

	async def search(self, dto: CharacterFilterDTO) -> Page[Character]:
		logger.info(f"Searching characters with filters: {dto}")

		try:
			result = await self.gateway.search(dto)
			logger.info(f"Found {result.count} characters")
			return result
		except Exception as e:
			logger.error(f"Failed to search characters: {e}")
			raise

	async def delete(self, character_uuid: UUID):
		logger.info(f"Deleting character: {character_uuid}")

		async with self.uow:
			try:
				# Check if character exists before deleting
				await self.gateway.get_one(character_uuid)
				await self.gateway.delete(character_uuid)
				logger.info(f"Successfully deleted character: {character_uuid}")
			except ValueError:
				# Re-raise validation errors as-is
				raise
			except Exception as e:
				logger.error(f"Failed to delete character {character_uuid}: {e}")
				raise

	async def update(self, target_character_uuid: UUID, new_character_data: Character):
		logger.info(f"Updating character: {target_character_uuid}")

		async with self.uow:
			try:
				# Check if character exists before updating
				await self.gateway.get_one(target_character_uuid)
				await self.gateway.update(target_character_uuid, new_character_data)
				logger.info(f"Successfully updated character: {target_character_uuid}")
			except ValueError:
				# Re-raise validation errors as-is
				raise
			except Exception as e:
				logger.error(f"Failed to update character {target_character_uuid}: {e}")
				raise
