import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import HTTPException

from src.application.auth.authz import AuthorizationService
from src.application.chats.service import ChatService
from src.application.chats.schemas import ChatFilterDTO
from src.application.ports.chats import IChatGateway
from src.application.ports.messages import IMessageGateway
from src.application.ports.scenes import IInitialMessageGateway
from src.application.ports.common import IUnitOfWork, Page
from src.domain.models import Chat, ChatRoles, Message, MessageStatus, InitialMessage


class TestChatService:
	@pytest.fixture
	def authz(self):
		return AuthorizationService()

	@pytest.fixture
	def mock_chat_gateway(self):
		return AsyncMock(spec=IChatGateway)

	@pytest.fixture
	def mock_initial_message_gateway(self):
		return AsyncMock(spec=IInitialMessageGateway)

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
	def chat_service(self, mock_chat_gateway, mock_initial_message_gateway, mock_message_gateway, mock_uow, authz):
		return ChatService(
			chat_gateway=mock_chat_gateway,
			initial_message_gateway=mock_initial_message_gateway,
			message_gateway=mock_message_gateway,
			uow=mock_uow,
			authz=authz,
		)

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

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_choose_initial_message_seeds_greeting_and_sets_column(
		self, chat_service, mock_chat_gateway, mock_initial_message_gateway, mock_message_gateway, mock_uow, sample_chat
	):
		# Arrange: chat not yet chosen (initial_message_id is None by default),
		# initial message belongs to the chat's scene.
		initial_message = InitialMessage(id=uuid4(), scene_id=sample_chat.scene_id, text="Welcome!")
		mock_chat_gateway.get_one.return_value = sample_chat
		mock_initial_message_gateway.get_one.return_value = initial_message
		seeded = Message(id=uuid4(), message="Welcome!", chat_id=sample_chat.id, role=ChatRoles.MODEL)
		mock_message_gateway.create.return_value = seeded

		# Act
		result = await chat_service.choose_initial_message(sample_chat.id, initial_message.id, sample_chat.user_id)

		# Assert: the choice is recorded and a model greeting seeded in one tx.
		assert result is seeded
		mock_chat_gateway.set_initial_message.assert_called_once_with(sample_chat.id, initial_message.id)
		mock_message_gateway.create.assert_called_once()
		created = mock_message_gateway.create.call_args.args[0]
		assert created.message == "Welcome!"
		assert created.role == ChatRoles.MODEL
		assert created.status == MessageStatus.COMPLETED
		assert created.chat_id == sample_chat.id

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_choose_initial_message_wrong_scene_rejected(
		self, chat_service, mock_chat_gateway, mock_initial_message_gateway, mock_message_gateway, sample_chat
	):
		# initial message belongs to a different scene than the chat
		initial_message = InitialMessage(id=uuid4(), scene_id=uuid4(), text="Welcome!")
		mock_chat_gateway.get_one.return_value = sample_chat
		mock_initial_message_gateway.get_one.return_value = initial_message

		with pytest.raises(ValueError, match="does not belong to this chat"):
			await chat_service.choose_initial_message(sample_chat.id, initial_message.id, sample_chat.user_id)

		mock_chat_gateway.set_initial_message.assert_not_called()
		mock_message_gateway.create.assert_not_called()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_choose_initial_message_already_chosen_rejected(
		self, chat_service, mock_chat_gateway, mock_initial_message_gateway, mock_message_gateway, sample_chat
	):
		# A chat that already has an initial message cannot pick another.
		chat = Chat(
			id=sample_chat.id,
			title=sample_chat.title,
			user_id=sample_chat.user_id,
			scene_id=sample_chat.scene_id,
			initial_message_id=uuid4(),
		)
		initial_message = InitialMessage(id=chat.initial_message_id, scene_id=chat.scene_id, text="Welcome!")
		mock_chat_gateway.get_one.return_value = chat
		mock_initial_message_gateway.get_one.return_value = initial_message

		with pytest.raises(ValueError, match="already has an initial message"):
			await chat_service.choose_initial_message(chat.id, uuid4(), chat.user_id)

		mock_chat_gateway.set_initial_message.assert_not_called()
		mock_message_gateway.create.assert_not_called()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_choose_initial_message_not_owner_raises_403(
		self, chat_service, mock_chat_gateway, mock_initial_message_gateway, mock_message_gateway, sample_chat
	):
		mock_chat_gateway.get_one.return_value = sample_chat

		with pytest.raises(HTTPException) as exc:
			await chat_service.choose_initial_message(sample_chat.id, uuid4(), uuid4())  # not the owner
		assert exc.value.status_code == 403

		mock_initial_message_gateway.get_one.assert_not_called()
		mock_message_gateway.create.assert_not_called()
