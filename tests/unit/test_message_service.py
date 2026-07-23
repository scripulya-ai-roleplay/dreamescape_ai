import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import HTTPException

from src.application.auth.authz import AuthorizationService
from src.application.message.service import MessageService
from src.application.message.schemas import MessagesFilterDto
from src.application.ports.messages import IMessageGateway
from src.application.ports.common import IUnitOfWork, Page
from src.application.ports.llm import LLMErrorResponse, LLMResult, UserMessageDTO
from src.domain.models import Message, ChatRoles, MessageStatus


class TestMessageService:
	@pytest.fixture
	def authz(self):
		return AuthorizationService()

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
	def message_service(self, mock_message_gateway, mock_uow, authz):
		return MessageService(message_gateway=mock_message_gateway, _uow=mock_uow, authz=authz)

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

	def _stub_owned(self, mock_message_gateway, sample_message, actor_id):
		"""Wire the gateway so the message resolves to an actor-owned chat."""
		mock_message_gateway.get_one.return_value = sample_message
		mock_message_gateway.get_chat_owner_for_message.return_value = actor_id

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
		actor_id = uuid4()
		expected_page = Page[Message](items=[sample_message], count=1, offset=0, limit=10)
		mock_message_gateway.search.return_value = expected_page

		# Act
		result = await message_service.search(sample_message_filter_dto, actor_id)

		# Assert
		assert result == expected_page
		mock_message_gateway.search.assert_called_once_with(sample_message_filter_dto, actor_id=actor_id)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_get_one_owner_ok(self, message_service, mock_message_gateway, sample_message):
		# Arrange
		actor_id = uuid4()
		message_id = sample_message.id
		self._stub_owned(mock_message_gateway, sample_message, actor_id)

		# Act
		result = await message_service.get_one(message_id, actor_id)

		# Assert
		assert result == sample_message
		mock_message_gateway.get_one.assert_called_once_with(message_id)
		mock_message_gateway.get_chat_owner_for_message.assert_called_once_with(message_id)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_get_one_not_owner_raises_403(self, message_service, mock_message_gateway, sample_message):
		# The message's chat belongs to someone else.
		mock_message_gateway.get_one.return_value = sample_message
		mock_message_gateway.get_chat_owner_for_message.return_value = uuid4()

		with pytest.raises(HTTPException) as exc:
			await message_service.get_one(sample_message.id, uuid4())
		assert exc.value.status_code == 403

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_update_success(self, message_service, mock_message_gateway, sample_message):
		# Arrange
		actor_id = uuid4()
		message_id = sample_message.id
		updated_text = "Updated message text"
		self._stub_owned(mock_message_gateway, sample_message, actor_id)
		mock_message_gateway.update.return_value = message_id

		# Act
		result = await message_service.update(message_id, updated_text, actor_id)

		# Assert
		assert result == message_id
		mock_message_gateway.update.assert_called_once_with(message_id, updated_text)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_update_not_owner_raises_403_without_updating(
		self, message_service, mock_message_gateway, sample_message
	):
		mock_message_gateway.get_one.return_value = sample_message
		mock_message_gateway.get_chat_owner_for_message.return_value = uuid4()

		with pytest.raises(HTTPException) as exc:
			await message_service.update(sample_message.id, "x", uuid4())
		assert exc.value.status_code == 403

		mock_message_gateway.update.assert_not_called()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_delete_success(self, message_service, mock_message_gateway, sample_message):
		# Arrange
		actor_id = uuid4()
		message_id = sample_message.id
		self._stub_owned(mock_message_gateway, sample_message, actor_id)
		mock_message_gateway.delete.return_value = message_id

		# Act
		result = await message_service.delete(message_id, actor_id)

		# Assert
		assert result == message_id
		mock_message_gateway.delete.assert_called_once_with(message_id)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_delete_not_owner_raises_403_without_deleting(
		self, message_service, mock_message_gateway, sample_message
	):
		mock_message_gateway.get_one.return_value = sample_message
		mock_message_gateway.get_chat_owner_for_message.return_value = uuid4()

		with pytest.raises(HTTPException) as exc:
			await message_service.delete(sample_message.id, uuid4())
		assert exc.value.status_code == 403

		mock_message_gateway.delete.assert_not_called()

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
			await message_service.get_one(message_id, uuid4())

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_search_empty_results(self, message_service, mock_message_gateway, sample_message_filter_dto):
		# Arrange
		actor_id = uuid4()
		empty_page = Page[Message](items=[], count=0, offset=0, limit=10)
		mock_message_gateway.search.return_value = empty_page

		# Act
		result = await message_service.search(sample_message_filter_dto, actor_id)

		# Assert
		assert result.items == []
		assert result.count == 0
		mock_message_gateway.search.assert_called_once_with(sample_message_filter_dto, actor_id=actor_id)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_update_not_found(self, message_service, mock_message_gateway, sample_message):
		# Arrange: owned check passes, but the row is gone at update time.
		actor_id = uuid4()
		self._stub_owned(mock_message_gateway, sample_message, actor_id)
		mock_message_gateway.update.side_effect = ValueError("Message not found")

		# Act & Assert
		with pytest.raises(ValueError, match="Message not found"):
			await message_service.update(sample_message.id, "Updated text", actor_id)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_delete_not_found(self, message_service, mock_message_gateway, sample_message):
		# Arrange
		actor_id = uuid4()
		self._stub_owned(mock_message_gateway, sample_message, actor_id)
		mock_message_gateway.delete.side_effect = ValueError("Message not found")

		# Act & Assert
		with pytest.raises(ValueError, match="Message not found"):
			await message_service.delete(sample_message.id, actor_id)

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

		expected_page = Page[Message](items=[model_message], count=1, offset=5, limit=5)
		mock_message_gateway.search.return_value = expected_page

		# Act
		actor_id = uuid4()
		result = await message_service.search(filter_dto, actor_id)

		# Assert
		assert result == expected_page
		assert result.items[0].role == ChatRoles.MODEL
		mock_message_gateway.search.assert_called_once_with(filter_dto, actor_id=actor_id)

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

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_append_model_message_success(self, message_service, mock_message_gateway):
		chat_id = uuid4()
		result = LLMResult(
			chat_id=chat_id,
			message=UserMessageDTO(chat_id=chat_id, message="hello back", role=ChatRoles.MODEL),
		)
		persisted = Message(
			id=uuid4(), message="hello back", chat_id=chat_id, role=ChatRoles.MODEL, status=MessageStatus.COMPLETED
		)
		mock_message_gateway.create.return_value = persisted

		got = await message_service.append_model_message(result)

		assert got is persisted
		sent = mock_message_gateway.create.await_args.args[0]
		assert sent.role == ChatRoles.MODEL
		assert sent.status == MessageStatus.COMPLETED
		assert sent.message == "hello back"
		assert sent.chat_id == chat_id

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_append_model_message_error_marks_failed(self, message_service, mock_message_gateway):
		chat_id = uuid4()
		result = LLMResult(
			chat_id=chat_id,
			error=LLMErrorResponse(error_code="model_is_inaccessible", status=503, reason="r", message="nope"),
		)
		persisted = Message(
			id=uuid4(), message="nope", chat_id=chat_id, role=ChatRoles.MODEL, status=MessageStatus.FAILED
		)
		mock_message_gateway.create.return_value = persisted

		got = await message_service.append_model_message(result)

		assert got is persisted
		sent = mock_message_gateway.create.await_args.args[0]
		assert sent.role == ChatRoles.MODEL
		assert sent.status == MessageStatus.FAILED
		assert sent.message == "nope"

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_append_model_message_neither_message_nor_error(self, message_service, mock_message_gateway):
		# An empty result is persisted as a FAILED row rather than silently dropped.
		chat_id = uuid4()
		result = LLMResult(chat_id=chat_id, message=None, error=None)

		await message_service.append_model_message(result)

		sent = mock_message_gateway.create.await_args.args[0]
		assert sent.chat_id == chat_id
		assert sent.role == ChatRoles.MODEL
		assert sent.status == MessageStatus.FAILED

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_record_failed_generation_persists_failed_row(self, message_service, mock_message_gateway):
		# Out-of-band FAILED turn (no LLMResult) — used by the heartbeat watchdog.
		chat_id = uuid4()
		persisted = Message(
			id=uuid4(), message="timed out", chat_id=chat_id, role=ChatRoles.MODEL, status=MessageStatus.FAILED
		)
		mock_message_gateway.create.return_value = persisted

		got = await message_service.record_failed_generation(chat_id, "timed out")

		assert got is persisted
		sent = mock_message_gateway.create.await_args.args[0]
		assert sent.chat_id == chat_id
		assert sent.role == ChatRoles.MODEL
		assert sent.status == MessageStatus.FAILED
		assert sent.message == "timed out"

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_latest_model_message_delegates(self, message_service, mock_message_gateway):
		chat_id = uuid4()
		await message_service.latest_model_message(chat_id)
		mock_message_gateway.latest_model_message.assert_called_once_with(chat_id)
