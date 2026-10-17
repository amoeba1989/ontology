"""OwlDocument — OWL 编辑器文档草稿。

编辑器（WebVowlEditor）的工作文档持久化载体：
- content 为编辑器完整文档 JSON（classes / objectProperties / dataProperties / individuals / namespaces）
- revision 乐观锁：多人/多端保存时防覆盖
- domain 为场景标签（drone / shopping / ...），与本体中心、血缘的场景切换口径一致

注意：编辑器草稿 ≠ 已发布本体。草稿物化为 OntologyEntity 走 /entities/from-file
或编辑器「发布」动作，保持构建 → 审核 → 发布流水线不变。
"""
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.utils.identifiers import gen_uuid


class OwlDocument(Base):
    __tablename__ = "owl_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    namespace_iri: Mapped[str | None] = mapped_column(String(255))
    domain: Mapped[str | None] = mapped_column(String(50))
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
