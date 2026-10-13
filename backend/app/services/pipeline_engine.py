"""PipelineEngine — 真实 Extract→Transform→Load 执行引擎。

复用平台唯一执行闸口 ExecuteService.execute_on_connection（带 AST 审查/参数化/
限流/审计/凭据加密）。engine="real" 的管道跑本引擎；engine="mock" 仍走旧的假进度。

约束（由闸口决定）：
- 禁 DDL —— 目标表必须预先存在，引擎只做 DML（INSERT / DELETE）。
- 写入要求 target Connection.writable=True。
- 全程参数化绑定，杜绝注入。

config_json 结构：
  {
    "source": {"connection_id": "...", "query": "SELECT ..."},
    "transform": {"column_map": [{"from":"src","to":"dst","cast":"int|float|str|bool"}]},
    "target": {"connection_id": "...", "table": "orders", "write_mode": "append|upsert|truncate_insert"},
    "upsert_keys": ["order_id"]
  }
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.pipeline import Pipeline, PipelineRun
from app.services.data_plane.execute_service import ExecuteService, ExecuteBlocked

logger = logging.getLogger(__name__)

_BATCH = 200
_DEFAULT_STEPS = ["抽取", "转换", "加载"]


class PipelineConfigError(RuntimeError):
    """配置不合法（缺字段、目标表不存在、不可写等）。"""


def _cast(value, cast: str | None):
    if cast in (None, "", "auto") or value is None:
        return value
    try:
        if cast == "int":
            return int(float(value))
        if cast == "float":
            return float(value)
        if cast == "str":
            return str(value)
        if cast == "bool":
            if isinstance(value, str):
                return value.strip().lower() in ("1", "true", "yes", "y")
            return bool(value)
    except (ValueError, TypeError):
        return None
    return value


def validate_config(cfg: dict) -> dict:
    """校验并返回规范化 config；不合法抛 PipelineConfigError。"""
    cfg = cfg or {}
    src = cfg.get("source") or {}
    tgt = cfg.get("target") or {}
    if not src.get("connection_id") or not (src.get("query") or "").strip():
        raise PipelineConfigError("source.connection_id 与 source.query 必填")
    if not tgt.get("connection_id") or not (tgt.get("table") or "").strip():
        raise PipelineConfigError("target.connection_id 与 target.table 必填")
    mode = (tgt.get("write_mode") or "append").lower()
    if mode not in ("append", "upsert", "truncate_insert"):
        raise PipelineConfigError("write_mode 仅支持 append|upsert|truncate_insert")
    if mode == "upsert" and not (cfg.get("upsert_keys") or []):
        raise PipelineConfigError("upsert 模式必须提供 upsert_keys")
    return cfg


def _extract(db: Session, cfg: dict) -> tuple[list[str], list[list]]:
    src = cfg["source"]
    res = ExecuteService(db).execute_on_connection(
        connection_id=src["connection_id"],
        sql=src["query"],
        params=src.get("params") or {},
        purpose="pipeline.extract",
    )
    return res.columns, res.rows


def _transform(columns: list[str], rows: list[list], cfg: dict) -> tuple[list[str], list[list]]:
    col_map = ((cfg.get("transform") or {}).get("column_map")) or []
    if not col_map:
        return columns, rows
    idx = {name: i for i, name in enumerate(columns)}
    resolved = []
    for m in col_map:
        frm = m.get("from")
        if frm not in idx:
            raise PipelineConfigError(f"列映射源字段不存在: {frm}")
        resolved.append((idx[frm], m.get("to") or frm, m.get("cast")))
    out_cols = [r[1] for r in resolved]
    out_rows = [[_cast(row[i], cast) for (i, _to, cast) in resolved] for row in rows]
    return out_cols, out_rows


def _insert_sql(table: str, cols: list[str], n: int) -> tuple[str, dict]:
    """构造多行参数化 INSERT，返回 (sql, 单批 params 模板的键列表)。"""
    col_list = ", ".join(cols)
    value_rows = []
    keys = []
    for r in range(n):
        ph = []
        for c in range(len(cols)):
            key = f"v{r}_{c}"
            ph.append(f":{key}")
            keys.append(key)
        value_rows.append("(" + ", ".join(ph) + ")")
    sql = f"INSERT INTO {table} ({col_list}) VALUES " + ", ".join(value_rows)
    return sql, keys


def _load(db: Session, cfg: dict, cols: list[str], rows: list[list]) -> int:
    tgt = cfg["target"]
    conn_id = tgt["connection_id"]
    table = tgt["table"]
    mode = (tgt.get("write_mode") or "append").lower()
    exec_svc = ExecuteService(db)
    written = 0

    if mode == "truncate_insert":
        exec_svc.execute_on_connection(
            connection_id=conn_id, sql=f"DELETE FROM {table}",
            purpose="pipeline.load.truncate", write=True,
        )

    upsert_keys = cfg.get("upsert_keys") or []
    # A full refresh with no results must clear stale rows too.
    if not rows:
        return 0
    key_idx = {c: i for i, c in enumerate(cols)}

    for start in range(0, len(rows), _BATCH):
        batch = rows[start:start + _BATCH]
        if mode == "upsert":
            missing = [k for k in upsert_keys if k not in key_idx]
            if missing:
                raise PipelineConfigError(f"upsert 主键不在输出列中: {missing}")
            # 先按主键批量删，再插 —— 纯 DML，跨库通用，避免方言化 upsert 语法
            conds = " AND ".join(f"{k} = :{k}" for k in upsert_keys)
            for row in batch:
                params = {k: row[key_idx[k]] for k in upsert_keys}
                exec_svc.execute_on_connection(
                    connection_id=conn_id,
                    sql=f"DELETE FROM {table} WHERE {conds}",
                    params=params, purpose="pipeline.load.upsert_delete", write=True,
                )
        sql, keys = _insert_sql(table, cols, len(batch))
        params = {}
        for r, row in enumerate(batch):
            for c in range(len(cols)):
                params[f"v{r}_{c}"] = row[c]
        exec_svc.execute_on_connection(
            connection_id=conn_id, sql=sql, params=params,
            purpose="pipeline.load.insert", write=True,
        )
        written += len(batch)
    return written


def _set_progress(db: Session, run: PipelineRun, idx: int, total: int, label: str) -> None:
    run.step_index = idx
    run.step_label = label
    run.progress = min(99, int(idx / max(1, total) * 100))
    db.commit()


def execute_run(run_id: str, session_factory=None) -> None:
    """在后台线程中执行一次真实运行；自管 Session，异常落 run.error。"""
    from app.database import SessionLocal
    db = (session_factory or SessionLocal)()
    try:
        run = db.get(PipelineRun, run_id)
        if not run:
            return
        pipeline = db.get(Pipeline, run.pipeline_id)
        if not pipeline:
            run.status = "error"
            run.error = "管线不存在"
            db.commit()
            return
        cfg = validate_config(pipeline.config_json or {})
        steps = list(pipeline.steps or []) or _DEFAULT_STEPS
        # 保证至少 3 段标签
        while len(steps) < 3:
            steps.append(_DEFAULT_STEPS[len(steps)])
        started = datetime.utcnow()

        _set_progress(db, run, 0, 3, steps[0])
        columns, rows = _extract(db, cfg)
        run.records_read = len(rows)
        db.commit()

        _set_progress(db, run, 1, 3, steps[1])
        out_cols, out_rows = _transform(columns, rows, cfg)

        _set_progress(db, run, 2, 3, steps[2])
        written = _load(db, cfg, out_cols, out_rows)

        dur = int((datetime.utcnow() - started).total_seconds() * 1000)
        run.records_written = written
        run.records = written
        run.status = "success"
        run.step_index = 2
        run.step_label = steps[2]
        run.progress = 100
        run.duration_ms = dur
        run.finished_at = datetime.utcnow()
        run.log_tail = f"读取 {len(rows)} 行，写入 {written} 行"
        pipeline.status = "success"
        pipeline.last_run_at = run.finished_at
        pipeline.last_records = written
        pipeline.last_objects = written
        pipeline.last_duration_ms = dur
        db.commit()
    except ExecuteBlocked as e:
        _fail(db, run_id, f"执行被拒绝：{e.detail or e.reason}")
    except PipelineConfigError as e:
        _fail(db, run_id, f"配置错误：{e}")
    except Exception as e:  # noqa: BLE001
        logger.exception("pipeline run failed: %s", e)
        _fail(db, run_id, f"运行失败：{e}")
    finally:
        db.close()


def _fail(db: Session, run_id: str, msg: str) -> None:
    try:
        run = db.get(PipelineRun, run_id)
        if run:
            run.status = "error"
            run.error = msg[:1000]
            run.log_tail = msg[:1000]
            run.finished_at = datetime.utcnow()
            p = db.get(Pipeline, run.pipeline_id)
            if p:
                p.status = "error"
            db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("failed to persist pipeline error")
        db.rollback()


def preview(pipeline_id: str, limit: int = 20) -> dict:
    """Dry-run：只跑 Extract+Transform，返回前 N 行，不落库。"""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        pipeline = db.get(Pipeline, pipeline_id)
        if not pipeline:
            raise PipelineConfigError("管线不存在")
        cfg = validate_config(pipeline.config_json or {})
        columns, rows = _extract(db, cfg)
        out_cols, out_rows = _transform(columns, rows, cfg)
        return {
            "records_read": len(rows),
            "columns": out_cols,
            "rows": out_rows[:limit],
            "target_table": cfg["target"]["table"],
            "write_mode": (cfg["target"].get("write_mode") or "append"),
        }
    finally:
        db.close()
