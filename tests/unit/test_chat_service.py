import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from src.application.chats.service import ChatService
from src.application.chats.schemas import ChatFilterDTO
from src.application.ports import IChatGateway, Page
from src.domain.models import Chat


class TestChatService:
	@pytest.fixture
	def mock_chat_gateway(self):
		return AsyncMock(spec=IChatGateway)

	@pytest.fixture
	def chat_service(self, mock_chat_gateway):
		return ChatService(chat_gateway=mock_chat_gateway)

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

	@pytest.mark.asyncio
	async def test_get_one_success(self, chat_service, mock_chat_gateway, sample_chat):
		# Arrange
		chat_id = sample_chat.id
		mock_chat_gateway.get_one.return_value = sample_chat

		# Act
		result = await chat_service.get_one(chat_id)

		# Assert
		assert result == sample_chat
		mock_chat_gateway.get_one.assert_called_once_with(chat_id)

	@pytest.mark.asyncio
	async def test_search_success(self, chat_service, mock_chat_gateway, sample_chat, sample_chat_filter_dto):
		# Arrange
		expected_page = Page[Chat](items=[sample_chat], count=1, offset=0, limit=10)
		mock_chat_gateway.search.return_value = expected_page

		# Act
		result = await chat_service.search(sample_chat_filter_dto)

		# Assert
		assert result == expected_page
		mock_chat_gateway.search.assert_called_once_with(sample_chat_filter_dto)

	@pytest.mark.asyncio
	async def test_delete_success(self, chat_service, mock_chat_gateway):
		# Arrange
		chat_id = uuid4()
		mock_chat_gateway.delete.return_value = chat_id

		# Act
		result = await chat_service.delete(chat_id)

		# Assert
		assert result == chat_id
		mock_chat_gateway.delete.assert_called_once_with(chat_id)

	@pytest.mark.asyncio
	async def test_update_success(self, chat_service, mock_chat_gateway):
		# Arrange
		chat_id = uuid4()
		new_name = "Updated Chat Name"
		mock_chat_gateway.update.return_value = chat_id

		# Act
		result = await chat_service.update(chat_id, new_name)

		# Assert
		assert result == chat_id
		mock_chat_gateway.update.assert_called_once_with(chat_id, new_name)

	@pytest.mark.asyncio
	async def test_start_chat_gateway_error(self, chat_service, mock_chat_gateway, sample_chat):
		# Arrange
		mock_chat_gateway.create.side_effect = ValueError("Database error")

		# Act & Assert
		with pytest.raises(ValueError, match="Database error"):
			await chat_service.start_chat(sample_chat)

	@pytest.mark.asyncio
	async def test_get_one_not_found(self, chat_service, mock_chat_gateway):
		# Arrange
		chat_id = uuid4()
		mock_chat_gateway.get_one.side_effect = ValueError("Chat not found")

		# Act & Assert
		with pytest.raises(ValueError, match="Chat not found"):
			await chat_service.get_one(chat_id)

	@pytest.mark.asyncio
	async def test_search_empty_results(self, chat_service, mock_chat_gateway, sample_chat_filter_dto):
		# Arrange
		empty_page = Page[Chat](items=[], count=0, offset=0, limit=10)
		mock_chat_gateway.search.return_value = empty_page

		# Act
		result = await chat_service.search(sample_chat_filter_dto)

		# Assert
		assert result.items == []
		assert result.count == 0
		mock_chat_gateway.search.assert_called_once_with(sample_chat_filter_dto)

	@pytest.mark.asyncio
	async def test_delete_not_found(self, chat_service, mock_chat_gateway):
		# Arrange
		chat_id = uuid4()
		mock_chat_gateway.delete.side_effect = ValueError("Chat not found")

		# Act & Assert
		with pytest.raises(ValueError, match="Chat not found"):
			await chat_service.delete(chat_id)

	@pytest.mark.asyncio
	async def test_update_not_found(self, chat_service, mock_chat_gateway):
		# Arrange
		chat_id = uuid4()
		new_name = "Updated Name"
		mock_chat_gateway.update.side_effect = ValueError("Chat not found")

		# Act & Assert
		with pytest.raises(ValueError, match="Chat not found"):
			await chat_service.update(chat_id, new_name)
