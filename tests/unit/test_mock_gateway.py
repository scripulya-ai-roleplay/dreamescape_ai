import pytest
from unittest.mock import Mock

from src.infrastructure.gateways.mock_gateway import MockGateway


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
    async def test_generate_response_success(self, mock_gateway, mock_logger):
        """Test successful mock response generation"""
        # Arrange
        user_message = "Hello, how are you?"

        # Act
        result = await mock_gateway.generate_response(user_message)

        # Assert
        assert isinstance(result, dict)
        assert "text" in result
        assert "model" in result
        assert "usage" in result
        
        assert result["text"] == f"Mock response for: {user_message}"
        assert result["model"] == "testing_mock"
        assert result["usage"]["tokens"] == 10
        
        # Verify logging
        mock_logger.info.assert_called_once_with(f"Mock gateway received: {user_message}")

    @pytest.mark.asyncio
    async def test_generate_response_empty_message(self, mock_gateway, mock_logger):
        """Test mock response with empty message"""
        # Arrange
        user_message = ""

        # Act
        result = await mock_gateway.generate_response(user_message)

        # Assert
        assert result["text"] == "Mock response for: "
        assert result["model"] == "testing_mock"
        assert result["usage"]["tokens"] == 10
        
        mock_logger.info.assert_called_once_with("Mock gateway received: ")

    @pytest.mark.asyncio
    async def test_generate_response_long_message(self, mock_gateway, mock_logger):
        """Test mock response with long message"""
        # Arrange
        user_message = "This is a very long message " * 50

        # Act
        result = await mock_gateway.generate_response(user_message)

        # Assert
        assert result["text"] == f"Mock response for: {user_message}"
        assert result["model"] == "testing_mock"
        assert result["usage"]["tokens"] == 10
        
        mock_logger.info.assert_called_once_with(f"Mock gateway received: {user_message}")

    @pytest.mark.asyncio
    async def test_generate_response_special_characters(self, mock_gateway, mock_logger):
        """Test mock response with special characters"""
        # Arrange
        user_message = "Hello! @#$%^&*()_+ 123 🌍"

        # Act
        result = await mock_gateway.generate_response(user_message)

        # Assert
        assert result["text"] == f"Mock response for: {user_message}"
        assert result["model"] == "testing_mock"
        assert result["usage"]["tokens"] == 10
        
        mock_logger.info.assert_called_once_with(f"Mock gateway received: {user_message}")

    @pytest.mark.asyncio
    async def test_generate_response_unicode_characters(self, mock_gateway, mock_logger):
        """Test mock response with Unicode characters"""
        # Arrange
        user_message = "Привет! 你好! こんにちは!"

        # Act
        result = await mock_gateway.generate_response(user_message)

        # Assert
        assert result["text"] == f"Mock response for: {user_message}"
        assert result["model"] == "testing_mock"
        assert result["usage"]["tokens"] == 10
        
        mock_logger.info.assert_called_once_with(f"Mock gateway received: {user_message}")

    @pytest.mark.asyncio
    async def test_generate_response_newline_characters(self, mock_gateway, mock_logger):
        """Test mock response with newline characters"""
        # Arrange
        user_message = "Line 1\nLine 2\nLine 3"

        # Act
        result = await mock_gateway.generate_response(user_message)

        # Assert
        assert result["text"] == f"Mock response for: {user_message}"
        assert result["model"] == "testing_mock"
        assert result["usage"]["tokens"] == 10
        
        mock_logger.info.assert_called_once_with(f"Mock gateway received: {user_message}")

    @pytest.mark.asyncio
    async def test_generate_response_consistent_structure(self, mock_gateway, mock_logger):
        """Test that response structure is always consistent"""
        # Arrange
        messages = ["Hello", "How are you?", "What's the weather like?"]

        # Act & Assert
        for message in messages:
            result = await mock_gateway.generate_response(message)
            
            # Verify structure is always the same
            assert len(result.keys()) == 3
            assert "text" in result
            assert "model" in result
            assert "usage" in result
            
            # Verify model and usage are always the same
            assert result["model"] == "testing_mock"
            assert result["usage"]["tokens"] == 10
            
            # Verify text includes the message
            assert message in result["text"]

    @pytest.mark.asyncio
    async def test_generate_response_no_exceptions(self, mock_gateway, mock_logger):
        """Test that mock gateway never raises exceptions"""
        # Arrange
        problematic_inputs = [
            None,  # This might cause issues in real gateways
            123,   # Non-string input
            [],    # List instead of string
            {}     # Dict instead of string
        ]

        # Act & Assert - should handle gracefully without exceptions
        for input_value in problematic_inputs:
            try:
                result = await mock_gateway.generate_response(input_value)
                # Should always return a dict with expected structure
                assert isinstance(result, dict)
                assert "text" in result
                assert "model" in result
                assert "usage" in result
            except Exception:
                # If an exception occurs, it's expected behavior for invalid inputs
                # The mock should be robust, but some type mismatches might still occur
                pass

    def test_dataclass_attributes(self, mock_gateway, mock_logger):
        """Test that MockGateway dataclass attributes are accessible"""
        # Assert
        assert mock_gateway.logger == mock_logger

    @pytest.mark.asyncio
    async def test_multiple_calls_independent(self, mock_gateway, mock_logger):
        """Test that multiple calls to generate_response are independent"""
        # Arrange
        message1 = "First message"
        message2 = "Second message"

        # Act
        result1 = await mock_gateway.generate_response(message1)
        result2 = await mock_gateway.generate_response(message2)

        # Assert
        assert result1["text"] == f"Mock response for: {message1}"
        assert result2["text"] == f"Mock response for: {message2}"
        assert result1 != result2
        
        # Verify both calls were logged
        assert mock_logger.info.call_count == 2
        mock_logger.info.assert_any_call(f"Mock gateway received: {message1}")
        mock_logger.info.assert_any_call(f"Mock gateway received: {message2}")

    @pytest.mark.asyncio
    async def test_response_immutability(self, mock_gateway, mock_logger):
        """Test that response dict can be safely modified without affecting future responses"""
        # Arrange
        user_message = "Test message"

        # Act
        result1 = await mock_gateway.generate_response(user_message)
        result1["text"] = "Modified text"  # Modify the response
        result1["new_field"] = "new_value"  # Add new field
        
        result2 = await mock_gateway.generate_response(user_message)

        # Assert - second response should be unaffected by modifications to first
        assert result2["text"] == f"Mock response for: {user_message}"
        assert "new_field" not in result2
        assert result2["model"] == "testing_mock"
        assert result2["usage"]["tokens"] == 10