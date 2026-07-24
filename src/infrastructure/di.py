import logging
from collections.abc import AsyncGenerator

import redis.asyncio
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from src.application.auth.authz import AuthorizationService
from src.application.auth.jwt_service import JWTService
from src.application.auth.password_hasher import Argon2PasswordHasher
from src.application.auth.service import AuthService
from src.application.character.service import CharacterService
from src.application.chats.llm_service import LLMChatsService
from src.application.chats.prompt_service import PromptService
from src.application.chats.service import ChatService
from src.application.chats.settings_service import ChatSettingsService
from src.application.events.server_events_service import ServerEventsService
from src.application.media.service import MediaService
from src.application.message.service import MessageService
from src.application.ports.auth import IAuthService, IJWTService, IPasswordHasher
from src.application.ports.authorization import IAuthorizationService, IVisibilityGateway
from src.application.ports.characters import ICharacterGateway, ICharacterService
from src.application.ports.chats import (
	IChatEventGateway,
	IChatGateway,
	IChatService,
	IChatSettingsGateway,
	IChatSettingsService,
	IChatsService,
)
from src.application.ports.llm import IGatewayFactory, IPromptService, IScripulyaAgentClient, LLMModelType
from src.application.ports.media import IImageReader, IMediaGateway, IMediaService, IObjectStorageGateway
from src.application.ports.messages import IGenerationHeartbeat, IMessageGateway, IMessageService, IServerEventsService
from src.application.ports.scenes import IInitialMessageGateway, IInitialMessageService, ISceneGateway, ISceneService
from src.application.ports.user import IUserGateway, IUserService
from src.application.scene.initial_message_service import InitialMessageService
from src.application.scene.service import SceneService
from src.application.streaming.llm_watchdog import GenerationWatchdog
from src.application.user.user_service import UserService
from src.conf import settings
from src.controllers.rabbit.v1.broker import broker
from src.infrastructure.database.postgresqluow import PostgresqlUOW
from src.infrastructure.gateways.character_gateway import CharacterGateway
from src.infrastructure.gateways.chat_event_gateway import ChatEventGateway
from src.infrastructure.gateways.chat_gateway import ChatGateway
from src.infrastructure.gateways.chat_settings_gateway import ChatSettingsGateway
from src.infrastructure.gateways.gateway_factory import GatewayFactory
from src.infrastructure.gateways.image_reader import ImageReader
from src.infrastructure.gateways.initial_message_gateway import InitialMessageGateway
from src.infrastructure.gateways.media_gateway import MediaGateway
from src.infrastructure.gateways.message_gateway import MessageGateway
from src.infrastructure.gateways.mock_gateway import MockGateway
from src.infrastructure.gateways.mock_scripulya_agent_client import MockScripulyaAgentClient
from src.infrastructure.gateways.object_storage_gateway import MinioObjectStorageGateway
from src.infrastructure.gateways.redis_heartbeat import RedisGenerationHeartbeat
from src.infrastructure.gateways.scenes_gateway import SceneGateway
from src.infrastructure.gateways.scripulya_agent_gateway import ScripulyaAgentClient, ScripulyaAgentGateway
from src.infrastructure.gateways.user_gateway import UserGateway
from src.infrastructure.gateways.visibility import VisibilityGateway
from src.infrastructure.logging.logger import Logger


