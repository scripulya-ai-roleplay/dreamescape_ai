from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.application.auth.authz import AuthorizationService
from src.application.scene.initial_message_service import InitialMessageService
from src.domain.models import InitialMessage, Scene


@pytest.mark.unit
class TestInitialMessageService:
	"""Unit tests for InitialMessageService visibility/ownership gates."""

	@pytest.fixture
	def authz(self):
		return AuthorizationService()

	@pytest.fixture
	def mock_initial_message_gateway(self):
		return AsyncMock()

	@pytest.fixture
	def mock_scene_gateway(self):
		return AsyncMock()

	@pytest.fixture
	def mock_uow(self):
		uow = AsyncMock()
		uow.__aenter__ = AsyncMock(return_value=uow)
		uow.__aexit__ = AsyncMock(return_value=None)
		return uow

	@pytest.fixture
	def service(self, mock_initial_message_gateway, mock_scene_gateway, mock_uow, authz):
		return InitialMessageService(
			initial_message_gateway=mock_initial_message_gateway,
			scene_gateway=mock_scene_gateway,
			uow=mock_uow,
			authz=authz,
		)

	@pytest.mark.asyncio
	async def test_list_for_scene_public_ok(self, service, mock_scene_gateway, mock_initial_message_gateway):
		scene_id = uuid4()
		# Visibility is gated by the owning scene; a public scene is readable by anyone.
		mock_scene_gateway.get_one.return_value = Scene(
			id=scene_id, title="Public", owner_id=uuid4(), background_prompt="b", is_public=True
		)
		mock_initial_message_gateway.list_for_scene.return_value = [InitialMessage(text="hi")]

		result = await service.list_for_scene(scene_id, None)

		assert len(result) == 1
		mock_initial_message_gateway.list_for_scene.assert_called_once_with(scene_id)

	@pytest.mark.asyncio
	async def test_list_for_scene_private_other_user_403(
		self, service, mock_scene_gateway, mock_initial_message_gateway
	):
		scene_id = uuid4()
		mock_scene_gateway.get_one.return_value = Scene(
			id=scene_id, title="Private", owner_id=uuid4(), background_prompt="b", is_public=False
		)

		with pytest.raises(HTTPException) as exc:
			await service.list_for_scene(scene_id, uuid4())  # not the owner
		assert exc.value.status_code == 403

		mock_initial_message_gateway.list_for_scene.assert_not_called()

	@pytest.mark.asyncio
	async def test_update_requires_scene_owner(self, service, mock_initial_message_gateway, mock_scene_gateway):
		# Ownership is derived from the owning scene: a non-owner cannot edit.
		scene_id = uuid4()
		mock_initial_message_gateway.get_one.return_value = InitialMessage(id=uuid4(), scene_id=scene_id, text="hi")
		mock_scene_gateway.get_one.return_value = Scene(
			id=scene_id, title="Private", owner_id=uuid4(), background_prompt="b", is_public=False
		)

		with pytest.raises(HTTPException) as exc:
			await service.update(uuid4(), "new text", uuid4())  # not the owner
		assert exc.value.status_code == 403

		mock_initial_message_gateway.update.assert_not_called()

	@pytest.mark.asyncio
	async def test_delete_by_owner_calls_gateway(self, service, mock_initial_message_gateway, mock_scene_gateway):
		scene_id = uuid4()
		owner = uuid4()
		im_id = uuid4()
		mock_initial_message_gateway.get_one.return_value = InitialMessage(id=im_id, scene_id=scene_id, text="hi")
		mock_scene_gateway.get_one.return_value = Scene(
			id=scene_id, title="Mine", owner_id=owner, background_prompt="b", is_public=False
		)
		mock_initial_message_gateway.delete.return_value = im_id
		mock_initial_message_gateway.count_referencing_chats.return_value = 0
		mock_initial_message_gateway.list_for_scene.return_value = [
			InitialMessage(id=im_id, scene_id=scene_id, text="hi"),
			InitialMessage(id=uuid4(), scene_id=scene_id, text="second"),
		]

		result = await service.delete(im_id, owner)

		assert result == im_id
		mock_initial_message_gateway.delete.assert_called_once_with(im_id)

	@pytest.mark.asyncio
	async def test_delete_last_initial_message_blocked(self, service, mock_initial_message_gateway, mock_scene_gateway):
		# A scene's only initial message cannot be deleted: new chats started from
		# it could then never satisfy the greeting gate, and there is no endpoint
		# to add one to an existing scene.
		scene_id = uuid4()
		owner = uuid4()
		im_id = uuid4()
		mock_initial_message_gateway.get_one.return_value = InitialMessage(id=im_id, scene_id=scene_id, text="hi")
		mock_scene_gateway.get_one.return_value = Scene(
			id=scene_id, title="Mine", owner_id=owner, background_prompt="b", is_public=False
		)
		mock_initial_message_gateway.count_referencing_chats.return_value = 0
		mock_initial_message_gateway.list_for_scene.return_value = [
			InitialMessage(id=im_id, scene_id=scene_id, text="hi")
		]

		with pytest.raises(ValueError, match="keep at least one initial message"):
			await service.delete(im_id, owner)

		mock_initial_message_gateway.delete.assert_not_called()

	@pytest.mark.asyncio
	async def test_delete_blocked_when_referenced(self, service, mock_initial_message_gateway, mock_scene_gateway):
		# An initial message referenced by any chat cannot be deleted: nulling the
		# pointer would re-arm the greeting gate for active conversations.
		scene_id = uuid4()
		owner = uuid4()
		im_id = uuid4()
		mock_initial_message_gateway.get_one.return_value = InitialMessage(id=im_id, scene_id=scene_id, text="hi")
		mock_scene_gateway.get_one.return_value = Scene(
			id=scene_id, title="Mine", owner_id=owner, background_prompt="b", is_public=False
		)
		mock_initial_message_gateway.count_referencing_chats.return_value = 1

		with pytest.raises(ValueError, match="in use by existing chats"):
			await service.delete(im_id, owner)

		mock_initial_message_gateway.delete.assert_not_called()
