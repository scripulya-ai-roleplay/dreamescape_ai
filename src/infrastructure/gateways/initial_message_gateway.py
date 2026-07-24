import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.scenes import IInitialMessageGateway
from src.domain.models import InitialMessage
from src.infrastructure.database.models import SceneInitialMessage as InitialMessageModel
from src.infrastructure.logging.logger import Logger


@dataclass
class InitialMessageGateway(IInitialMessageGateway):
	_session: AsyncSession
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)

	async def get_one(self, uuid: UUID) -> InitialMessage:
		self.logger.info(f"Getting initial message by ID: {uuid}")

		query = select(InitialMessageModel).where(InitialMessageModel.id == uuid)
		result = await self._session.execute(query)
		message_model = result.scalar_one_or_none()

		if not message_model:
			raise ValueError(f"Initial message with ID {uuid} not found")

		return self._to_domain(message_model)

	async def list_for_scene(self, scene_id: UUID) -> list[InitialMessage]:
		self.logger.info(f"Listing initial messages for scene: {scene_id}")

		query = (
			select(InitialMessageModel)
			.where(InitialMessageModel.scene_id == scene_id)
			.order_by(InitialMessageModel.created_at, InitialMessageModel.id)
		)
		result = await self._session.execute(query)
		models = result.scalars().all()

		return [self._to_domain(m) for m in models]

	async def bulk_create(self, scene_id: UUID, items: list[InitialMessage]) -> list[InitialMessage]:
		self.logger.info(f"Bulk creating {len(items)} initial message(s) for scene: {scene_id}")

		models = [InitialMessageModel(scene_id=scene_id, text=item.text) for item in items]
		self._session.add_all(models)
		await self._session.flush()
		for m in models:
			await self._session.refresh(m)

		self.logger.info(f"Successfully created {len(models)} initial message(s) for scene: {scene_id}")
		return [self._to_domain(m) for m in models]

	async def update(self, uuid: UUID, updated_text: str) -> UUID:
		self.logger.info(f"Updating initial message {uuid}")

		query = (
			update(InitialMessageModel)
			.where(InitialMessageModel.id == uuid)
			.values(text=updated_text, updated_at=func.now())
		)
		result = await self._session.execute(query)

		if result.rowcount == 0:
			raise ValueError(f"Initial message with ID {uuid} not found")

		self.logger.info(f"Successfully updated initial message: {uuid}")
		return uuid

	async def delete(self, uuid: UUID) -> UUID:
		self.logger.info(f"Deleting initial message: {uuid}")

		query = delete(InitialMessageModel).where(InitialMessageModel.id == uuid)
		result = await self._session.execute(query)

		if result.rowcount == 0:
			raise ValueError(f"Initial message with ID {uuid} not found")

		self.logger.info(f"Successfully deleted initial message: {uuid}")
		return uuid

	def _to_domain(self, message_model: InitialMessageModel) -> InitialMessage:
		return InitialMessage(
			id=message_model.id,
			scene_id=message_model.scene_id,
			text=message_model.text,
			date_created=message_model.created_at,
			date_edited=message_model.updated_at,
		)
