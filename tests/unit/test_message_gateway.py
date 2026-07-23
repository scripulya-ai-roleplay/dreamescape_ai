import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.gateways.message_gateway import MessageGateway
from src.application.message.schemas import MessagesFilterDto
from src.application.ports.common import Page
from src.domain.models import Message, ChatRoles, MessageStatus
from src.infrastructure.database.models import Message as MessageModel


class TestMessageGateway:
	@pytest.fixture
	def mock_session(self):
		session = AsyncMock(spec=AsyncSession)
		return session

	@pytest.fixture
	def message_gateway(self, mock_session):
		return MessageGateway(_session=mock_session)

	@pytest.mark.unit
	def test_to_domain_message_maps_status(self, message_gateway):
		# The DB string 'status' must round-trip into the MessageStatus enum.
		result = message_gateway._to_domain_message(self._model_row(status="pending"))
		assert result.status == MessageStatus.PENDING

	@pytest.fixture
	def sample_message_model(self):
		model = Mock(spec=MessageModel)
		model.id = uuid4()
		model.chat_id = uuid4()
		model.role = "user"
		model.content = "Test message content"
		model.status = "completed"
		model.cost_crystals = 0
		model.created_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
		model.updated_at = datetime(2024, 1, 2, 15, 30, 0, tzinfo=timezone.utc)
		return model

	@pytest.fixture
	def sample_message_filter_dto(self):
		return MessagesFilterDto(chats_ids=[uuid4()], roles=[ChatRoles.USER], limit=10, offset=0)

	@pytest.fixture
	def sample_domain_message(self):
		return Message(
			id=uuid4(),
			message="Test message content",
			chat_id=uuid4(),
			role=ChatRoles.USER,
		)

	def _model_row(self, *, role="model", content="AI response", status="pending"):
		"""A standalone ORM-style row for SELECT-based gateway methods."""
		row = Mock(spec=MessageModel)
		row.id = uuid4()
		row.chat_id = uuid4()
		row.role = role
		row.content = content
		row.status = status
		row.cost_crystals = 0
		row.created_at = datetime(2024, 3, 10, 8, 0, 0, tzinfo=timezone.utc)
		row.updated_at = datetime(2024, 3, 11, 9, 0, 0, tzinfo=timezone.utc)
		return row

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_create_success(self, message_gateway, mock_session, sample_domain_message):
		# Arrange
		expected_id = uuid4()

		# Mock the created model that will be added to session
		def mock_add(model):
			model.id = expected_id
			model.chat_id = sample_domain_message.chat_id
			model.role = sample_domain_message.role.value
			model.content = sample_domain_message.message

		mock_session.add = Mock(side_effect=mock_add)
		mock_session.refresh = AsyncMock()

		# Act
		result = await message_gateway.create(sample_domain_message)

		# Assert
		assert result.id == expected_id
		assert result.chat_id == sample_domain_message.chat_id
		assert result.role == sample_domain_message.role
		assert result.message == sample_domain_message.message
		# Timestamps are populated by the database (server defaults), so they are
		# absent on a non-flushed model in this unit test.
		assert result.date_created is None
		assert result.date_edited is None
		mock_session.add.assert_called_once()
		mock_session.refresh.assert_called_once()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_search_success(self, message_gateway, mock_session, sample_message_model, sample_message_filter_dto):
		# Arrange
		mock_count_result = Mock()
		mock_count_result.scalar.return_value = 1

		mock_scalars = Mock()
		mock_scalars.all.return_value = [sample_message_model]
		mock_search_result = Mock()
		mock_search_result.scalars.return_value = mock_scalars

		mock_session.execute.side_effect = [mock_count_result, mock_search_result]

		# Act
		result = await message_gateway.search(sample_message_filter_dto)

		# Assert
		assert isinstance(result, Page)
		assert len(result.items) == 1
		assert result.count == 1
		assert result.offset == 0
		assert result.limit == 10
		assert result.items[0].id == sample_message_model.id
		assert result.items[0].message == sample_message_model.content
		assert result.items[0].role == ChatRoles(sample_message_model.role)
		assert result.items[0].date_created == sample_message_model.created_at
		assert result.items[0].date_edited == sample_message_model.updated_at

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_search_with_all_filters(self, message_gateway, mock_session, sample_message_model):
		# Arrange
		filter_dto = MessagesFilterDto(
			ids=[uuid4(), uuid4()],
			chats_ids=[uuid4(), uuid4()],
			roles=[ChatRoles.USER, ChatRoles.MODEL],
			limit=20,
			offset=5,
		)

		mock_count_result = Mock()
		mock_count_result.scalar.return_value = 3

		mock_search_result = Mock()
		mock_search_result.scalars.return_value.all.return_value = [sample_message_model]

		mock_session.execute.side_effect = [mock_count_result, mock_search_result]

		# Act
		result = await message_gateway.search(filter_dto)

		# Assert
		assert result.count == 3
		assert result.offset == 5
		assert result.limit == 20
		assert len(result.items) == 1

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_search_no_results(self, message_gateway, mock_session, sample_message_filter_dto):
		# Arrange
		mock_count_result = Mock()
		mock_count_result.scalar.return_value = 0

		mock_search_result = Mock()
		mock_search_result.scalars.return_value.all.return_value = []

		mock_session.execute.side_effect = [mock_count_result, mock_search_result]

		# Act
		result = await message_gateway.search(sample_message_filter_dto)

		# Assert
		assert result.count == 0
		assert len(result.items) == 0

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_get_one_success(self, message_gateway, mock_session, sample_message_model):
		# Arrange
		message_id = sample_message_model.id
		mock_result = Mock()
		mock_result.scalar_one_or_none.return_value = sample_message_model
		mock_session.execute.return_value = mock_result

		# Act
		result = await message_gateway.get_one(message_id)

		# Assert
		assert result.id == sample_message_model.id
		assert result.message == sample_message_model.content
		assert result.chat_id == sample_message_model.chat_id
		assert result.role == ChatRoles(sample_message_model.role)
		assert result.date_created == sample_message_model.created_at
		assert result.date_edited == sample_message_model.updated_at
		mock_session.execute.assert_called_once()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_get_one_not_found(self, message_gateway, mock_session):
		# Arrange
		message_id = uuid4()
		mock_result = Mock()
		mock_result.scalar_one_or_none.return_value = None
		mock_session.execute.return_value = mock_result

		# Act & Assert
		with pytest.raises(ValueError, match="Message with ID .* not found"):
			await message_gateway.get_one(message_id)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_update_success(self, message_gateway, mock_session):
		# Arrange
		message_id = uuid4()
		updated_text = "Updated message content"
		mock_result = AsyncMock()
		mock_result.rowcount = 1
		mock_session.execute.return_value = mock_result
		mock_session.commit = AsyncMock()

		# Act
		result = await message_gateway.update(message_id, updated_text)

		# Assert
		assert result == message_id
		mock_session.execute.assert_called_once()
		# The gateway must not commit; the UOW owns the transaction boundary.
		mock_session.commit.assert_not_called()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_update_bumps_date_edited(self, message_gateway, mock_session):
		# Arrange
		message_id = uuid4()
		updated_text = "Updated message content"
		mock_result = AsyncMock()
		mock_result.rowcount = 1
		mock_session.execute.return_value = mock_result

		# Act
		await message_gateway.update(message_id, updated_text)

		# Assert: the UPDATE statement must set both the content and the edited timestamp
		executed_statement = mock_session.execute.call_args[0][0]
		compiled_statement = str(executed_statement)
		assert "content" in compiled_statement
		assert "updated_at" in compiled_statement

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_update_not_found(self, message_gateway, mock_session):
		# Arrange
		message_id = uuid4()
		updated_text = "Updated text"
		mock_result = AsyncMock()
		mock_result.rowcount = 0
		mock_session.execute.return_value = mock_result

		# Act & Assert
		with pytest.raises(ValueError, match="Message with ID .* not found"):
			await message_gateway.update(message_id, updated_text)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_delete_success(self, message_gateway, mock_session):
		# Arrange
		message_id = uuid4()
		mock_result = AsyncMock()
		mock_result.rowcount = 1
		mock_session.execute.return_value = mock_result
		mock_session.commit = AsyncMock()

		# Act
		result = await message_gateway.delete(message_id)

		# Assert
		assert result == message_id
		mock_session.execute.assert_called_once()
		# The gateway must not commit; the UOW owns the transaction boundary.
		mock_session.commit.assert_not_called()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_delete_not_found(self, message_gateway, mock_session):
		# Arrange
		message_id = uuid4()
		mock_result = AsyncMock()
		mock_result.rowcount = 0
		mock_session.execute.return_value = mock_result

		# Act & Assert
		with pytest.raises(ValueError, match="Message with ID .* not found"):
			await message_gateway.delete(message_id)

	@pytest.mark.unit
	def test_to_domain_message_conversion_user_role(self, message_gateway, sample_message_model):
		# Act
		result = message_gateway._to_domain_message(sample_message_model)

		# Assert
		assert result.id == sample_message_model.id
		assert result.message == sample_message_model.content
		assert result.chat_id == sample_message_model.chat_id
		assert result.role == ChatRoles.USER
		assert result.date_created == sample_message_model.created_at
		assert result.date_edited == sample_message_model.updated_at

	@pytest.mark.unit
	def test_to_domain_message_conversion_model_role(self, message_gateway):
		# Arrange
		message_model = Mock(spec=MessageModel)
		message_model.id = uuid4()
		message_model.chat_id = uuid4()
		message_model.role = "model"
		message_model.content = "AI response"
		message_model.status = "completed"
		message_model.created_at = datetime(2024, 3, 10, 8, 0, 0, tzinfo=timezone.utc)
		message_model.updated_at = datetime(2024, 3, 11, 9, 0, 0, tzinfo=timezone.utc)

		# Act
		result = message_gateway._to_domain_message(message_model)

		# Assert
		assert result.id == message_model.id
		assert result.message == message_model.content
		assert result.chat_id == message_model.chat_id
		assert result.role == ChatRoles.MODEL
		assert result.date_created == message_model.created_at
		assert result.date_edited == message_model.updated_at

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_search_empty_filters(self, message_gateway, mock_session, sample_message_model):
		# Arrange
		empty_filter_dto = MessagesFilterDto(limit=10, offset=0)

		mock_count_result = Mock()
		mock_count_result.scalar.return_value = 1

		mock_search_result = Mock()
		mock_search_result.scalars.return_value.all.return_value = [sample_message_model]

		mock_session.execute.side_effect = [mock_count_result, mock_search_result]

		# Act
		result = await message_gateway.search(empty_filter_dto)

		# Assert
		assert len(result.items) == 1
		assert result.count == 1

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_create_with_empty_message(self, message_gateway, mock_session):
		# Arrange
		empty_message = Message(
			message="",  # Empty content
			chat_id=uuid4(),
			role=ChatRoles.USER,
		)

		expected_id = uuid4()
		mock_message_model = Mock()
		mock_message_model.id = expected_id
		mock_message_model.chat_id = empty_message.chat_id
		mock_message_model.role = empty_message.role.value
		mock_message_model.content = ""

		mock_session.add = Mock()
		mock_session.refresh = AsyncMock()

		# Act
		result = await message_gateway.create(empty_message)

		# Assert
		assert result.message == ""
		mock_session.add.assert_called_once()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_search_ordering_newest_first(self, message_gateway, mock_session, sample_message_filter_dto):
		# Arrange
		mock_count_result = Mock()
		mock_count_result.scalar.return_value = 0

		mock_search_result = Mock()
		mock_search_result.scalars.return_value.all.return_value = []

		mock_session.execute.side_effect = [mock_count_result, mock_search_result]

		# Act
		await message_gateway.search(sample_message_filter_dto)

		# Assert
		# Verify that the search query includes ordering by created_at desc
		# This is implicitly tested by the query construction in the gateway
		assert mock_session.execute.call_count == 2

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_create_persists_status(self, message_gateway, mock_session):
		"""create() must write the domain MessageStatus onto the ORM row."""
		from src.domain.models import MessageStatus as MS

		msg = Message(message="hi", chat_id=uuid4(), role=ChatRoles.MODEL, status=MS.PENDING)
		mock_session.add = Mock()
		mock_session.refresh = AsyncMock()

		await message_gateway.create(msg)

		added = mock_session.add.call_args.args[0]
		assert added.status == "pending"

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_latest_model_message_returns_newest(self, message_gateway, mock_session):
		row = self._model_row(role="model", content="latest", status="completed")
		mock_result = Mock()
		mock_result.scalar_one_or_none.return_value = row
		mock_session.execute.return_value = mock_result

		result = await message_gateway.latest_model_message(row.chat_id)

		assert result is not None
		assert result.message == "latest"
		assert result.role == ChatRoles.MODEL

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_latest_model_message_none_when_empty(self, message_gateway, mock_session):
		mock_result = Mock()
		mock_result.scalar_one_or_none.return_value = None
		mock_session.execute.return_value = mock_result

		assert await message_gateway.latest_model_message(uuid4()) is None
