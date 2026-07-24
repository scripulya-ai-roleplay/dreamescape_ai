import logging
from dataclasses import dataclass
from uuid import UUID

from src.application.ports.authorization import IAuthorizationService
from src.application.ports.common import IUnitOfWork
from src.application.ports.scenes import IInitialMessageGateway, IInitialMessageService, ISceneGateway
from src.domain.models import InitialMessage
from src.infrastructure.logging.logger import Logger


@dataclass
class InitialMessageService(IInitialMessageService):
	initial_message_gateway: IInitialMessageGateway
	scene_gateway: ISceneGateway
	uow: IUnitOfWork
	authz: IAuthorizationService
	logger: logging.Logger = logging.getLogger(Logger.LOGGER_NAME)

	async def list_for_scene(self, scene_uuid: UUID, actor_id: UUID | None) -> list[InitialMessage]:
		self.logger.info(f"Listing initial messages for scene: {scene_uuid}")

		# Visibility is gated by the owning scene: a private scene's initial
		# messages are only readable by its owner (would otherwise leak prompts).
		scene = await self.scene_gateway.get_one(scene_uuid)
		self.authz.require_visible(is_public=scene.is_public, owner_id=scene.owner_id, actor_id=actor_id, noun="scene")

		return await self.initial_message_gateway.list_for_scene(scene_uuid)

	async def update(self, initial_message_uuid: UUID, updated_text: str, actor_id: UUID) -> UUID:
		self.logger.info(f"Updating initial message: {initial_message_uuid}")

		await self._require_owned(initial_message_uuid, actor_id)
		async with self.uow:
			return await self.initial_message_gateway.update(initial_message_uuid, updated_text)

	async def delete(self, initial_message_uuid: UUID, actor_id: UUID) -> UUID:
		self.logger.info(f"Deleting initial message: {initial_message_uuid}")

		initial_message = await self._require_owned(initial_message_uuid, actor_id)
		async with self.uow:
			if await self.initial_message_gateway.count_referencing_chats(initial_message_uuid) > 0:
				raise ValueError("Initial message is in use by existing chats and cannot be deleted")
			if len(await self.initial_message_gateway.list_for_scene(initial_message.scene_id)) <= 1:
				raise ValueError("Scene must keep at least one initial message")
			return await self.initial_message_gateway.delete(initial_message_uuid)

	async def _require_owned(self, initial_message_uuid: UUID, actor_id: UUID) -> InitialMessage:
		# Ownership is derived from the owning scene, since initial messages are
		# only editable by the scene's author.
		initial_message = await self.initial_message_gateway.get_one(initial_message_uuid)
		scene = await self.scene_gateway.get_one(initial_message.scene_id)
		self.authz.require_owned(owner_id=scene.owner_id, actor_id=actor_id, noun="initial message")
		return initial_message