class GatewayProvider(Provider):
	@provide(scope=Scope.APP)
	def provide_logger(self) -> logging.Logger:
		return logging.getLogger(Logger.LOGGER_NAME)

	@provide(scope=Scope.APP)
	async def provide_redis_client(self) -> AsyncGenerator[redis.asyncio.Redis]:
		# Yielded so dishka closes the connection pool on container shutdown.
		client = redis.asyncio.from_url(settings.REDIS_URL, decode_responses=True)
		try:
			yield client
		finally:
			await client.aclose()

	@provide(scope=Scope.APP)
	def provide_generation_heartbeat(
		self, redis_client: redis.asyncio.Redis, logger: logging.Logger
	) -> IGenerationHeartbeat:
		return RedisGenerationHeartbeat(_redis=redis_client, logger=logger)

	@provide(scope=Scope.APP)
	def provide_scripulya_agent_client(
		self,
		logger: logging.Logger,
		heartbeat: IGenerationHeartbeat,
		redis_client: redis.asyncio.Redis,
		events: IChatEventGateway,
	) -> IScripulyaAgentClient:
		if settings.LLM_AGENT_ENABLED:
			return ScripulyaAgentClient(
				broker=broker,
				request_queue=settings.LLM_AGENT_REQUEST_QUEUE,
				timeout=settings.LLM_AGENT_TIMEOUT,
				logger=logger,
				heartbeat=heartbeat,
				redis=redis_client,
				events=events,
			)
		return MockScripulyaAgentClient(logger=logger)

	@provide(scope=Scope.REQUEST)
	def provide_scripulya_agent_gateway(
		self, client: IScripulyaAgentClient, logger: logging.Logger
	) -> ScripulyaAgentGateway:
		return ScripulyaAgentGateway(logger=logger, _client=client)

	@provide(scope=Scope.REQUEST)
	def provide_mock_gateway(self, logger: logging.Logger) -> MockGateway:
		return MockGateway(logger=logger)

	@provide(scope=Scope.REQUEST)
	def provide_gateway_factory(
		self, agent_gateway: ScripulyaAgentGateway, mock_gateway: MockGateway
	) -> IGatewayFactory:
		gateways = {"testing_mock": mock_gateway}
		gateways.update({m.value: agent_gateway for m in LLMModelType if m != LLMModelType.testing_mock})
		return GatewayFactory(gateways)

	@provide(scope=Scope.REQUEST)
	def provide_user_gateway(self, session: AsyncSession, logger: logging.Logger) -> IUserGateway:
		return UserGateway(session, logger=logger)

	@provide(scope=Scope.APP)
	def provide_visibility_gateway(self) -> IVisibilityGateway:
		return VisibilityGateway()

	@provide(scope=Scope.REQUEST)
	def provide_scene_gateway(
		self, session: AsyncSession, visibility_gateway: IVisibilityGateway, logger: logging.Logger
	) -> ISceneGateway:
		return SceneGateway(session, visibility=visibility_gateway, logger=logger)

	@provide(scope=Scope.REQUEST)
	def provide_initial_message_gateway(self, session: AsyncSession, logger: logging.Logger) -> IInitialMessageGateway:
		return InitialMessageGateway(session, logger=logger)

	@provide(scope=Scope.REQUEST)
	def provide_character_gateway(
		self, session: AsyncSession, visibility_gateway: IVisibilityGateway, logger: logging.Logger
	) -> ICharacterGateway:
		return CharacterGateway(session, visibility=visibility_gateway, logger=logger)

	@provide(scope=Scope.REQUEST)
	def provide_chat_gateway(self, session: AsyncSession, logger: logging.Logger) -> IChatGateway:
		return ChatGateway(session, logger=logger)

	@provide(scope=Scope.REQUEST)
	def provide_chat_settings_gateway(self, session: AsyncSession, logger: logging.Logger) -> IChatSettingsGateway:
		return ChatSettingsGateway(session, logger=logger)

	@provide(scope=Scope.REQUEST)
	def provide_message_gateway(self, session: AsyncSession, logger: logging.Logger) -> IMessageGateway:
		return MessageGateway(session, logger=logger)

	@provide(scope=Scope.APP)
	def provide_object_storage_gateway(self, logger: logging.Logger) -> IObjectStorageGateway:
		return MinioObjectStorageGateway.from_settings(settings, logger=logger)

	@provide(scope=Scope.APP)
	def provide_image_reader(self, logger: logging.Logger) -> IImageReader:
		return ImageReader(max_bytes=settings.MEDIA_MAX_UPLOAD_BYTES, logger=logger)

	@provide(scope=Scope.REQUEST)
	def provide_media_gateway(
		self, session: AsyncSession, visibility_gateway: IVisibilityGateway, logger: logging.Logger
	) -> IMediaGateway:
		return MediaGateway(session, visibility=visibility_gateway, logger=logger)

	@provide(scope=Scope.APP)
	def provide_chat_event_gateway(self, logger: logging.Logger) -> IChatEventGateway:
		return ChatEventGateway(logger=logger)


