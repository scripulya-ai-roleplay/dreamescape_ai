import pytest
from unittest.mock import AsyncMock, MagicMock

from uuid import uuid4

from src.application.chats.llm_service import LLMChatsService
from src.application.ports import UserMessageDTO, LLMModelType, IGatewayFactory, ILLMChatGateway, IMessageGateway, Page
from src.domain.models import ChatRoles, Message


class TestChatsService:
	@pytest.fixture
	def mock_gateway(self):
		"""Mock gateway that simulates LLM response generation."""
		gateway = AsyncMock(spec=ILLMChatGateway)
		gateway.generate_response.return_value = {
			"text": "This is a test response from the LLM",
			"model": "test-model",
			"usage": {"tokens": 50},
		}
		return gateway

	@pytest.fixture
	def mock_gateway_factory(self, mock_gateway):
		"""Mock gateway factory that creates gateways."""
		factory = MagicMock(spec=IGatewayFactory)
		factory.create_gateway.return_value = mock_gateway
		return factory

	@pytest.fixture
	def mock_messages_gateway(self):
		"""Mock messages gateway for history retrieval."""
		gateway = AsyncMock(spec=IMessageGateway)
		gateway.search.return_value = Page[Message](items=[], count=0, offset=0, limit=10)
		return gateway

	@pytest.fixture
	def chats_service(self, mock_gateway_factory, mock_messages_gateway):
		"""LLMChatsService instance with mocked dependencies."""
		return LLMChatsService(gateway_factory=mock_gateway_factory, messages_gateway=mock_messages_gateway)

	@pytest.fixture
	def sample_chat_id(self):
		return uuid4()

	@pytest.fixture
	def sample_user_message_dto(self, sample_chat_id):
		"""Sample UserMessageDTO for testing."""
		return UserMessageDTO(
			message="Hello, how are you?",
			llm_model=LLMModelType.gemini_flash_preview,
			chat_id=sample_chat_id,
			role=ChatRoles.USER,
		)

	@pytest.fixture
	def sample_mock_message_dto(self, sample_chat_id):
		"""Sample UserMessageDTO with mock model for testing."""
		return UserMessageDTO(
			message="Test message for mock model",
			llm_model=LLMModelType.testing_mock,
			chat_id=sample_chat_id,
			role=ChatRoles.USER,
		)

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_send_message_success_gemini(
		self, chats_service, mock_gateway_factory, mock_gateway, sample_user_message_dto
	):
		"""Test successful message sending with Gemini model."""
		# Act
		result = await chats_service.send_message(sample_user_message_dto)

		# Assert
		mock_gateway_factory.create_gateway.assert_called_once_with("gemini-3-flash-preview")
		mock_gateway.generate_response.assert_called_once_with("Hello, how are you?", [])
		assert result == {
			"text": "This is a test response from the LLM",
			"model": "test-model",
			"usage": {"tokens": 50},
		}

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_send_message_success_mock_model(
		self, chats_service, mock_gateway_factory, mock_gateway, sample_mock_message_dto
	):
		"""Test successful message sending with mock model."""
		# Act
		result = await chats_service.send_message(sample_mock_message_dto)

		# Assert
		mock_gateway_factory.create_gateway.assert_called_once_with("testing_mock")
		mock_gateway.generate_response.assert_called_once_with("Test message for mock model", [])
		assert result == {
			"text": "This is a test response from the LLM",
			"model": "test-model",
			"usage": {"tokens": 50},
		}

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_send_message_empty_message(self, chats_service, mock_gateway_factory, mock_gateway):
		"""Test sending an empty message."""
		# Arrange
		empty_message_dto = UserMessageDTO(
			message="", llm_model=LLMModelType.gemini_flash_preview, chat_id=uuid4(), role=ChatRoles.USER
		)

		# Act
		result = await chats_service.send_message(empty_message_dto)

		# Assert
		mock_gateway_factory.create_gateway.assert_called_once_with("gemini-3-flash-preview")
		mock_gateway.generate_response.assert_called_once_with("", [])
		assert result == {
			"text": "This is a test response from the LLM",
			"model": "test-model",
			"usage": {"tokens": 50},
		}

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_send_message_long_message(self, chats_service, mock_gateway_factory, mock_gateway):
		"""Test sending a long message."""
		# Arrange
		long_message = "This is a very long message " * 100
		long_message_dto = UserMessageDTO(
			message=long_message, llm_model=LLMModelType.gemini_flash_preview, chat_id=uuid4(), role=ChatRoles.USER
		)

		# Act
		result = await chats_service.send_message(long_message_dto)

		# Assert
		mock_gateway_factory.create_gateway.assert_called_once_with("gemini-3-flash-preview")
		mock_gateway.generate_response.assert_called_once_with(long_message, [])
		assert result == {
			"text": "This is a test response from the LLM",
			"model": "test-model",
			"usage": {"tokens": 50},
		}

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_send_message_gateway_factory_error(
		self, mock_gateway_factory, mock_messages_gateway, sample_user_message_dto
	):
		"""Test error handling when gateway factory fails."""
		# Arrange
		mock_gateway_factory.create_gateway.side_effect = Exception("Gateway creation failed")
		chats_service = LLMChatsService(gateway_factory=mock_gateway_factory, messages_gateway=mock_messages_gateway)

		# Act & Assert
		with pytest.raises(Exception) as exc_info:
			await chats_service.send_message(sample_user_message_dto)

		assert str(exc_info.value) == "Gateway creation failed"
		mock_gateway_factory.create_gateway.assert_called_once_with("gemini-3-flash-preview")

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_send_message_gateway_response_error(
		self, chats_service, mock_gateway_factory, mock_gateway, sample_user_message_dto
	):
		"""Test error handling when gateway response generation fails."""
		# Arrange
		mock_gateway.generate_response.side_effect = Exception("Response generation failed")

		# Act & Assert
		with pytest.raises(Exception) as exc_info:
			await chats_service.send_message(sample_user_message_dto)

		assert str(exc_info.value) == "Response generation failed"
		mock_gateway_factory.create_gateway.assert_called_once_with("gemini-3-flash-preview")
		mock_gateway.generate_response.assert_called_once_with("Hello, how are you?", [])

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_send_message_different_response_format(
		self, chats_service, mock_gateway_factory, mock_gateway, sample_user_message_dto
	):
		"""Test handling different response formats from gateway."""
		# Arrange
		mock_gateway.generate_response.return_value = {
			"response": "Different format response",
			"metadata": {"source": "test"},
		}

		# Act
		result = await chats_service.send_message(sample_user_message_dto)

		# Assert
		mock_gateway_factory.create_gateway.assert_called_once_with("gemini-3-flash-preview")
		mock_gateway.generate_response.assert_called_once_with("Hello, how are you?", [])
		assert result == {"response": "Different format response", "metadata": {"source": "test"}}

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_send_message_special_characters(self, chats_service, mock_gateway_factory, mock_gateway):
		"""Test sending message with special characters."""
		# Arrange
		special_message = "Hello! 🚀 How are you? @#$%^&*()_+-=[]{}|;':\",./<>?"
		special_message_dto = UserMessageDTO(
			message=special_message, llm_model=LLMModelType.testing_mock, chat_id=uuid4(), role=ChatRoles.USER
		)

		# Act
		result = await chats_service.send_message(special_message_dto)

		# Assert
		mock_gateway_factory.create_gateway.assert_called_once_with("testing_mock")
		mock_gateway.generate_response.assert_called_once_with(special_message, [])
		assert result == {
			"text": "This is a test response from the LLM",
			"model": "test-model",
			"usage": {"tokens": 50},
		}

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_send_message_unicode_characters(self, chats_service, mock_gateway_factory, mock_gateway):
		"""Test sending message with unicode characters."""
		# Arrange
		unicode_message = "你好世界! Привет мир! مرحبا بالعالم!"
		unicode_message_dto = UserMessageDTO(
			message=unicode_message, llm_model=LLMModelType.gemini_flash_preview, chat_id=uuid4(), role=ChatRoles.USER
		)

		# Act
		result = await chats_service.send_message(unicode_message_dto)

		# Assert
		mock_gateway_factory.create_gateway.assert_called_once_with("gemini-3-flash-preview")
		mock_gateway.generate_response.assert_called_once_with(unicode_message, [])
		assert result == {
			"text": "This is a test response from the LLM",
			"model": "test-model",
			"usage": {"tokens": 50},
		}
