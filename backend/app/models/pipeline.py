from datetime import datetime

from sqlalchemy import String, Integer, Text, DateTime, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.utils.identifiers import gen_uuid


class Pipeline(Base):
    __tablename__ = "pipelines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(300), default="")
    target: Mapped[str] = mapped_column(String(300), default="")
    datasource_id: Mapped[str | None] = mapped_column(String(36))
    steps: Mapped[list] = mapped_column(JSON, default=list)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    schedule: Mapped[str] = mapped_column(String(120), default="")
    step_duration_ms: Mapped[int] = mapped_column(Integer, default=1500)
    engine: Mapped[str] = mapped_column(String(20), default="mock")
        # mock=仅演示进度；real=走 ExecuteService 真实 Extract→Transform→Load
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)
        # real 引擎配置：{source:{connection_id,query}, transform:{column_map,filter_sql},
        #   target:{connection_id,table,write_mode}, upsert_keys, incremental:{column,last_value}}
    status: Mapped[str] = mapped_column(String(20), default="idle")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_records: Mapped[int | None] = mapped_column(Integer)
    last_objects: Mapped[int | None] = mapped_column(Integer)
    last_duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    pipeline_id: Mapped[str] = mapped_column(String(36), ForeignKey("pipelines.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
    step_index: Mapped[int] = mapped_column(Integer, default=0)
    step_label: Mapped[str] = mapped_column(String(200), default="")
    records: Mapped[int] = mapped_column(Integer, default=0)
    records_read: Mapped[int] = mapped_column(Integer, default=0)
    records_written: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    log_tail: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
