"""Persistent, revisioned drafts shared by AI suggestions and form editing."""
from datetime import datetime
from sqlalchemy import String, Integer, JSON, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.utils.identifiers import gen_uuid


class ModelingDraft(Base):
    __tablename__ = "modeling_drafts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(200))
    scenario: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    proposal: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    materialized: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ModelingDraftEvent(Base):
    __tablename__ = "modeling_draft_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    draft_id: Mapped[str] = mapped_column(String(36), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(40))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