class ServiceProvider(Provider):
	@provide(scope=Scope.REQUEST)
	def provide_user_service(
		self,
		user_gateway: IUserGateway,
		uow: PostgresqlUOW,
		authorization_service: IAuthorizationService,
		logger: logging.Logger,
	) -> IUserService:
		return UserService(user_gateway, uow, authz=authorization_service, logger=logger)

	@provide(scope=Scope.REQUEST)
	def provide_jwt_service(self, logger: logging.Logger) -> IJWTService:
		return JWTService(
			private_key=settings.JWT_SECRET_KEY,
			public_key=settings.JWT_PUBLIC_KEY,
			algorithm=settings.JWT_ALGORITHM,
			access_token_expire_minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
			logger=logger,
		)

	@provide(scope=Scope.APP)
	def provide_password_hasher(self, logger: logging.Logger) -> IPasswordHasher:
		return Argon2PasswordHasher(logger=logger)

	@provide(scope=Scope.REQUEST)
	def provide_auth_service(
		self,
		user_gateway: IUserGateway,
		password_hasher: IPasswordHasher,
		logger: logging.Logger,
	) -> IAuthService:
		return AuthService(_user_gateway=user_gateway, _password_hasher=password_hasher, logger=logger)

	@provide(scope=Scope.APP)
	def provide_prompt_service(self) -> IPromptService:
		return PromptService()

	@provide(scope=Scope.APP)
	def provide_authorization_service(self) -> IAuthorizationService:
		return AuthorizationService()

	@provide(scope=Scope.REQUEST)
	def provide_chats_service(
		self,
		gateway_factory: IGatewayFactory,
		message_service: IMessageService,
		chat_settings_gateway: IChatSettingsGateway,
		chat_gateway: IChatGateway,
		scene_gateway: ISceneGateway,
		character_gateway: ICharacterGateway,
		prompt_service: IPromptService,
		authorization_service: IAuthorizationService,
		events: IChatEventGateway,
		logger: logging.Logger,
	) -> IChatsService:
		return LLMChatsService(
			gateway_factory=gateway_factory,
			message_service=message_service,
			chat_settings_gateway=chat_settings_gateway,
			chat_gateway=chat_gateway,
			scene_gateway=scene_gateway,
			character_gateway=character_gateway,
			prompt_service=prompt_service,
			authz=authorization_service,
			_events=events,
			logger=logger,
		)

	@provide(scope=Scope.REQUEST)
	def provide_chat_settings_service(
		self, chat_settings_gateway: IChatSettingsGateway, uow: PostgresqlUOW, logger: logging.Logger
	) -> IChatSettingsService:
		return ChatSettingsService(chat_settings_gateway=chat_settings_gateway, uow=uow, logger=logger)

	@provide(scope=Scope.APP)
	def provide_server_events_service(
		self, events: IChatEventGateway, container: AsyncContainer
	) -> IServerEventsService:
		return ServerEventsService(_events=events, _container=container)

	@provide(scope=Scope.APP)
	def provide_generation_watchdog(
		self,
		heartbeat: IGenerationHeartbeat,
		events: IChatEventGateway,
		container: AsyncContainer,
		logger: logging.Logger,
	) -> GenerationWatchdog:
		return GenerationWatchdog(_heartbeat=heartbeat, _events=events, _container=container, logger=logger)

	@provide(scope=Scope.REQUEST)
	def provide_chat_service(
		self,
		chat_gateway: IChatGateway,
		initial_message_gateway: IInitialMessageGateway,
		message_gateway: IMessageGateway,
		uow: PostgresqlUOW,
		authorization_service: IAuthorizationService,
		logger: logging.Logger,
	) -> IChatService:
		return ChatService(
			chat_gateway=chat_gateway,
			initial_message_gateway=initial_message_gateway,
			message_gateway=message_gateway,
			uow=uow,
			authz=authorization_service,
			logger=logger,
		)

	@provide(scope=Scope.REQUEST)
	def provide_message_service(
		self,
		message_gateway: IMessageGateway,
		uow: PostgresqlUOW,
		authorization_service: IAuthorizationService,
		logger: logging.Logger,
	) -> IMessageService:
		return MessageService(message_gateway=message_gateway, authz=authorization_service, _uow=uow, logger=logger)

	@provide(scope=Scope.REQUEST)
	def provide_media_service(
		self,
		storage: IObjectStorageGateway,
		media_gateway: IMediaGateway,
		reader: IImageReader,
		uow: PostgresqlUOW,
		authorization_service: IAuthorizationService,
		logger: logging.Logger,
	) -> IMediaService:
		return MediaService(
			storage=storage, gateway=media_gateway, reader=reader, uow=uow, authz=authorization_service, logger=logger
		)

	@provide(scope=Scope.REQUEST)
	def provide_scene_service(
		self,
		scene_gateway: ISceneGateway,
		initial_message_gateway: IInitialMessageGateway,
		uow: PostgresqlUOW,
		authorization_service: IAuthorizationService,
		logger: logging.Logger,
	) -> ISceneService:
		return SceneService(
			uow=uow,
			gateway=scene_gateway,
			initial_message_gateway=initial_message_gateway,
			authz=authorization_service,
			logger=logger,
		)

	@provide(scope=Scope.REQUEST)
	def provide_initial_message_service(
		self,
		initial_message_gateway: IInitialMessageGateway,
		scene_gateway: ISceneGateway,
		uow: PostgresqlUOW,
		authorization_service: IAuthorizationService,
		logger: logging.Logger,
	) -> IInitialMessageService:
		return InitialMessageService(
			initial_message_gateway=initial_message_gateway,
			scene_gateway=scene_gateway,
			uow=uow,
			authz=authorization_service,
			logger=logger,
		)

	@provide(scope=Scope.REQUEST)
	def provide_character_service(
		self,
		character_gateway: ICharacterGateway,
		uow: PostgresqlUOW,
		authorization_service: IAuthorizationService,
		logger: logging.Logger,
	) -> ICharacterService:
		return CharacterService(uow=uow, gateway=character_gateway, authz=authorization_service, logger=logger)


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
	) -> AsyncGenerator[AsyncSession]:
		async with session_maker() as session:
			yield session


class UoWProvider(Provider):
	@provide(scope=Scope.REQUEST)
	def provide_postgresql_uow(self, session: AsyncSession) -> PostgresqlUOW:
		return PostgresqlUOW(session)


def create_container():
	"""Create dishka container with gateway factory and database providers"""
	return make_async_container(GatewayProvider(), DatabaseProvider(), UoWProvider(), ServiceProvider())
