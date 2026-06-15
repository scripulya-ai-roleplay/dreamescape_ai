import json
import pytest
from unittest.mock import AsyncMock, Mock

from src.infrastructure.gateways.google_gateway import GoogleGateway
from src.infrastructure.exceptions import JSONParsingException, ContentSafetyException, LLMGatewayException

genai = pytest.importorskip("google.genai")
from google.genai import types  # noqa: E402


def _make_response(text: str, finish_reason: types.FinishReason = types.FinishReason.STOP) -> Mock:
	candidate = Mock()
	candidate.finish_reason = finish_reason
	response = Mock()
	response.text = text
	response.candidates = [candidate]
	return response


@pytest.mark.unit
class TestGoogleGateway:
	"""Unit tests for GoogleGateway"""

	@pytest.fixture
	def mock_chat(self):
		"""Mock async chat session"""
		chat = Mock()
		chat.send_message = AsyncMock()
		return chat

	@pytest.fixture
	def mock_client(self, mock_chat):
		"""Mock genai.Client for testing"""
		client = Mock(spec=genai.Client)
		client.aio.chats.create.return_value = mock_chat
		return client

	@pytest.fixture
	def mock_logger(self):
		"""Mock logger for testing"""
		return Mock()

	@pytest.fixture
	def mock_config(self):
		"""Mock GenerateContentConfig"""
		return Mock(spec=types.GenerateContentConfig)

	@pytest.fixture
	def google_gateway(self, mock_client, mock_logger, mock_config):
		"""GoogleGateway instance with mocked dependencies"""
		return GoogleGateway(
			logger=mock_logger,
			_client=mock_client,
			_model_name="gemini-3-flash-preview",
			_config=mock_config,
		)

	@pytest.mark.asyncio
	async def test_generate_response_success(self, google_gateway, mock_chat, mock_logger):
		"""Test successful response generation"""
		# Arrange
		user_message = "Hello, how are you?"
		expected_response = {"text": "I'm doing well, thank you!", "model": "gemini"}
		mock_chat.send_message.return_value = _make_response(json.dumps(expected_response))

		# Act
		result = await google_gateway.generate_response(user_message)

		# Assert
		assert result == expected_response
		mock_chat.send_message.assert_awaited_once_with(user_message)

	@pytest.mark.asyncio
	async def test_generate_response_json_parsing_error(self, google_gateway, mock_chat, mock_logger):
		"""Test response generation with JSON parsing error"""
		# Arrange
		user_message = "Hello"
		mock_chat.send_message.return_value = _make_response("Invalid JSON response")

		# Act & Assert
		with pytest.raises(JSONParsingException) as exc_info:
			await google_gateway.generate_response(user_message)

		exception = exc_info.value
		assert "Сбой парсинга JSON ответа от LLM" in str(exception)
		assert exception.details["response_text"] == "Invalid JSON response"
		assert "original_error" in exception.details

		mock_logger.error.assert_called_once_with("[Ошибка]: Сбой парсинга JSON.")

	@pytest.mark.asyncio
	async def test_generate_response_content_safety_exception(self, google_gateway, mock_chat, mock_logger):
		"""Test response generation blocked by content safety filters"""
		# Arrange
		user_message = "Inappropriate content"
		mock_chat.send_message.return_value = _make_response(text="", finish_reason=types.FinishReason.SAFETY)

		# Act & Assert
		with pytest.raises(ContentSafetyException) as exc_info:
			await google_gateway.generate_response(user_message)

		exception = exc_info.value
		assert "Ответ заблокирован фильтрами безопасности Gemini" in str(exception)
		assert "finish_reason" in exception.details

		mock_logger.error.assert_called_once_with("[Ошибка]: Ответ заблокирован фильтрами безопасности Gemini.")

	@pytest.mark.asyncio
	async def test_generate_response_general_exception(self, google_gateway, mock_chat, mock_logger):
		"""Test response generation with general exception"""
		# Arrange
		user_message = "Hello"
		error_message = "Network error"
		mock_chat.send_message.side_effect = Exception(error_message)

		# Act & Assert
		with pytest.raises(LLMGatewayException) as exc_info:
			await google_gateway.generate_response(user_message)

		exception = exc_info.value
		assert f"Ошибка шлюза LLM: {error_message}" in str(exception)
		assert exception.details["original_error"] == error_message
		assert exception.details["error_type"] == "Exception"

		mock_logger.error.assert_called_once_with(f"[Ошибка]: {error_message}")

	@pytest.mark.asyncio
	async def test_generate_response_complex_json(self, google_gateway, mock_chat):
		"""Test response generation with complex JSON structure"""
		# Arrange
		user_message = "Generate complex response"
		complex_response = {
			"text": "Complex response text",
			"model": "gemini-pro",
			"usage": {"input_tokens": 10, "output_tokens": 20},
			"metadata": {"safety_scores": {"harassment": 0.1, "hate": 0.05}, "finish_reason": "stop"},
		}
		mock_chat.send_message.return_value = _make_response(json.dumps(complex_response))

		# Act
		result = await google_gateway.generate_response(user_message)

		# Assert
		assert result == complex_response
		assert result["usage"]["input_tokens"] == 10
		assert result["metadata"]["safety_scores"]["harassment"] == 0.1

	@pytest.mark.asyncio
	async def test_generate_response_empty_json(self, google_gateway, mock_chat):
		"""Test response generation with empty JSON"""
		# Arrange
		user_message = "Hello"
		empty_response = {}
		mock_chat.send_message.return_value = _make_response(json.dumps(empty_response))

		# Act
		result = await google_gateway.generate_response(user_message)

		# Assert
		assert result == empty_response

	@pytest.mark.asyncio
	async def test_generate_response_json_with_unicode(self, google_gateway, mock_chat):
		"""Test response generation with Unicode characters in JSON"""
		# Arrange
		user_message = "Hello in different languages"
		unicode_response = {"text": "Привет! 你好! こんにちは! 🌍", "language": "multilingual"}
		mock_chat.send_message.return_value = _make_response(json.dumps(unicode_response, ensure_ascii=False))

		# Act
		result = await google_gateway.generate_response(user_message)

		# Assert
		assert result == unicode_response
		assert "Привет!" in result["text"]
		assert "🌍" in result["text"]

	@pytest.mark.asyncio
	async def test_generate_response_json_with_null_values(self, google_gateway, mock_chat):
		"""Test response generation with null values in JSON"""
		# Arrange
		user_message = "Hello"
		response_with_nulls = {"text": "Response text", "optional_field": None, "empty_list": [], "zero_value": 0}
		mock_chat.send_message.return_value = _make_response(json.dumps(response_with_nulls))

		# Act
		result = await google_gateway.generate_response(user_message)

		# Assert
		assert result == response_with_nulls
		assert result["optional_field"] is None
		assert result["empty_list"] == []
		assert result["zero_value"] == 0

	def test_dataclass_attributes(self, google_gateway, mock_client, mock_logger, mock_config):
		"""Test that GoogleGateway dataclass attributes are accessible"""
		# Assert
		assert google_gateway._client == mock_client
		assert google_gateway.logger == mock_logger
		assert google_gateway._model_name == "gemini-3-flash-preview"
		assert google_gateway._config == mock_config
