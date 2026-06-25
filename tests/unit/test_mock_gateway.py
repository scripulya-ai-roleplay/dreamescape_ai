import pytest
from unittest.mock import Mock
from uuid import uuid4

from src.application.ports import LLMModelType, UserMessageDTO
from src.domain.models import ChatRoles
from src.infrastructure.gateways.mock_gateway import MockGateway


def _msg(text: str, llm_model: LLMModelType = LLMModelType.testing_mock) -> UserMessageDTO:
	return UserMessageDTO(chat_id=uuid4(), message=text, llm_model=llm_model, role=ChatRoles.USER)


@pytest.mark.unit
class TestMockGateway:
	"""Unit tests for MockGateway"""

	@pytest.fixture
	def mock_logger(self):
		"""Mock logger for testing"""
		return Mock()

	@pytest.fixture
	def mock_gateway(self, mock_logger):
		"""MockGateway instance with mocked dependencies"""
		return MockGateway(logger=mock_logger)

	@pytest.mark.asyncio
	@pytest.mark.parametrize(
		"text",
		[
			"Hello, how are you?",
			"",
			"This is a very long message " * 50,
			"Hello! @#$%^&*()_+ 123 🌍",
			"Привет! 你好! こんにちは!",
			"Line 1\nLine 2\nLine 3",
		],
	)
	async def test_submit_echoes_message(self, mock_gateway, mock_logger, text):
		"""The mock wraps the incoming message text and reports consistent metadata."""
		result = await mock_gateway.submit(_msg(text), history=[])

		assert result.text == f"Mock response for: {text}"
		assert result.model == LLMModelType.testing_mock
		assert result.usage["tokens"] == 10
		assert result.provider == "mock"
		mock_logger.info.assert_called_once_with(f"Mock gateway received: {text}")

	@pytest.mark.asyncio
	async def test_submit_echoes_chosen_model(self, mock_gateway):
		"""A non-testing model routed to the mock is echoed back."""
		result = await mock_gateway.submit(_msg("hi", LLMModelType.gemini_flash_preview), history=[])
		assert result.model == LLMModelType.gemini_flash_preview

	@pytest.mark.asyncio
	async def test_history_does_not_affect_output(self, mock_gateway):
		result = await mock_gateway.submit(_msg("hello"), history=[_msg("prior"), _msg("prior 2")])
		assert result.text == "Mock response for: hello"

	def test_dataclass_attributes(self, mock_gateway, mock_logger):
		"""Test that MockGateway dataclass attributes are accessible"""
		assert mock_gateway.logger == mock_logger

	@pytest.mark.asyncio
	async def test_multiple_calls_independent(self, mock_gateway, mock_logger):
		"""Test that multiple calls to submit are independent"""
		result1 = await mock_gateway.submit(_msg("First message"), history=[])
		result2 = await mock_gateway.submit(_msg("Second message"), history=[])

		assert result1.text == "Mock response for: First message"
		assert result2.text == "Mock response for: Second message"
		assert result1 != result2
		assert mock_logger.info.call_count == 2
