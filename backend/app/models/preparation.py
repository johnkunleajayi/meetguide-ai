"""Persistent preparation metadata, never live transcripts or cue answers."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Preparation(Base):
    __tablename__ = "session_preparations"
    __table_args__ = (UniqueConstraint("id", "user_id", name="uq_preparation_owner"),)
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(64))
    objective: Mapped[str] = mapped_column(String(600))
    technical_interview: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    coding_language: Mapped[str] = mapped_column(String(20), default="auto", server_default="auto")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PreparationDocument(Base):
    __tablename__ = "preparation_documents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["preparation_id", "user_id"],
            ["session_preparations.id", "session_preparations.user_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["document_id", "user_id"],
            ["context_documents.id", "context_documents.user_id"],
            ondelete="CASCADE",
        ),
    )
    preparation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    document_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    context_role: Mapped[str] = mapped_column(String(64))


class ActivePreparation(Base):
    __tablename__ = "active_preparations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["preparation_id", "user_id"],
            ["session_preparations.id", "session_preparations.user_id"],
            ondelete="CASCADE",
        ),
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    preparation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
