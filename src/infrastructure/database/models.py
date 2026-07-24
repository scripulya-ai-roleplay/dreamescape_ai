import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, ForeignKey, Index, Integer, String, Table, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func, text


class Base(DeclarativeBase):
	pass


character_scene = Table(
	"character_scene",
	Base.metadata,
	Column("character_id", UUID(as_uuid=True), ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True),
	Column("scene_id", UUID(as_uuid=True), ForeignKey("scenes.id", ondelete="CASCADE"), primary_key=True),
)

character_likes = Table(
	"character_likes",
	Base.metadata,
	Column("character_id", UUID(as_uuid=True), ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True),
	Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)
scene_likes = Table(
	"scene_likes",
	Base.metadata,
	Column("scene_id", UUID(as_uuid=True), ForeignKey("scenes.id", ondelete="CASCADE"), primary_key=True),
	Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)
character_bookmarks = Table(
	"character_bookmarks",
	Base.metadata,
	Column("character_id", UUID(as_uuid=True), ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True),
	Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)
scene_bookmarks = Table(
	"scene_bookmarks",
	Base.metadata,
	Column("scene_id", UUID(as_uuid=True), ForeignKey("scenes.id", ondelete="CASCADE"), primary_key=True),
	Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
	__tablename__ = "users"
	__table_args__ = (CheckConstraint("role IN ('admin', 'api', 'developer')", name="check_user_role_valid"),)

	id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
	)
	username: Mapped[str | None] = mapped_column(String(100), unique=True)
	password_hash: Mapped[str | None] = mapped_column(Text)
	google_id: Mapped[str | None] = mapped_column(String(255), unique=True)
	role: Mapped[str] = mapped_column(String(20), nullable=False, server_default="api", default="api")
	crystal_balance: Mapped[int] = mapped_column(Integer, server_default="1000", default=1000)

	characters: Mapped[list["Character"]] = relationship(back_populates="owner")
	scenes: Mapped[list["Scene"]] = relationship(back_populates="owner")
	chats: Mapped[list["Chat"]] = relationship(back_populates="user")


class Character(Base):
	__tablename__ = "characters"

	id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
	)
	owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
	name: Mapped[str] = mapped_column(String(255))
	system_prompt: Mapped[str] = mapped_column(Text)
	is_public: Mapped[bool] = mapped_column(Boolean, server_default="false", default=False)

	owner: Mapped["User"] = relationship(back_populates="characters")
	scenes: Mapped[list["Scene"]] = relationship(back_populates="characters", secondary="character_scene")


class Scene(Base):
	__tablename__ = "scenes"

	id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
	)
	owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
	title: Mapped[str] = mapped_column(Text)
	description: Mapped[str] = mapped_column(Text)
	background_prompt: Mapped[str] = mapped_column(Text)
	is_public: Mapped[bool] = mapped_column(Boolean, server_default="false", default=False)

	owner: Mapped["User"] = relationship(back_populates="scenes")
	chats: Mapped[list["Chat"]] = relationship(back_populates="scene")
	characters: Mapped[list["Character"]] = relationship(back_populates="scenes", secondary="character_scene")
	initial_messages: Mapped[list["SceneInitialMessage"]] = relationship(
		back_populates="scene", cascade="all, delete-orphan", order_by="SceneInitialMessage.created_at"
	)


class SceneInitialMessage(Base):
	__tablename__ = "scene_initial_messages"

	id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
	)
	scene_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"), index=True)
	text: Mapped[str] = mapped_column(Text)
	created_at: Mapped[datetime] = mapped_column(server_default=func.now())
	updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

	scene: Mapped["Scene"] = relationship(back_populates="initial_messages")


class Chat(Base):
	__tablename__ = "chats"

	id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
	)
	name: Mapped[str] = mapped_column(Text)
	user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
	scene_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("scenes.id", ondelete="SET NULL"), index=True)
	user_character_id: Mapped[uuid.UUID | None] = mapped_column(
		ForeignKey("characters.id", ondelete="SET NULL"), index=True
	)
	initial_message_id: Mapped[uuid.UUID | None] = mapped_column(
		ForeignKey("scene_initial_messages.id", ondelete="SET NULL"), index=True
	)
	created_at: Mapped[datetime] = mapped_column(server_default=func.now())

	user: Mapped["User"] = relationship(back_populates="chats")
	scene: Mapped[Optional["Scene"]] = relationship(back_populates="chats")
	messages: Mapped[list["Message"]] = relationship(back_populates="chat")
	settings: Mapped[Optional["ChatSettings"]] = relationship(
		back_populates="chat", uselist=False, cascade="all, delete-orphan"
	)


class ChatSettings(Base):
	__tablename__ = "chat_settings"
	chat_id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), ForeignKey("chats.id", ondelete="CASCADE"), primary_key=True
	)
	settings: Mapped[dict] = mapped_column(JSONB)
	created_at: Mapped[datetime] = mapped_column(server_default=func.now())
	updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

	chat: Mapped["Chat"] = relationship(back_populates="settings")


class Message(Base):
	__tablename__ = "messages"
	__table_args__ = (
		CheckConstraint("role IN ('user', 'model')", name="check_role_valid"),
		CheckConstraint("status IN ('pending', 'completed', 'failed')", name="check_message_status_valid"),
	)

	id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
	)
	chat_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), index=True)
	role: Mapped[str] = mapped_column(String(50))
	content: Mapped[str] = mapped_column(Text)
	status: Mapped[str] = mapped_column(String(20), server_default="completed", default="completed")
	cost_crystals: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
	created_at: Mapped[datetime] = mapped_column(server_default=func.now())
	updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

	chat: Mapped["Chat"] = relationship(back_populates="messages")


class MediaAsset(Base):
	__tablename__ = "media_assets"
	__table_args__ = (
		Index("idx_media_entity", "entity_type", "entity_id"),
		CheckConstraint("object_key IS NOT NULL OR file_url IS NOT NULL", name="check_media_has_location"),
	)

	id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
	)
	object_key: Mapped[str | None] = mapped_column(Text)
	bucket: Mapped[str | None] = mapped_column(String(63))
	file_url: Mapped[str | None] = mapped_column(Text)
	content_type: Mapped[str] = mapped_column(String(100), server_default="image/png", default="image/png")
	size_bytes: Mapped[int] = mapped_column(BigInteger, server_default="0", default=0)
	entity_type: Mapped[str] = mapped_column(String(100))
	entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
	is_public: Mapped[bool] = mapped_column(Boolean, server_default="false", default=False)
	owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
	created_at: Mapped[datetime] = mapped_column(server_default=func.now())
