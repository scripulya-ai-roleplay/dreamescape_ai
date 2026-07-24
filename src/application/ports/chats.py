import abc
import asyncio
from typing import Optional
from uuid import UUID

from src.application.chats.schemas import ChatFilterDTO
from src.application.chats.settings import ChatSettings
from src.application.ports.common import Page

from src.application.ports.llm import UserMessageDTO
from src.domain.models import Chat, Message


class IChatsService(abc.ABC):
	@abc.abstractmethod
	async def send_message(self, chat_dto: UserMessageDTO, actor_id: UUID) -> Message: ...


class IChatGateway(abc.ABC):
	@abc.abstractmethod
	async def create(self, chat: Chat) -> UUID: ...

	@abc.abstractmethod
	async def get_one(self, chat_uuid: UUID) -> Chat: ...

	@abc.abstractmethod
	async def search(self, dto: ChatFilterDTO, actor_id: UUID | None = None) -> Page[Chat]: ...

	@abc.abstractmethod
	async def delete(self, chat_uuid: UUID) -> UUID: ...

	@abc.abstractmethod
	async def update(self, target_chat_uuid: UUID, chat_name: str) -> UUID: ...

	@abc.abstractmethod
	async def set_persona(self, chat_uuid: UUID, user_character_id: UUID) -> UUID: ...

	@abc.abstractmethod
	async def set_initial_message(self, chat_uuid: UUID, initial_message_id: UUID) -> UUID: ...


class IChatService(abc.ABC):
	@abc.abstractmethod
	async def start_chat(self, chat: Chat) -> UUID: ...

	@abc.abstractmethod
	async def get_one(self, chat_uuid: UUID, actor_id: UUID) -> Chat: ...

	@abc.abstractmethod
	async def search(self, dto: ChatFilterDTO, actor_id: UUID) -> Page[Chat]: ...

	@abc.abstractmethod
	async def delete(self, chat_uuid: UUID, actor_id: UUID) -> UUID: ...

	@abc.abstractmethod
	async def update(self, target_chat_uuid: UUID, chat_name: str, actor_id: UUID) -> UUID: ...

	@abc.abstractmethod
	async def set_persona(self, chat_uuid: UUID, user_character_id: UUID, actor_id: UUID) -> UUID: ...

	@abc.abstractmethod
	async def choose_initial_message(self, chat_uuid: UUID, initial_message_uuid: UUID, actor_id: UUID) -> Message: ...


class IChatSettingsGateway(abc.ABC):
	@abc.abstractmethod
	async def get_for_chat(self, chat_id: UUID) -> Optional[ChatSettings]: ...

	@abc.abstractmethod
	async def upsert(self, chat_id: UUID, settings: ChatSettings) -> ChatSettings: ...


class IChatSettingsService(abc.ABC):
	@abc.abstractmethod
	async def get_for_chat(self, chat_id: UUID) -> Optional[ChatSettings]: ...

	@abc.abstractmethod
	async def upsert(self, chat_id: UUID, settings: ChatSettings) -> ChatSettings: ...


class IChatEventGateway(abc.ABC):
	@abc.abstractmethod
	def subscribe(self, chat_id: UUID) -> asyncio.Queue: ...

	@abc.abstractmethod
	def unsubscribe(self, chat_id: UUID, queue: asyncio.Queue) -> None: ...

	@abc.abstractmethod
	def publish_message(self, chat_id: UUID, message: Message) -> None: ...
