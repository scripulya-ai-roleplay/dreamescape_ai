import pytest
from unittest.mock import Mock

from src.infrastructure.gateways.gateway_factory import GatewayFactory
from src.application.ports import ILLMChatGateway, IGatewayFactory


@pytest.mark.unit
class TestGatewayFactory:
	"""Unit tests for GatewayFactory"""

	@pytest.fixture
	def mock_google_gateway(self):
		"""Mock Google gateway for testing"""
		return Mock(spec=ILLMChatGateway)

	@pytest.fixture
	def mock_mock_gateway(self):
		"""Mock mock gateway for testing"""
		return Mock(spec=ILLMChatGateway)

	@pytest.fixture
	def gateway_registry(self, mock_google_gateway, mock_mock_gateway):
		"""Registry of gateways for testing"""
		return {"google": mock_google_gateway, "mock": mock_mock_gateway}

	@pytest.fixture
	def gateway_factory(self, gateway_registry):
		"""GatewayFactory instance with mocked dependencies"""
		return GatewayFactory(gateway_registry)

	def test_create_gateway_success_google(self, gateway_factory, mock_google_gateway):
		"""Test successful creation of Google gateway"""
		# Act
		result = gateway_factory.create_gateway("google")

		# Assert
		assert result == mock_google_gateway

	def test_create_gateway_success_mock(self, gateway_factory, mock_mock_gateway):
		"""Test successful creation of mock gateway"""
		# Act
		result = gateway_factory.create_gateway("mock")

		# Assert
		assert result == mock_mock_gateway

	def test_create_gateway_unknown_type(self, gateway_factory):
		"""Test gateway creation with unknown type"""
		# Act & Assert
		with pytest.raises(ValueError, match="Unknown gateway type: unknown"):
			gateway_factory.create_gateway("unknown")

	def test_create_gateway_empty_string(self, gateway_factory):
		"""Test gateway creation with empty string"""
		# Act & Assert
		with pytest.raises(ValueError, match="Unknown gateway type: "):
			gateway_factory.create_gateway("")

	def test_create_gateway_none_type(self, gateway_factory):
		"""Test gateway creation with None type"""
		# Act & Assert
		with pytest.raises(ValueError, match="Unknown gateway type: None"):
			gateway_factory.create_gateway(None)

	def test_create_gateway_case_sensitive(self, gateway_factory):
		"""Test that gateway type is case sensitive"""
		# Act & Assert
		with pytest.raises(ValueError, match="Unknown gateway type: Google"):
			gateway_factory.create_gateway("Google")

		with pytest.raises(ValueError, match="Unknown gateway type: MOCK"):
			gateway_factory.create_gateway("MOCK")

	def test_factory_with_empty_registry(self):
		"""Test factory behavior with empty gateway registry"""
		# Arrange
		empty_factory = GatewayFactory({})

		# Act & Assert
		with pytest.raises(ValueError, match="Unknown gateway type: google"):
			empty_factory.create_gateway("google")

	def test_factory_with_single_gateway(self, mock_google_gateway):
		"""Test factory with single gateway in registry"""
		# Arrange
		single_gateway_factory = GatewayFactory({"google": mock_google_gateway})

		# Act
		result = single_gateway_factory.create_gateway("google")

		# Assert
		assert result == mock_google_gateway

		# Should still fail for unknown types
		with pytest.raises(ValueError, match="Unknown gateway type: mock"):
			single_gateway_factory.create_gateway("mock")

	def test_factory_initialization(self, gateway_registry):
		"""Test proper factory initialization"""
		# Act
		factory = GatewayFactory(gateway_registry)

		# Assert
		assert factory._gateways == gateway_registry
		assert len(factory._gateways) == 2
		assert "google" in factory._gateways
		assert "mock" in factory._gateways

	def test_factory_registry_immutability(self, gateway_factory):
		# Act - try to modify the registry externally
		gateway_factory._gateways["new_gateway"] = Mock()

		# Assert - the factory should still work with original gateways
		# (Note: This test verifies current behavior, not necessarily desired behavior)
		assert "new_gateway" in gateway_factory._gateways

		# But original gateways should still work
		assert gateway_factory.create_gateway("google") is not None
		assert gateway_factory.create_gateway("mock") is not None

	def test_gateway_reuse(self, gateway_factory, mock_google_gateway):
		"""Test that the same gateway instance is returned for repeated calls"""
		# Act
		result1 = gateway_factory.create_gateway("google")
		result2 = gateway_factory.create_gateway("google")

		# Assert
		assert result1 == mock_google_gateway
		assert result2 == mock_google_gateway
		assert result1 is result2  # Same instance

	def test_multiple_different_gateways(self, gateway_factory, mock_google_gateway, mock_mock_gateway):
		"""Test creation of multiple different gateways"""
		# Act
		google_result = gateway_factory.create_gateway("google")
		mock_result = gateway_factory.create_gateway("mock")

		# Assert
		assert google_result == mock_google_gateway
		assert mock_result == mock_mock_gateway
		assert google_result != mock_result

	def test_gateway_factory_interface_compliance(self, gateway_factory):
		"""Test that GatewayFactory implements IGatewayFactory interface"""
		# Assert
		assert isinstance(gateway_factory, IGatewayFactory)
		assert hasattr(gateway_factory, "create_gateway")
		assert callable(gateway_factory.create_gateway)

	def test_custom_gateway_types(self):
		"""Test factory with custom gateway types"""
		# Arrange
		custom_gateway1 = Mock(spec=ILLMChatGateway)
		custom_gateway2 = Mock(spec=ILLMChatGateway)
		custom_registry = {
			"openai": custom_gateway1,
			"anthropic": custom_gateway2,
			"local-llm": Mock(spec=ILLMChatGateway),
		}
		custom_factory = GatewayFactory(custom_registry)

		# Act & Assert
		assert custom_factory.create_gateway("openai") == custom_gateway1
		assert custom_factory.create_gateway("anthropic") == custom_gateway2
		assert custom_factory.create_gateway("local-llm") is not None

		with pytest.raises(ValueError, match="Unknown gateway type: google"):
			custom_factory.create_gateway("google")

	def test_special_character_gateway_names(self):
		"""Test gateway names with special characters"""
		# Arrange
		special_gateway = Mock(spec=ILLMChatGateway)
		special_registry = {
			"test-gateway": special_gateway,
			"test_gateway": special_gateway,
			"test.gateway": special_gateway,
			"test123": special_gateway,
		}
		special_factory = GatewayFactory(special_registry)

		# Act & Assert
		assert special_factory.create_gateway("test-gateway") == special_gateway
		assert special_factory.create_gateway("test_gateway") == special_gateway
		assert special_factory.create_gateway("test.gateway") == special_gateway
		assert special_factory.create_gateway("test123") == special_gateway

	def test_numeric_gateway_types(self):
		"""Test that numeric gateway types work"""
		# Arrange
		numeric_gateway = Mock(spec=ILLMChatGateway)
		numeric_registry = {"123": numeric_gateway, "gateway1": numeric_gateway}
		numeric_factory = GatewayFactory(numeric_registry)

		# Act & Assert
		assert numeric_factory.create_gateway("123") == numeric_gateway
		assert numeric_factory.create_gateway("gateway1") == numeric_gateway
