"""场景中心 — 场景注册表（导航层元数据，工作台页面本身不在本表管理范围）"""
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, String, Text, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.utils.identifiers import gen_uuid


class SceneRegistry(Base):
    __tablename__ = "scene_registry"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    icon: Mapped[str] = mapped_column(String(16), default="🔹")
    color: Mapped[str] = mapped_column(String(20), default="#2E5BFF")
    # 绑定的前端工作台路由；空 = 未配置工作台，点击时前端提示
    route: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    # 场景引用的本体资产：{object_classes:[], rule_ids:[], action_ids:[], agent_ids:[], seats:[]}
    assets: Mapped[Optional[dict]] = mapped_column("assets_json", JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="enabled")  # enabled/disabled
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by: Mapped[str] = mapped_column(String(50), default="admin")
