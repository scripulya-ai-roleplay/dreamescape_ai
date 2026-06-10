import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from src.application.message.service import MessageService
from src.application.message.schemas import MessagesFilterDto
from src.application.ports import IMessageGateway, IUnitOfWork, Page
from src.domain.models import Message, ChatRoles


class TestMessageService:
	@pytest.fixture
	def mock_message_gateway(self):
		return AsyncMock(spec=IMessageGateway)

	@pytest.fixture
	def mock_uow(self):
		uow = AsyncMock(spec=IUnitOfWork)
		uow.__aenter__ = AsyncMock()
		uow.__aexit__ = AsyncMock(return_value=False)
		return uow

	@pytest.fixture
	def message_service(self, mock_message_gateway, mock_uow):
		return MessageService(message_gateway=mock_message_gateway, _uow=mock_uow)

	@pytest.fixture
	def sample_message(self):
		return Message(
			id=uuid4(),
			message="Hello, this is a test message",
			chat_id=uuid4(),
			role=ChatRoles.USER,
		)

	@pytest.fixture
	def sample_message_filter_dto(self):
		return MessagesFilterDto(chats_ids=[uuid4()], roles=[ChatRoles.USER], limit=10, offset=0)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_send_message_success(self, message_service, mock_message_gateway, sample_message):
		# Arrange
		expected_message = sample_message
		mock_message_gateway.create.return_value = expected_message

		# Act
		result = await message_service.send_message(sample_message)

		# Assert
		assert result == expected_message
		mock_message_gateway.create.assert_called_once_with(sample_message)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_search_success(
		self, message_service, mock_message_gateway, sample_message, sample_message_filter_dto
	):
		# Arrange
		expected_page = Page[Message](items=[sample_message], count=1, offset=0, limit=10)
		mock_message_gateway.search.return_value = expected_page

		# Act
		result = await message_service.search(sample_message_filter_dto)

		# Assert
		assert result == expected_page
		mock_message_gateway.search.assert_called_once_with(sample_message_filter_dto)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_get_one_success(self, message_service, mock_message_gateway, sample_message):
		# Arrange
		message_id = sample_message.id
		mock_message_gateway.get_one.return_value = sample_message

		# Act
		result = await message_service.get_one(message_id)

		# Assert
		assert result == sample_message
		mock_message_gateway.get_one.assert_called_once_with(message_id)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_update_success(self, message_service, mock_message_gateway):
		# Arrange
		message_id = uuid4()
		updated_text = "Updated message text"
		mock_message_gateway.update.return_value = message_id

		# Act
		result = await message_service.update(message_id, updated_text)

		# Assert
		assert result == message_id
		mock_message_gateway.update.assert_called_once_with(message_id, updated_text)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_delete_success(self, message_service, mock_message_gateway):
		# Arrange
		message_id = uuid4()
		mock_message_gateway.delete.return_value = message_id

		# Act
		result = await message_service.delete(message_id)

		# Assert
		assert result == message_id
		mock_message_gateway.delete.assert_called_once_with(message_id)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_send_message_gateway_error(self, message_service, mock_message_gateway, sample_message):
		# Arrange
		mock_message_gateway.create.side_effect = ValueError("Database error")

		# Act & Assert
		with pytest.raises(ValueError, match="Database error"):
			await message_service.send_message(sample_message)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_get_one_not_found(self, message_service, mock_message_gateway):
		# Arrange
		message_id = uuid4()
		mock_message_gateway.get_one.side_effect = ValueError("Message not found")

		# Act & Assert
		with pytest.raises(ValueError, match="Message not found"):
			await message_service.get_one(message_id)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_search_empty_results(self, message_service, mock_message_gateway, sample_message_filter_dto):
		# Arrange
		empty_page = Page[Message](items=[], count=0, offset=0, limit=10)
		mock_message_gateway.search.return_value = empty_page

		# Act
		result = await message_service.search(sample_message_filter_dto)

		# Assert
		assert result.items == []
		assert result.count == 0
		mock_message_gateway.search.assert_called_once_with(sample_message_filter_dto)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_update_not_found(self, message_service, mock_message_gateway):
		# Arrange
		message_id = uuid4()
		updated_text = "Updated text"
		mock_message_gateway.update.side_effect = ValueError("Message not found")

		# Act & Assert
		with pytest.raises(ValueError, match="Message not found"):
			await message_service.update(message_id, updated_text)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_delete_not_found(self, message_service, mock_message_gateway):
		# Arrange
		message_id = uuid4()
		mock_message_gateway.delete.side_effect = ValueError("Message not found")

		# Act & Assert
		with pytest.raises(ValueError, match="Message not found"):
			await message_service.delete(message_id)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_search_with_model_role(self, message_service, mock_message_gateway):
		# Arrange
		model_message = Message(
			id=uuid4(),
			message="AI generated response",
			chat_id=uuid4(),
			role=ChatRoles.MODEL,
		)

		filter_dto = MessagesFilterDto(roles=[ChatRoles.MODEL], limit=5, offset=0)

		expected_page = Page[Message](items=[model_message], count=1, offset=0, limit=5)
		mock_message_gateway.search.return_value = expected_page

		# Act
		result = await message_service.search(filter_dto)

		# Assert
		assert result == expected_page
		assert result.items[0].role == ChatRoles.MODEL
		mock_message_gateway.search.assert_called_once_with(filter_dto)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_send_message_with_empty_content(self, message_service, mock_message_gateway):
		# Arrange
		empty_message = Message(
			id=uuid4(),
			message="",  # Empty message content
			chat_id=uuid4(),
			role=ChatRoles.USER,
		)
		mock_message_gateway.create.return_value = empty_message

		# Act
		result = await message_service.send_message(empty_message)

		# Assert
		assert result == empty_message
		assert result.message == ""
		mock_message_gateway.create.assert_called_once_with(empty_message)
