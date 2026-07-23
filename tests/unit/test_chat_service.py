import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import HTTPException

from src.application.auth.authz import AuthorizationService
from src.application.chats.service import ChatService
from src.application.chats.schemas import ChatFilterDTO
from src.application.ports.chats import IChatGateway
from src.application.ports.common import IUnitOfWork, Page
from src.domain.models import Chat


class TestChatService:
	@pytest.fixture
	def authz(self):
		return AuthorizationService()

	@pytest.fixture
	def mock_chat_gateway(self):
		return AsyncMock(spec=IChatGateway)

	@pytest.fixture
	def mock_uow(self):
		uow = AsyncMock(spec=IUnitOfWork)
		uow.__aenter__ = AsyncMock()
		uow.__aexit__ = AsyncMock(return_value=False)
		return uow

	@pytest.fixture
	def chat_service(self, mock_chat_gateway, mock_uow, authz):
		return ChatService(chat_gateway=mock_chat_gateway, uow=mock_uow, authz=authz)

	@pytest.fixture
	def sample_chat(self):
		return Chat(
			id=uuid4(),
			title="Test Chat",
			user_id=uuid4(),
			scene_id=uuid4(),
		)

	@pytest.fixture
	def sample_chat_filter_dto(self):
		return ChatFilterDTO(titles=["Test Chat"], limit=10, offset=0)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_start_chat_success(self, chat_service, mock_chat_gateway, sample_chat):
		# Arrange
		expected_chat_id = uuid4()
		mock_chat_gateway.create.return_value = expected_chat_id

		# Act
		result = await chat_service.start_chat(sample_chat)

		# Assert
		assert result == expected_chat_id
		mock_chat_gateway.create.assert_called_once_with(sample_chat)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_get_one_owner_ok(self, chat_service, mock_chat_gateway, sample_chat):
		# Arrange
		chat_id = sample_chat.id
		mock_chat_gateway.get_one.return_value = sample_chat

		# Act
		result = await chat_service.get_one(chat_id, sample_chat.user_id)

		# Assert
		assert result == sample_chat
		mock_chat_gateway.get_one.assert_called_once_with(chat_id)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_get_one_not_owner_raises_403(self, chat_service, mock_chat_gateway, sample_chat):
		mock_chat_gateway.get_one.return_value = sample_chat

		with pytest.raises(HTTPException) as exc:
			await chat_service.get_one(sample_chat.id, uuid4())  # a different user
		assert exc.value.status_code == 403

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_search_success(self, chat_service, mock_chat_gateway, sample_chat, sample_chat_filter_dto):
		# Arrange
		actor_id = uuid4()
		expected_page = Page[Chat](items=[sample_chat], count=1, offset=0, limit=10)
		mock_chat_gateway.search.return_value = expected_page

		# Act
		result = await chat_service.search(sample_chat_filter_dto, actor_id)

		# Assert
		assert result == expected_page
		mock_chat_gateway.search.assert_called_once_with(sample_chat_filter_dto, actor_id=actor_id)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_delete_success(self, chat_service, mock_chat_gateway, sample_chat):
		# Arrange: the gateway returns an owned chat, so the ownership gate passes.
		chat_id = sample_chat.id
		mock_chat_gateway.get_one.return_value = sample_chat
		mock_chat_gateway.delete.return_value = chat_id

		# Act
		result = await chat_service.delete(chat_id, sample_chat.user_id)

		# Assert
		assert result == chat_id
		mock_chat_gateway.delete.assert_called_once_with(chat_id)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_delete_not_owner_raises_403_without_deleting(self, chat_service, mock_chat_gateway, sample_chat):
		mock_chat_gateway.get_one.return_value = sample_chat

		with pytest.raises(HTTPException) as exc:
			await chat_service.delete(sample_chat.id, uuid4())  # not the owner
		assert exc.value.status_code == 403

		mock_chat_gateway.delete.assert_not_called()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_update_success(self, chat_service, mock_chat_gateway, sample_chat):
		# Arrange
		chat_id = sample_chat.id
		new_name = "Updated Chat Name"
		mock_chat_gateway.get_one.return_value = sample_chat
		mock_chat_gateway.update.return_value = chat_id

		# Act
		result = await chat_service.update(chat_id, new_name, sample_chat.user_id)

		# Assert
		assert result == chat_id
		mock_chat_gateway.update.assert_called_once_with(chat_id, new_name)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_update_not_owner_raises_403_without_updating(self, chat_service, mock_chat_gateway, sample_chat):
		mock_chat_gateway.get_one.return_value = sample_chat

		with pytest.raises(HTTPException) as exc:
			await chat_service.update(sample_chat.id, "x", uuid4())  # not the owner
		assert exc.value.status_code == 403

		mock_chat_gateway.update.assert_not_called()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_set_persona_success(self, chat_service, mock_chat_gateway, sample_chat):
		# Arrange
		chat_id = sample_chat.id
		character_id = uuid4()
		mock_chat_gateway.get_one.return_value = sample_chat
		mock_chat_gateway.set_persona.return_value = chat_id

		# Act
		result = await chat_service.set_persona(chat_id, character_id, sample_chat.user_id)

		# Assert
		assert result == chat_id
		mock_chat_gateway.set_persona.assert_called_once_with(chat_id, character_id)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_set_persona_not_owner_raises_403(self, chat_service, mock_chat_gateway, sample_chat):
		mock_chat_gateway.get_one.return_value = sample_chat

		with pytest.raises(HTTPException) as exc:
			await chat_service.set_persona(sample_chat.id, uuid4(), uuid4())  # not the owner
		assert exc.value.status_code == 403

		mock_chat_gateway.set_persona.assert_not_called()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_start_chat_gateway_error(self, chat_service, mock_chat_gateway, sample_chat):
		# Arrange
		mock_chat_gateway.create.side_effect = ValueError("Database error")

		# Act & Assert
		with pytest.raises(ValueError, match="Database error"):
			await chat_service.start_chat(sample_chat)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_get_one_not_found(self, chat_service, mock_chat_gateway):
		# Arrange
		chat_id = uuid4()
		mock_chat_gateway.get_one.side_effect = ValueError("Chat not found")

		# Act & Assert
		with pytest.raises(ValueError, match="Chat not found"):
			await chat_service.get_one(chat_id, uuid4())

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_search_empty_results(self, chat_service, mock_chat_gateway, sample_chat_filter_dto):
		# Arrange
		actor_id = uuid4()
		empty_page = Page[Chat](items=[], count=0, offset=0, limit=10)
		mock_chat_gateway.search.return_value = empty_page

		# Act
		result = await chat_service.search(sample_chat_filter_dto, actor_id)

		# Assert
		assert result.items == []
		assert result.count == 0
		mock_chat_gateway.search.assert_called_once_with(sample_chat_filter_dto, actor_id=actor_id)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_delete_not_found(self, chat_service, mock_chat_gateway, sample_chat):
		# Arrange: owned chat resolves, but the row is gone at delete time.
		mock_chat_gateway.get_one.return_value = sample_chat
		mock_chat_gateway.delete.side_effect = ValueError("Chat not found")

		# Act & Assert
		with pytest.raises(ValueError, match="Chat not found"):
			await chat_service.delete(sample_chat.id, sample_chat.user_id)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_update_not_found(self, chat_service, mock_chat_gateway, sample_chat):
		# Arrange
		mock_chat_gateway.get_one.return_value = sample_chat
		mock_chat_gateway.update.side_effect = ValueError("Chat not found")

		# Act & Assert
		with pytest.raises(ValueError, match="Chat not found"):
			await chat_service.update(sample_chat.id, "Updated Name", sample_chat.user_id)
