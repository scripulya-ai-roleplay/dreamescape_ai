import logging
from typing import AsyncGenerator

from dishka import Provider, Scope, make_async_container, provide
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine, create_async_engine, async_sessionmaker

from src.conf import settings
from src.infrastructure.database.postgresqluow import PostgresqlUOW
from src.infrastructure.gateways.google_gateway import GoogleGateway
from src.application.ports import (
	IUserService,
	IUserGateway,
	IJWTService,
	IGatewayFactory,
	IChatsService,
	ISceneService,
	ISceneGateway,
)
from src.infrastructure.gateways.mock_gateway import MockGateway
from src.infrastructure.gateways.gateway_factory import GatewayFactory
from src.infrastructure.gateways.user_gateway import UserGateway
from src.infrastructure.gateways.scenes_gateway import SceneGateway
from src.application.user.user_service import UserService
from src.application.scene.service import SceneService
from src.application.auth.jwt_service import JWTService
from src.application.chats.service import ChatsService


logger = logging.getLogger(__name__)


class GatewayProvider(Provider):
	@provide(scope=Scope.REQUEST)
	def provide_google_gateway(self) -> GoogleGateway:
		return GoogleGateway(
			logger=logger,
			chat=settings.CHAT,
		)

	@provide(scope=Scope.REQUEST)
	def provide_mock_gateway(self) -> MockGateway:
		return MockGateway(logger=logger)

	@provide(scope=Scope.REQUEST)
	def provide_gateway_factory(self, google_gateway: GoogleGateway, mock_gateway: MockGateway) -> IGatewayFactory:
		gateways = {
			"gemini-3-flash-preview": google_gateway,
			"testing_mock": mock_gateway,
		}
		return GatewayFactory(gateways)

	@provide(scope=Scope.REQUEST)
	def provide_user_gateway(self, session: AsyncSession) -> IUserGateway:
		return UserGateway(session)

	@provide(scope=Scope.REQUEST)
	def provide_scene_gateway(self, session: AsyncSession) -> ISceneGateway:
		return SceneGateway(session)


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
	def provide_chats_service(self, gateway_factory: IGatewayFactory) -> IChatsService:
		return ChatsService(gateway_factory=gateway_factory)

	@provide(scope=Scope.REQUEST)
	def provide_scene_service(self, scene_gateway: ISceneGateway, uow: PostgresqlUOW) -> ISceneService:
		return SceneService(uow=uow, gateway=scene_gateway)


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
	return make_async_container(
		GatewayProvider(),
		DatabaseProvider(),
		UoWProvider(),
		ServiceProvider(),
	)
