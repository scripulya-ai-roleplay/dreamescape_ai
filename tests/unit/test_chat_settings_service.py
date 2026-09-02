from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.application.chats.settings_service import ChatSettingsService
from src.application.ports.chats import IChatGateway, IChatSettingsGateway
from src.application.ports.common import IUnitOfWork
from src.domain.models import Chat
from src.infrastructure.exceptions import ChatReadOnlyException


def _chat(scene_id):
	return Chat(id=uuid4(), title="chat", user_id=uuid4(), scene_id=scene_id)


class TestChatSettingsService:
	@pytest.fixture
	def mock_settings_gateway(self):
		return AsyncMock(spec=IChatSettingsGateway)

	@pytest.fixture
	def mock_chat_gateway(self):
		return AsyncMock(spec=IChatGateway)

	@pytest.fixture
	def mock_uow(self):
		uow = AsyncMock(spec=IUnitOfWork)
		uow.__aenter__ = AsyncMock()
		uow.__aexit__ = AsyncMock(return_value=False)
		return uow

	@pytest.fixture
	def settings_service(self, mock_settings_gateway, mock_chat_gateway, mock_uow):
		return ChatSettingsService(
			chat_settings_gateway=mock_settings_gateway,
			chat_gateway=mock_chat_gateway,
			uow=mock_uow,
		)

	@pytest.fixture
	def sample_settings(self):
		return AsyncMock()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_upsert_read_only_chat_rejected(
		self, settings_service, mock_settings_gateway, mock_chat_gateway, mock_uow, sample_settings
	):
		chat_uuid = uuid4()
		mock_chat_gateway.get_one.return_value = _chat(None)

		with pytest.raises(ChatReadOnlyException):
			await settings_service.upsert(chat_uuid, sample_settings)

		mock_settings_gateway.upsert.assert_not_called()
		mock_uow.__aenter__.assert_not_called()

	@pytest.mark.unit
	@pytest.mark.asyncio
	async def test_upsert_writable_chat_passes(
		self, settings_service, mock_settings_gateway, mock_chat_gateway, sample_settings
	):
		chat_uuid = uuid4()
		mock_chat_gateway.get_one.return_value = _chat(uuid4())
		mock_settings_gateway.upsert.return_value = sample_settings

		result = await settings_service.upsert(chat_uuid, sample_settings)

		assert result is sample_settings
		mock_settings_gateway.upsert.assert_called_once_with(chat_uuid, sample_settings)
