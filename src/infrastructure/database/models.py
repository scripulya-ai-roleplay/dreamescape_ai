import uuid
from datetime import datetime
from typing import List, Optional
from sqlalchemy import String, Text, Boolean, Integer, ForeignKey, CheckConstraint, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func, text
from sqlalchemy.dialects.postgresql import UUID


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    test_username: Mapped[Optional[str]] = mapped_column(String(255))
    google_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    crystal_balance: Mapped[int] = mapped_column(Integer, server_default="1000", default=1000)

    characters: Mapped[List["Character"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    scenes: Mapped[List["Scene"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    chats: Mapped[List["Chat"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Character(Base):
    __tablename__ = 'characters'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    name: Mapped[str] = mapped_column(String(255))
    system_prompt: Mapped[str] = mapped_column(Text)
    is_public: Mapped[bool] = mapped_column(Boolean, server_default="false", default=False)

    owner: Mapped["User"] = relationship(back_populates="characters")
    chats: Mapped[List["Chat"]] = relationship(back_populates="character", cascade="all, delete-orphan")


class Scene(Base):
    __tablename__ = 'scenes'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    title: Mapped[str] = mapped_column(String(255))
    background_prompt: Mapped[str] = mapped_column(Text)

    owner: Mapped["User"] = relationship(back_populates="scenes")
    chats: Mapped[List["Chat"]] = relationship(back_populates="scene", cascade="all, delete-orphan")


class Chat(Base):
    __tablename__ = 'chats'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('characters.id', ondelete='CASCADE'))
    scene_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey('scenes.id', ondelete='SET NULL'))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="chats")
    character: Mapped["Character"] = relationship(back_populates="chats")
    scene: Mapped[Optional["Scene"]] = relationship(back_populates="chats")
    messages: Mapped[List["Message"]] = relationship(back_populates="chat", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = 'messages'
    __table_args__ = (
        CheckConstraint("role IN ('user', 'model', 'system')", name='check_role_valid'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    chat_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('chats.id', ondelete='CASCADE'), index=True)
    role: Mapped[str] = mapped_column(String(50))
    content: Mapped[str] = mapped_column(Text)
    cost_crystals: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    chat: Mapped["Chat"] = relationship(back_populates="messages")


class MediaAsset(Base):
    __tablename__ = 'media_assets'
    __table_args__ = (
        Index('idx_media_entity', 'entity_type', 'entity_id'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    file_url: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
