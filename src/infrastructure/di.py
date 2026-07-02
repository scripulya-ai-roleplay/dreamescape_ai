import logging
from typing import AsyncGenerator

from dishka import AsyncContainer, Provider, Scope, make_async_container, provide

from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine, create_async_engine, async_sessionmaker

from src.conf import settings
from src.controllers.rabbit.v1.broker import broker
from src.infrastructure.database.postgresqluow import PostgresqlUOW
from src.infrastructure.gateways.scripulya_agent_gateway import ScripulyaAgentClient, ScripulyaAgentGateway
from src.infrastructure.gateways.mock_scripulya_agent_client import MockScripulyaAgentClient
from src.application.ports import (
	IUserService,
	IUserGateway,
	IJWTService,
	IGatewayFactory,
	IChatsService,
	IChatService,
	IChatGateway,
	IChatEventGateway,
	IChatSettingsGateway,
	IChatSettingsService,
	IServerEventsService,
	IMessageService,
	IMessageGateway,
	ISceneService,
	ISceneGateway,
	ICharacterService,
	ICharacterGateway,
	IScripulyaAgentClient,
	LLMModelType,
)
from src.infrastructure.gateways.mock_gateway import MockGateway
from src.infrastructure.gateways.gateway_factory import GatewayFactory
from src.infrastructure.gateways.user_gateway import UserGateway
from src.infrastructure.gateways.scenes_gateway import SceneGateway
from src.infrastructure.gateways.character_gateway import CharacterGateway
from src.infrastructure.gateways.chat_gateway import ChatGateway
from src.infrastructure.gateways.chat_settings_gateway import ChatSettingsGateway
from src.infrastructure.gateways.message_gateway import MessageGateway
from src.infrastructure.gateways.chat_event_gateway import ChatEventGateway
from src.application.events.server_events_service import ServerEventsService
from src.application.user.user_service import UserService
from src.application.scene.service import SceneService
from src.application.character.service import CharacterService
from src.application.chats.service import ChatService
from src.application.chats.settings_service import ChatSettingsService
from src.application.chats.llm_service import LLMChatsService
from src.application.message.service import MessageService
from src.application.auth.jwt_service import JWTService


logger = logging.getLogger(__name__)


class GatewayProvider(Provider):
	@provide(scope=Scope.APP)
	def provide_scripulya_agent_client(self) -> IScripulyaAgentClient:
		if settings.LLM_AGENT_ENABLED:
			return ScripulyaAgentClient(
				broker=broker,
				request_queue=settings.LLM_AGENT_REQUEST_QUEUE,
				timeout=settings.LLM_AGENT_TIMEOUT,
				logger=logger,
			)
		return MockScripulyaAgentClient(logger=logger)

	@provide(scope=Scope.REQUEST)
	def provide_scripulya_agent_gateway(self, client: IScripulyaAgentClient) -> ScripulyaAgentGateway:
		return ScripulyaAgentGateway(logger=logger, _client=client)

	@provide(scope=Scope.REQUEST)
	def provide_mock_gateway(self) -> MockGateway:
		return MockGateway(logger=logger)

	@provide(scope=Scope.REQUEST)
	def provide_gateway_factory(
		self, agent_gateway: ScripulyaAgentGateway, mock_gateway: MockGateway
	) -> IGatewayFactory:
		# Real models are delegated to scripulya_agent; testing_mock stays local (offline).
		gateways = {"testing_mock": mock_gateway}
		gateways.update({m.value: agent_gateway for m in LLMModelType if m != LLMModelType.testing_mock})
		return GatewayFactory(gateways)

	@provide(scope=Scope.REQUEST)
	def provide_user_gateway(self, session: AsyncSession) -> IUserGateway:
		return UserGateway(session)

	@provide(scope=Scope.REQUEST)
	def provide_scene_gateway(self, session: AsyncSession) -> ISceneGateway:
		return SceneGateway(session)

	@provide(scope=Scope.REQUEST)
	def provide_character_gateway(self, session: AsyncSession) -> ICharacterGateway:
		return CharacterGateway(session)

	@provide(scope=Scope.REQUEST)
	def provide_chat_gateway(self, session: AsyncSession) -> IChatGateway:
		return ChatGateway(session)

	@provide(scope=Scope.REQUEST)
	def provide_chat_settings_gateway(self, session: AsyncSession) -> IChatSettingsGateway:
		return ChatSettingsGateway(session)

	@provide(scope=Scope.REQUEST)
	def provide_message_gateway(self, session: AsyncSession) -> IMessageGateway:
		return MessageGateway(session)

	@provide(scope=Scope.APP)
	def provide_chat_event_gateway(self) -> IChatEventGateway:
		# In-process SSE fan-out; shared by the chats service, the result subscriber,
		# and the SSE service. Single-process only (see ChatEventGateway docstring).
		return ChatEventGateway()


