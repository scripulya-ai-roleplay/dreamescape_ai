import pytest
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.gateways.chat_gateway import ChatGateway
from src.application.chats.schemas import ChatFilterDTO
from src.application.ports import Page
from src.domain.models import Chat
from src.infrastructure.database.models import Chat as ChatModel


class TestChatGateway:
	@pytest.fixture
	def mock_session(self):
		session = AsyncMock(spec=AsyncSession)
		return session

	@pytest.fixture
	def chat_gateway(self, mock_session):
		return ChatGateway(_session=mock_session)

	@pytest.fixture
	def sample_chat_model(self):
		model = Mock(spec=ChatModel)
		model.id = uuid4()
		model.name = "Test Chat"
		model.user_id = uuid4()
		model.scene_id = uuid4()
		model.messages = []
		return model

	@pytest.fixture
	def sample_chat_filter_dto(self):
		return ChatFilterDTO(titles=["Test Chat"], limit=10, offset=0)

	@pytest.fixture
	def sample_domain_chat(self):
		return Chat(
			id=uuid4(),
			title="Test Chat",
			user_id=uuid4(),
			scene_id=uuid4(),
		)

	@pytest.mark.asyncio
	async def test_create_success(self, chat_gateway, mock_session, sample_domain_chat):
		# Arrange
		expected_id = uuid4()

		# Mock the created model that will be added to session
		def mock_add(model):
			model.id = expected_id

		mock_session.add = Mock(side_effect=mock_add)
		mock_session.commit = AsyncMock()
		mock_session.refresh = AsyncMock()

		# Act
		result = await chat_gateway.create(sample_domain_chat)

		# Assert
		assert result == expected_id
		mock_session.add.assert_called_once()
		mock_session.commit.assert_called_once()
		mock_session.refresh.assert_called_once()

	@pytest.mark.asyncio
	async def test_get_one_success(self, chat_gateway, mock_session, sample_chat_model):
		# Arrange
		chat_id = sample_chat_model.id
		mock_result = AsyncMock()
		mock_result.scalar_one_or_none.return_value = sample_chat_model
		mock_session.execute.return_value = mock_result

		# Act
		result = await chat_gateway.get_one(chat_id)

		# Assert
		assert result.id == sample_chat_model.id
		assert result.title == sample_chat_model.name
		assert result.user_id == sample_chat_model.user_id
		assert result.scene_id == sample_chat_model.scene_id
		mock_session.execute.assert_called_once()

	@pytest.mark.asyncio
	async def test_get_one_not_found(self, chat_gateway, mock_session):
		# Arrange
		chat_id = uuid4()
		mock_result = AsyncMock()
		mock_result.scalar_one_or_none.return_value = None
		mock_session.execute.return_value = mock_result

		# Act & Assert
		with pytest.raises(ValueError, match="Chat with ID .* not found"):
			await chat_gateway.get_one(chat_id)

	@pytest.mark.asyncio
	async def test_search_success(self, chat_gateway, mock_session, sample_chat_model, sample_chat_filter_dto):
		# Arrange
		mock_count_result = AsyncMock()
		mock_count_result.scalar.return_value = 1

		mock_search_result = AsyncMock()
		mock_search_result.scalars.return_value.all.return_value = [sample_chat_model]

		mock_session.execute.side_effect = [mock_count_result, mock_search_result]

		# Act
		result = await chat_gateway.search(sample_chat_filter_dto)

		# Assert
		assert isinstance(result, Page)
		assert len(result.items) == 1
		assert result.count == 1
		assert result.offset == 0
		assert result.limit == 10
		assert result.items[0].id == sample_chat_model.id
		assert result.items[0].title == sample_chat_model.name

	@pytest.mark.asyncio
	async def test_search_with_filters(self, chat_gateway, mock_session, sample_chat_model):
		# Arrange
		filter_dto = ChatFilterDTO(
			ids=[uuid4(), uuid4()],
			titles=["Chat1", "Chat2"],
			user_ids=[uuid4()],
			scene_ids=[uuid4()],
			limit=20,
			offset=10,
		)

		mock_count_result = AsyncMock()
		mock_count_result.scalar.return_value = 2

		mock_search_result = AsyncMock()
		mock_search_result.scalars.return_value.all.return_value = [sample_chat_model]

		mock_session.execute.side_effect = [mock_count_result, mock_search_result]

		# Act
		result = await chat_gateway.search(filter_dto)

		# Assert
		assert result.count == 2
		assert result.offset == 10
		assert result.limit == 20
		assert len(result.items) == 1

	@pytest.mark.asyncio
	async def test_search_no_results(self, chat_gateway, mock_session, sample_chat_filter_dto):
		# Arrange
		mock_count_result = AsyncMock()
		mock_count_result.scalar.return_value = 0

		mock_search_result = AsyncMock()
		mock_search_result.scalars.return_value.all.return_value = []

		mock_session.execute.side_effect = [mock_count_result, mock_search_result]

		# Act
		result = await chat_gateway.search(sample_chat_filter_dto)

		# Assert
		assert result.count == 0
		assert len(result.items) == 0

	@pytest.mark.asyncio
	async def test_delete_success(self, chat_gateway, mock_session):
		# Arrange
		chat_id = uuid4()
		mock_result = AsyncMock()
		mock_result.rowcount = 1
		mock_session.execute.return_value = mock_result
		mock_session.commit = AsyncMock()

		# Act
		result = await chat_gateway.delete(chat_id)

		# Assert
		assert result == chat_id
		mock_session.execute.assert_called_once()
		mock_session.commit.assert_called_once()

	@pytest.mark.asyncio
	async def test_delete_not_found(self, chat_gateway, mock_session):
		# Arrange
		chat_id = uuid4()
		mock_result = AsyncMock()
		mock_result.rowcount = 0
		mock_session.execute.return_value = mock_result

		# Act & Assert
		with pytest.raises(ValueError, match="Chat with ID .* not found"):
			await chat_gateway.delete(chat_id)

	@pytest.mark.asyncio
	async def test_update_success(self, chat_gateway, mock_session):
		# Arrange
		chat_id = uuid4()
		new_name = "Updated Chat Name"
		mock_result = AsyncMock()
		mock_result.rowcount = 1
		mock_session.execute.return_value = mock_result
		mock_session.commit = AsyncMock()

		# Act
		result = await chat_gateway.update(chat_id, new_name)

		# Assert
		assert result == chat_id
		mock_session.execute.assert_called_once()
		mock_session.commit.assert_called_once()

	@pytest.mark.asyncio
	async def test_update_not_found(self, chat_gateway, mock_session):
		# Arrange
		chat_id = uuid4()
		new_name = "Updated Name"
		mock_result = AsyncMock()
		mock_result.rowcount = 0
		mock_session.execute.return_value = mock_result

		# Act & Assert
		with pytest.raises(ValueError, match="Chat with ID .* not found"):
			await chat_gateway.update(chat_id, new_name)

	def test_to_domain_chat_conversion(self, chat_gateway, sample_chat_model):
		# Act
		result = chat_gateway._to_domain_chat(sample_chat_model)

		# Assert
		assert result.id == sample_chat_model.id
		assert result.title == sample_chat_model.name  # Conversion from 'name' to 'title'
		assert result.user_id == sample_chat_model.user_id
		assert result.scene_id == sample_chat_model.scene_id

	@pytest.mark.asyncio
	async def test_search_empty_filters(self, chat_gateway, mock_session, sample_chat_model):
		# Arrange
		empty_filter_dto = ChatFilterDTO(limit=10, offset=0)

		mock_count_result = AsyncMock()
		mock_count_result.scalar.return_value = 1

		mock_search_result = AsyncMock()
		mock_search_result.scalars.return_value.all.return_value = [sample_chat_model]

		mock_session.execute.side_effect = [mock_count_result, mock_search_result]

		# Act
		result = await chat_gateway.search(empty_filter_dto)

		# Assert
		assert len(result.items) == 1
		assert result.count == 1
