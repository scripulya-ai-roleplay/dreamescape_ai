from unittest.mock import Mock
from uuid import uuid4

import pytest

from src.application.ports import IScripulyaAgentClient, LLMModelType, LLMRequest, UserMessageDTO
from src.domain.models import ChatRoles
from src.infrastructure.gateways.mock_scripulya_agent_client import MockScripulyaAgentClient


def _request(text: str = "hello") -> LLMRequest:
	return LLMRequest(
		message=UserMessageDTO(
			chat_id=uuid4(),
			message=text,
			llm_model=LLMModelType.gemini_flash_preview,
			role=ChatRoles.USER,
		),
		history=[],
	)


@pytest.mark.unit
class TestMockScripulyaAgentClient:
	"""Unit tests for the offline (no-broker) agent client stand-in."""

	@pytest.fixture
	def mock_logger(self):
		return Mock()

	@pytest.fixture
	def client(self, mock_logger):
		return MockScripulyaAgentClient(logger=mock_logger)

	@pytest.mark.asyncio
	async def test_publish_is_a_noop_that_does_not_raise(self, client):
		"""publish() drops the request without a broker; it must not raise."""
		req = _request("hi")

		await client.publish(req)  # no exception

	@pytest.mark.asyncio
	async def test_publish_logs_the_chat_id(self, client, mock_logger):
		"""The dropped request is logged so the no-op is not silent."""
		req = _request("dropped me")

		await client.publish(req)

		mock_logger.info.assert_called_once()
		args, _ = mock_logger.info.call_args
		assert req.message.chat_id in args

	def test_is_a_scripulya_agent_client(self, client):
		"""The mock satisfies the interface so DI can swap it for the real client."""
		assert isinstance(client, IScripulyaAgentClient)
