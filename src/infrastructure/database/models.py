import uuid
from datetime import datetime
from typing import List, Optional
from sqlalchemy import String, Text, Boolean, Integer, ForeignKey, CheckConstraint, Index, Table, Column
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func, text
from sqlalchemy.dialects.postgresql import UUID


class Base(DeclarativeBase):
	pass


# Association table for many-to-many relationship between Character and Scene
character_scene = Table(
	"character_scene",
	Base.metadata,
	Column("character_id", UUID(as_uuid=True), ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True),
	Column("scene_id", UUID(as_uuid=True), ForeignKey("scenes.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
	__tablename__ = "users"

	id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
	)
	test_username: Mapped[Optional[str]] = mapped_column(String(255))
	google_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
	crystal_balance: Mapped[int] = mapped_column(Integer, server_default="1000", default=1000)

	characters: Mapped[List["Character"]] = relationship(back_populates="owner")
	scenes: Mapped[List["Scene"]] = relationship(back_populates="owner")
	chats: Mapped[List["Chat"]] = relationship(back_populates="user")


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
	scenes: Mapped[List["Scene"]] = relationship(back_populates="characters", secondary="character_scene")


class Scene(Base):
	__tablename__ = "scenes"

	id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
	)
	owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
	title: Mapped[str] = mapped_column(Text)
	description: Mapped[str] = mapped_column(Text)
	initial_message_text: Mapped[str] = mapped_column(Text)
	background_prompt: Mapped[str] = mapped_column(Text)

	owner: Mapped["User"] = relationship(back_populates="scenes")
	chats: Mapped[List["Chat"]] = relationship(back_populates="scene")
	characters: Mapped[List["Character"]] = relationship(back_populates="scenes", secondary="character_scene")


class Chat(Base):
	__tablename__ = "chats"

	id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
	)
	name: Mapped[str] = mapped_column(Text)
	user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
	scene_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("scenes.id", ondelete="SET NULL"))
	created_at: Mapped[datetime] = mapped_column(server_default=func.now())

	user: Mapped["User"] = relationship(back_populates="chats")
	scene: Mapped[Optional["Scene"]] = relationship(back_populates="chats")
	messages: Mapped[List["Message"]] = relationship(back_populates="chat")


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
	__table_args__ = (Index("idx_media_entity", "entity_type", "entity_id"),)

	id: Mapped[uuid.UUID] = mapped_column(
		UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
	)
	file_url: Mapped[str] = mapped_column(Text)
	entity_type: Mapped[str] = mapped_column(String(100))
	entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
