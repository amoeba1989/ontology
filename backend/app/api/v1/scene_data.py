"""
场景业务数据 API（共享工厂）
按场景 key 参数化：目标/传感器/事件/研判 的只读聚合 + 决策确认/效果回填写入。
military（边海空情）与 drone（无人机反制）复用同一套演示表结构
（target/sensor/behavior_event/assessment/command_decision）与 OODA 闭环逻辑。
规则评估 / 行动执行 / 智能体研判分别复用 /rules、/actions、/agents 既有接口。
"""
import logging
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories.connection_repo import ConnectionRepository

logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parents[3]

SCENE_CONFIGS: dict[str, dict] = {
    "military": {"conn_name": "知彼演示库", "fallback_db": "mil_demo.db", "label": "军事演示库"},
    "drone": {"conn_name": "反制演示库", "fallback_db": "drone_demo.db", "label": "反制演示库"},
}

THREAT_ORDER = {"critical": 0, "hostile": 1, "unknown": 2, "friendly": 3}

_EFFECT_EVENT_TYPE = "处置效果"


def build_scene_router(key: str, cfg: dict) -> APIRouter:
    router = APIRouter(prefix=f"/scenes/{key}", tags=[f"{key}-scene"])

    def _db_path(db: Session) -> str:
        conn = ConnectionRepository(db).find_by_name(cfg["conn_name"])
        if conn and conn.database:
            return conn.database
        return str(_BACKEND_ROOT / cfg["fallback_db"])

    def _check_db(db: Session) -> str:
        path = _db_path(db)
        if not Path(path).exists():
            raise HTTPException(status_code=503, detail=f"{cfg['label']}不存在: {path}")
        return path

    def _query(db: Session, sql: str, params: tuple = ()) -> list[dict]:
        path = _check_db(db)
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in con.execute(sql, params).fetchall()]
        finally:
            con.close()

    def _write(db: Session, sqls: list[tuple[str, tuple]]) -> None:
        path = _check_db(db)
        con = sqlite3.connect(path)
        try:
            for sql, params in sqls:
                con.execute(sql, params)
            con.commit()
        finally:
            con.close()

    def _ensure_decision_table(db: Session) -> None:
        _write(
            db,
            [
                (
                    """CREATE TABLE IF NOT EXISTS command_decision (
                        decision_id TEXT PRIMARY KEY,
                        target_id TEXT NOT NULL,
                        assessment_id TEXT,
                        confirmed_threat TEXT NOT NULL,
                        selected_action_id TEXT,
                        selected_action_name TEXT,
                        order_text TEXT DEFAULT '',
                        decided_by TEXT DEFAULT '指挥员',
                        decided_at TEXT NOT NULL
                    )""",
                    (),
                )
            ],
        )

    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    def _ooda_stage(db: Session, target_id: str) -> str:
        """返回目标当前所处的 OODA 阶段：observe/orient/decide/act/closed"""
        if not _query(db, "SELECT 1 FROM behavior_event WHERE target_id=? LIMIT 1", (target_id,)):
            return "observe"
        if not _query(db, "SELECT 1 FROM assessment WHERE target_id=? LIMIT 1", (target_id,)):
            return "orient"
        _ensure_decision_table(db)
        if not _query(db, "SELECT 1 FROM command_decision WHERE target_id=? LIMIT 1", (target_id,)):
            return "decide"
        if not _query(
            db,
            "SELECT 1 FROM behavior_event WHERE target_id=? AND event_type=? LIMIT 1",
            (target_id, _EFFECT_EVENT_TYPE),
        ):
            return "act"
        return "closed"

    @router.get("/overview")
    def overview(db: Session = Depends(get_db)):
        targets = _query(db, "SELECT threat_level FROM target")
        sensors = _query(db, "SELECT is_active FROM sensor")
        events = _query(db, "SELECT COUNT(*) AS n FROM behavior_event")
        assessments = _query(db, "SELECT threat_assessment FROM assessment")
        dist: dict[str, int] = {}
        for t in targets:
            dist[t["threat_level"]] = dist.get(t["threat_level"], 0) + 1
        latest = _query(db, "SELECT MAX(updated_at) AS m FROM target")
        return {
            "targets_total": len(targets),
            "hostile_targets": dist.get("hostile", 0) + dist.get("critical", 0),
            "active_sensors": sum(1 for s in sensors if s["is_active"]),
            "sensors_total": len(sensors),
            "events_total": events[0]["n"] if events else 0,
            "hostile_assessments": sum(
                1 for a in assessments if a["threat_assessment"] in ("hostile", "critical")
            ),
            "assessments_total": len(assessments),
            "threat_distribution": dist,
            "latest_update": (latest[0]["m"] if latest else None),
        }

    @router.get("/targets")
    def targets(db: Session = Depends(get_db)):
        rows = _query(
            db,
            """
            SELECT t.*,
                   (SELECT COUNT(*) FROM behavior_event e WHERE e.target_id = t.target_id) AS event_count,
                   (SELECT a.assessment_id FROM assessment a WHERE a.target_id = t.target_id
                     ORDER BY a.assessed_at DESC LIMIT 1) AS latest_assessment_id
            FROM target t ORDER BY t.updated_at DESC
            """,
        )
        assessments = {a["assessment_id"]: a for a in _query(db, "SELECT * FROM assessment")}
        for r in rows:
            r["latest_assessment"] = assessments.get(r.pop("latest_assessment_id", None))
            r["ooda_stage"] = _ooda_stage(db, r["target_id"])
        rows.sort(key=lambda r: THREAT_ORDER.get(r["threat_level"], 9))
        return rows

    @router.get("/targets/{target_id}/situation")
    def situation(target_id: str, db: Session = Depends(get_db)):
        target = _query(db, "SELECT * FROM target WHERE target_id=?", (target_id,))
        if not target:
            raise HTTPException(status_code=404, detail=f"目标不存在: {target_id}")
        events = _query(
            db,
            "SELECT * FROM behavior_event WHERE target_id=? ORDER BY observed_at DESC",
            (target_id,),
        )
        assessments = _query(
            db,
            "SELECT * FROM assessment WHERE target_id=? ORDER BY assessed_at DESC",
            (target_id,),
        )
        sensors = _query(db, "SELECT * FROM sensor ORDER BY is_active DESC, sensor_id")
        _ensure_decision_table(db)
        decisions = _query(
            db,
            "SELECT * FROM command_decision WHERE target_id=? ORDER BY decided_at DESC",
            (target_id,),
        )
        effects = _query(
            db,
            "SELECT * FROM behavior_event WHERE target_id=? AND event_type=? ORDER BY observed_at DESC",
            (target_id, _EFFECT_EVENT_TYPE),
        )
        return {
            "target": target[0],
            "events": events,
            "assessments": assessments,
            "sensors": sensors,
            "decisions": decisions,
            "effects": effects,
            "high_confidence_events": [e for e in events if (e["confidence"] or 0) >= 0.8],
            "ooda_stage": _ooda_stage(db, target_id),
        }

    class DecisionCreate(BaseModel):
        assessment_id: str
        confirmed_threat: str
        selected_action_id: str | None = None
        selected_action_name: str | None = None
        order_text: str = ""
        decided_by: str = "指挥员"

    @router.post("/targets/{target_id}/decisions", status_code=201)
    def create_decision(target_id: str, body: DecisionCreate, db: Session = Depends(get_db)):
        """指挥席决策确认：确认威胁等级并选定处置行动，生成处置指令记录"""
        if not _query(db, "SELECT 1 FROM target WHERE target_id=? LIMIT 1", (target_id,)):
            raise HTTPException(status_code=404, detail=f"目标不存在: {target_id}")
        if body.confirmed_threat not in THREAT_ORDER:
            raise HTTPException(status_code=422, detail=f"威胁等级非法: {body.confirmed_threat}")
        _ensure_decision_table(db)
        decision_id = f"DEC-{uuid.uuid4().hex[:8].upper()}"
        _write(
            db,
            [
                (
                    """INSERT INTO command_decision
                       (decision_id, target_id, assessment_id, confirmed_threat,
                        selected_action_id, selected_action_name, order_text, decided_by, decided_at)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (
                        decision_id,
                        target_id,
                        body.assessment_id,
                        body.confirmed_threat,
                        body.selected_action_id,
                        body.selected_action_name,
                        body.order_text,
                        body.decided_by,
                        _now(),
                    ),
                )
            ],
        )
        row = _query(db, "SELECT * FROM command_decision WHERE decision_id=?", (decision_id,))
        return {**row[0], "ooda_stage": _ooda_stage(db, target_id)}

    class EffectCreate(BaseModel):
        decision_id: str | None = None
        effect_description: str
        new_threat: str | None = None

    @router.post("/targets/{target_id}/effects", status_code=201)
    def submit_effect(target_id: str, body: EffectCreate, db: Session = Depends(get_db)):
        """行动席效果回填（Assess）：效果写入 behavior_event，回流形成新一轮观察，闭合 OODA 环"""
        if not _query(db, "SELECT 1 FROM target WHERE target_id=? LIMIT 1", (target_id,)):
            raise HTTPException(status_code=404, detail=f"目标不存在: {target_id}")
        if body.new_threat and body.new_threat not in THREAT_ORDER:
            raise HTTPException(status_code=422, detail=f"威胁等级非法: {body.new_threat}")
        event_id = f"EVT-{uuid.uuid4().hex[:8].upper()}"
        sqls: list[tuple[str, tuple]] = [
            (
                """INSERT INTO behavior_event
                   (event_id, target_id, event_type, description, confidence, observed_at)
                   VALUES (?,?,?,?,?,?)""",
                (event_id, target_id, _EFFECT_EVENT_TYPE, body.effect_description, 1.0, _now()),
            )
        ]
        if body.new_threat:
            sqls.append(
                (
                    "UPDATE target SET threat_level=?, updated_at=? WHERE target_id=?",
                    (body.new_threat, _now(), target_id),
                )
            )
        _write(db, sqls)
        row = _query(db, "SELECT * FROM behavior_event WHERE event_id=?", (event_id,))
        return {**row[0], "ooda_stage": _ooda_stage(db, target_id)}

    return router


routers = [build_scene_router(key, cfg) for key, cfg in SCENE_CONFIGS.items()]