class ServiceProvider(Provider):
	@provide(scope=Scope.REQUEST)
	def provide_user_service(self, user_gateway: IUserGateway, uow: PostgresqlUOW) -> IUserService:
		return UserService(user_gateway, uow)

	@provide(scope=Scope.REQUEST)
	def provide_jwt_service(self) -> IJWTService:
		return JWTService(
			private_key=settings.JWT_SECRET_KEY,
			public_key=settings.JWT_PUBLIC_KEY,
			algorithm=settings.JWT_ALGORITHM,
			logger=logger,
		)

	@provide(scope=Scope.REQUEST)
	def provide_chats_service(
		self,
		gateway_factory: IGatewayFactory,
		message_gateway: IMessageGateway,
		chat_settings_gateway: IChatSettingsGateway,
		uow: PostgresqlUOW,
		events: IChatEventGateway,
	) -> IChatsService:
		return LLMChatsService(
			gateway_factory=gateway_factory,
			messages_gateway=message_gateway,
			chat_settings_gateway=chat_settings_gateway,
			_uow=uow,
			_events=events,
		)

	@provide(scope=Scope.REQUEST)
	def provide_chat_settings_service(self, chat_settings_gateway: IChatSettingsGateway) -> IChatSettingsService:
		return ChatSettingsService(chat_settings_gateway=chat_settings_gateway)

	@provide(scope=Scope.APP)
	def provide_server_events_service(
		self, events: IChatEventGateway, container: AsyncContainer
	) -> IServerEventsService:
		return ServerEventsService(_events=events, _container=container)

	@provide(scope=Scope.REQUEST)
	def provide_chat_service(self, chat_gateway: IChatGateway) -> IChatService:
		return ChatService(chat_gateway=chat_gateway)

	@provide(scope=Scope.REQUEST)
	def provide_message_service(self, message_gateway: IMessageGateway, uow: PostgresqlUOW) -> IMessageService:
		return MessageService(message_gateway=message_gateway, _uow=uow)

	@provide(scope=Scope.REQUEST)
	def provide_scene_service(self, scene_gateway: ISceneGateway, uow: PostgresqlUOW) -> ISceneService:
		return SceneService(uow=uow, gateway=scene_gateway)

	@provide(scope=Scope.REQUEST)
	def provide_character_service(self, character_gateway: ICharacterGateway, uow: PostgresqlUOW) -> ICharacterService:
		return CharacterService(uow=uow, gateway=character_gateway)


class DatabaseProvider(Provider):
	@provide(scope=Scope.APP)
	def provide_async_engine(self) -> AsyncEngine:
		return create_async_engine(
			settings.DATABASE_URL,
			echo=settings.DEBUG,
			future=True,
		)

	@provide(scope=Scope.APP)
	def provide_session_maker(self, engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
		return async_sessionmaker(
			engine,
			class_=AsyncSession,
			expire_on_commit=False,
		)

	@provide(scope=Scope.REQUEST)
	async def provide_async_session(
		self, session_maker: async_sessionmaker[AsyncSession]
	) -> AsyncGenerator[AsyncSession, None]:
		async with session_maker() as session:
			yield session


class UoWProvider(Provider):
	@provide(scope=Scope.REQUEST)
	def provide_postgresql_uow(self, session: AsyncSession) -> PostgresqlUOW:
		return PostgresqlUOW(session)


def create_container():
	"""Create dishka container with gateway factory and database providers"""
	return make_async_container(GatewayProvider(), DatabaseProvider(), UoWProvider(), ServiceProvider())
