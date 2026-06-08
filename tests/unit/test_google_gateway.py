import json
import pytest
from unittest.mock import Mock

from src.infrastructure.gateways.google_gateway import GoogleGateway
from src.infrastructure.exceptions import JSONParsingException, ContentSafetyException, LLMGatewayException

genai = pytest.importorskip("google.generativeai")


@pytest.mark.unit
class TestGoogleGateway:
	"""Unit tests for GoogleGateway"""

	@pytest.fixture
	def mock_chat_session(self):
		"""Mock ChatSession for testing"""
		return Mock(spec=genai.ChatSession)

	@pytest.fixture
	def mock_client(self, mock_chat_session):
		"""Mock GenerativeModel client for testing"""
		client = Mock(spec=genai.GenerativeModel)
		client.start_chat.return_value = mock_chat_session
		return client

	@pytest.fixture
	def mock_logger(self):
		"""Mock logger for testing"""
		return Mock()

	@pytest.fixture
	def google_gateway(self, mock_client, mock_logger):
		"""GoogleGateway instance with mocked dependencies"""
		return GoogleGateway(_client=mock_client, logger=mock_logger)

	@pytest.mark.asyncio
	async def test_generate_response_success(self, google_gateway, mock_chat_session, mock_logger):
		"""Test successful response generation"""
		# Arrange
		user_message = "Hello, how are you?"
		expected_response = {"text": "I'm doing well, thank you!", "model": "gemini"}

		mock_response = Mock()
		mock_response.text = json.dumps(expected_response)
		mock_chat_session.send_message.return_value = mock_response

		# Act
		result = await google_gateway.generate_response(user_message)

		# Assert
		assert result == expected_response
		mock_chat_session.send_message.assert_called_once_with(user_message)

	@pytest.mark.asyncio
	async def test_generate_response_json_parsing_error(self, google_gateway, mock_chat_session, mock_logger):
		"""Test response generation with JSON parsing error"""
		# Arrange
		user_message = "Hello"
		mock_response = Mock()
		mock_response.text = "Invalid JSON response"
		mock_chat_session.send_message.return_value = mock_response

		# Act & Assert
		with pytest.raises(JSONParsingException) as exc_info:
			await google_gateway.generate_response(user_message)

		exception = exc_info.value
		assert "Сбой парсинга JSON ответа от LLM" in str(exception)
		assert exception.details["response_text"] == "Invalid JSON response"
		assert "original_error" in exception.details

		mock_logger.error.assert_called_once_with("[Ошибка]: Сбой парсинга JSON.")

	@pytest.mark.asyncio
	async def test_generate_response_content_safety_exception(self, google_gateway, mock_chat_session, mock_logger):
		"""Test response generation blocked by content safety filters"""
		# Arrange
		user_message = "Inappropriate content"
		mock_chat_session.send_message.side_effect = genai.types.generation_types.StopCandidateException(
			"Content blocked by safety filters"
		)

		# Act & Assert
		with pytest.raises(ContentSafetyException) as exc_info:
			await google_gateway.generate_response(user_message)

		exception = exc_info.value
		assert "Ответ заблокирован фильтрами безопасности Gemini" in str(exception)
		assert "original_error" in exception.details

		mock_logger.error.assert_called_once_with("[Ошибка]: Ответ заблокирован фильтрами безопасности Gemini.")

	@pytest.mark.asyncio
	async def test_generate_response_general_exception(self, google_gateway, mock_chat_session, mock_logger):
		"""Test response generation with general exception"""
		# Arrange
		user_message = "Hello"
		error_message = "Network error"
		mock_chat_session.send_message.side_effect = Exception(error_message)

		# Act & Assert
		with pytest.raises(LLMGatewayException) as exc_info:
			await google_gateway.generate_response(user_message)

		exception = exc_info.value
		assert f"Ошибка шлюза LLM: {error_message}" in str(exception)
		assert exception.details["original_error"] == error_message
		assert exception.details["error_type"] == "Exception"

		mock_logger.error.assert_called_once_with(f"[Ошибка]: {error_message}")

	@pytest.mark.asyncio
	async def test_generate_response_complex_json(self, google_gateway, mock_chat_session):
		"""Test response generation with complex JSON structure"""
		# Arrange
		user_message = "Generate complex response"
		complex_response = {
			"text": "Complex response text",
			"model": "gemini-pro",
			"usage": {"input_tokens": 10, "output_tokens": 20},
			"metadata": {"safety_scores": {"harassment": 0.1, "hate": 0.05}, "finish_reason": "stop"},
		}

		mock_response = Mock()
		mock_response.text = json.dumps(complex_response)
		mock_chat_session.send_message.return_value = mock_response

		# Act
		result = await google_gateway.generate_response(user_message)

		# Assert
		assert result == complex_response
		assert result["usage"]["input_tokens"] == 10
		assert result["metadata"]["safety_scores"]["harassment"] == 0.1

	@pytest.mark.asyncio
	async def test_generate_response_empty_json(self, google_gateway, mock_chat_session):
		"""Test response generation with empty JSON"""
		# Arrange
		user_message = "Hello"
		empty_response = {}

		mock_response = Mock()
		mock_response.text = json.dumps(empty_response)
		mock_chat_session.send_message.return_value = mock_response

		# Act
		result = await google_gateway.generate_response(user_message)

		# Assert
		assert result == empty_response

	@pytest.mark.asyncio
	async def test_generate_response_json_with_unicode(self, google_gateway, mock_chat_session):
		"""Test response generation with Unicode characters in JSON"""
		# Arrange
		user_message = "Hello in different languages"
		unicode_response = {"text": "Привет! 你好! こんにちは! 🌍", "language": "multilingual"}

		mock_response = Mock()
		mock_response.text = json.dumps(unicode_response, ensure_ascii=False)
		mock_chat_session.send_message.return_value = mock_response

		# Act
		result = await google_gateway.generate_response(user_message)

		# Assert
		assert result == unicode_response
		assert "Привет!" in result["text"]
		assert "🌍" in result["text"]

	@pytest.mark.asyncio
	async def test_generate_response_json_with_null_values(self, google_gateway, mock_chat_session):
		"""Test response generation with null values in JSON"""
		# Arrange
		user_message = "Hello"
		response_with_nulls = {"text": "Response text", "optional_field": None, "empty_list": [], "zero_value": 0}

		mock_response = Mock()
		mock_response.text = json.dumps(response_with_nulls)
		mock_chat_session.send_message.return_value = mock_response

		# Act
		result = await google_gateway.generate_response(user_message)

		# Assert
		assert result == response_with_nulls
		assert result["optional_field"] is None
		assert result["empty_list"] == []
		assert result["zero_value"] == 0

	def test_dataclass_attributes(self, google_gateway, mock_client, mock_logger):
		"""Test that GoogleGateway dataclass attributes are accessible"""
		# Assert
		assert google_gateway._client == mock_client
		assert google_gateway.logger == mock_logger
