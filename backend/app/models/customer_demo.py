"""Additive demo installation manifest and durable skill execution evidence."""
from datetime import datetime
from sqlalchemy import String, JSON, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.utils.identifiers import gen_uuid


class CustomerDemoPack(Base):
    __tablename__ = "customer_demo_packs"
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), unique=True)
    resources: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="installing")
    report: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SkillRun(Base):
    __tablename__ = "skill_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    skill_id: Mapped[str] = mapped_column(String(36), index=True)
    skill_version: Mapped[int] = mapped_column(Integer, default=0)
    user_id: Mapped[str] = mapped_column(String(36), default="")
    source: Mapped[str] = mapped_column(String(100), default="manual")
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20))
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
