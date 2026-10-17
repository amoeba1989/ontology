import math
import re
import time
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Any
from datetime import datetime

from app.database import get_db
from app.models import OntologyEntity, EntityAttribute, EntityRelation, BusinessRule, EntityAction, AuditLog
from app.models.asset import Asset

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# ── 本体态势舱（Three.js 工作台）数据聚合 ──────────────────────────

DOMAIN_LABELS = {"military": "军事场景"}
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# 事件摘要里优先展示的字段（实例行 → 一句话描述）
_TAG_FIELDS = [
    "event_type", "threat_assessment", "threat_level", "ooda_phase",
    "status", "risk_flag", "member_level", "channel",
    "amount", "confidence", "category", "target_type", "sensor_type",
    "speed_knots", "recommended_action",
]
_WARN_TOKENS = ("hostile", "critical", "high", "risk", "pending", "suspicious",
                "告警", "风险", "高危", "异常", "敌对", "可疑")
_DATE_PRIORITY = ["observed_at", "assessed_at", "created_at", "occurred_at",
                  "event_time", "registered_at", "updated_at", "timestamp"]
_OK_TOKENS = ("benign", "completed", "paid", "active", "normal", "friendly",
              "正常", "完成", "已支付", "无害", "友好")


def _domain_label(key: str | None) -> str:
    return DOMAIN_LABELS.get(key or "") or key or "未分组"


_ROW_COUNT_CACHE: dict[tuple[str, str], tuple[float, int]] = {}


def _table_row_count(db: Session, connection_id: str | None, table: str) -> int | None:
    """真实 COUNT(*)（30s TTL 缓存）；连接不可用或表名非法时返回 None 由调用方兜底。"""
    if not connection_id or not table or not _IDENT_RE.match(table):
        return None
    key = (connection_id, table)
    cached = _ROW_COUNT_CACHE.get(key)
    now = time.time()
    if cached and cached[0] > now:
        return cached[1]
    from app.services.data_plane.execute_service import ExecuteService
    from app.connectors import ConnectorRegistry
    from app.models.connection import Connection
    # 表名可能是 SQL 保留字（如 demo 本体实体 Order），必须按连接方言加标识符引号
    conn = db.get(Connection, connection_id)
    quote = ConnectorRegistry.get(conn.type).quote_identifier() if conn else '"'
    safe_table = f"{quote}{table}{quote}"
    try:
        res = ExecuteService(db).execute_on_connection(
            connection_id=connection_id, sql=f"SELECT COUNT(*) AS n FROM {safe_table}",
            purpose="dashboard.row_count",
        )
        n = int(res.rows[0][0]) if res.rows else 0
    except Exception:
        return None
    _ROW_COUNT_CACHE[key] = (now + 30, n)
    return n


def _as_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip().startswith("{"):
        import json
        try:
            return json.loads(value)
        except ValueError:
            return {}
    return {}


def _iso(value: Any) -> str | None:
    """把 SQLite 的 'YYYY-MM-DD HH:MM:SS' 或 datetime 归一为可字典序排序的 ISO 串。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    s = str(value).strip().replace(" ", "T")
    return s[:19] if s else None


def _query_entities(db: Session, domain: str | None):
    entities = db.query(OntologyEntity).order_by(OntologyEntity.tier, OntologyEntity.name).all()
    if domain:
        entities = [e for e in entities if (e.domain or "") == domain]
    return entities


def _classify(value: Any) -> str:
    text = str(value or "").lower()
    if any(t in text for t in _WARN_TOKENS):
        return "warning"
    if any(t in text for t in _OK_TOKENS):
        return "ok"
    return "info"


def _constraint_text(a: EntityAttribute) -> str:
    """把属性约束压成一句中文展示文本（枚举优先取 enumLabels）。"""
    c = _as_dict(a.constraints_json)
    parts: list[str] = []
    values, labels = c.get("enumValues") or [], c.get("enumLabels") or []
    if values:
        shown = [labels[i] if i < len(labels) and labels[i] else v for i, v in enumerate(values)]
        parts.append("枚举 " + "/".join(str(s) for s in shown))
    if c.get("min") is not None or c.get("max") is not None:
        parts.append(f"范围 {c.get('min', '-∞')}~{c.get('max', '+∞')}")
    if c.get("pattern"):
        parts.append(f"正则 {c['pattern']}")
    if c.get("refTarget"):
        parts.append(f"引用 {c['refTarget']}")
    if a.type == "date":
        parts.append("时间戳")
    return " · ".join(parts)


@router.get("/ontology-scene")
def get_ontology_scene(domain: str | None = None, db: Session = Depends(get_db)):
    """态势舱一次成图：场景列表 + 节点（属性/规则/行动/实例数）+ 关系边。"""
    from app.models.object_binding import ObjectBinding

    all_entities = db.query(OntologyEntity).order_by(OntologyEntity.tier, OntologyEntity.name).all()
    domain_counts: dict[str, int] = {}
    for e in all_entities:
        domain_counts[e.domain or ""] = domain_counts.get(e.domain or "", 0) + 1

    entities = [e for e in all_entities if not domain or (e.domain or "") == domain]
    ids = {e.id for e in entities}
    cn_name = {e.id: e.name_cn for e in entities}

    attrs_by: dict[str, list] = {}
    if ids:
        for a in db.query(EntityAttribute).filter(EntityAttribute.entity_id.in_(ids)).all():
            attrs_by.setdefault(a.entity_id, []).append(a)

    rules_by: dict[str, list] = {}
    actions_by: dict[str, list] = {}
    if ids:
        for a in db.query(EntityAction).filter(EntityAction.entity_id.in_(ids)).all():
            actions_by.setdefault(a.entity_id, []).append(a)
        for r in db.query(BusinessRule).filter(BusinessRule.entity_id.in_(ids)).all():
            rules_by.setdefault(r.entity_id, []).append(r)
    action_by_id = {a.id: a for group in actions_by.values() for a in group}

    inst_count: dict[str, int] = {}
    table_of: dict[str, str] = {}
    asset_of: dict[str, str] = {}
    if ids:
        bindings = db.query(ObjectBinding).filter(
            ObjectBinding.object_type_id.in_(ids),
            ObjectBinding.role == "primary",
            ObjectBinding.status == "active",
        ).all()
        assets = {a.id: a for a in db.query(Asset).all()}
        for b in bindings:
            asset = assets.get(b.asset_id)
            if not asset:
                continue
            asset_of[b.object_type_id] = asset.id
            table = (asset.locator or {}).get("table", "")
            table_of[b.object_type_id] = table
            real = _table_row_count(db, asset.connection_id, table)
            inst_count[b.object_type_id] = real if real is not None else (asset.profile or {}).get("row_count", 0)

    nodes = []
    for e in entities:
        rules = []
        for r in sorted(rules_by.get(e.id, []), key=lambda x: (x.priority != "high", x.name)):
            act = action_by_id.get(r.action_id)
            rules.append({
                "id": r.id, "name": r.name,
                "condition_expr": r.condition_expr or "",
                "action_desc": r.action_desc or "",
                "status": r.status, "priority": r.priority,
                "trigger_count": r.trigger_count or 0,
                "last_triggered": _iso(r.last_triggered),
                "action_name": act.name if act else None,
                "conditions": _as_dict(r.conditions_json),
            })
        nodes.append({
            "id": e.id, "name": e.name, "name_cn": e.name_cn,
            "tier": e.tier, "status": e.status, "domain": e.domain or "",
            "description": e.description or "",
            "instance_count": inst_count.get(e.id, 0),
            "source_table": table_of.get(e.id, ""),
            "asset_id": asset_of.get(e.id, ""),
            "attributes": [
                {
                    "id": a.id, "name": a.name, "type": a.type,
                    "required": bool(a.required), "example": a.example,
                    "description": a.description or "",
                    "source_field": a.source_field,
                    "constraints": _as_dict(a.constraints_json),
                    "constraint_text": _constraint_text(a),
                }
                for a in sorted(attrs_by.get(e.id, []), key=lambda x: (not x.required, x.name))
            ],
            "rules": rules,
            "actions": [
                {"id": a.id, "name": a.name, "action_type": a.action_type,
                 "status": a.status, "description": a.description or ""}
                for a in sorted(actions_by.get(e.id, []), key=lambda x: x.name)
            ],
        })

    # 约束验证状态挂在绑定资产上：没有质量规则 = 无约束（null），
    # 有规则但没跑过评估 = unknown，两者都不能画成"已通过"
    from app.services.data_plane.quality_rule_service import QualityRuleService
    quality = QualityRuleService(db)
    health_cache: dict[str, dict] = {}
    for n in nodes:
        aid = n["asset_id"]
        if aid not in health_cache:
            health_cache[aid] = quality.asset_aggregate_status(aid) if aid else {}
        agg = health_cache[aid]
        rule_count = agg.get("rule_count", 0)
        n["constraint_status"] = agg.get("status") if rule_count else None
        n["constraint_rule_count"] = rule_count
        n["constraint_by_status"] = agg.get("by_status", {})

    rels = db.query(EntityRelation).all()
    edges = [
        {
            "id": r.id, "from_id": r.from_entity_id, "to_id": r.to_entity_id,
            "from_name": cn_name.get(r.from_entity_id, ""), "to_name": cn_name.get(r.to_entity_id, ""),
            "label": r.name, "name_cn": r.name_cn or "",
            "rel_type": r.rel_type, "cardinality": r.cardinality,
            "description": r.description or "",
        }
        for r in rels
        if r.from_entity_id in ids and r.to_entity_id in ids
    ]

    node_ids = {n["id"] for n in nodes}
    for n in nodes:
        n["relation_count"] = sum(1 for r in rels if r.from_entity_id == n["id"] or r.to_entity_id == n["id"])

    return {
        "domains": [
            {"key": k, "label": _domain_label(k), "entity_count": c}
            for k, c in sorted(domain_counts.items(), key=lambda x: (x[0] == "", x[0]))
        ],
        "nodes": nodes,
        "edges": edges,
        "summary": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "domain_count": sum(1 for k in domain_counts if k),
            "attribute_count": sum(len(n["attributes"]) for n in nodes),
            "rule_count": sum(len(n["rules"]) for n in nodes),
            "instance_count": sum(n["instance_count"] for n in nodes if n["id"] in node_ids),
        },
        "active_domain": domain or "",
        "active_domain_label": _domain_label(domain) if domain else "全部场景",
    }


@router.get("/ontology-events")
def get_ontology_events(domain: str | None = None, limit: int = 30, db: Session = Depends(get_db)):
    """态势舱事件流：绑定表实例行（真实查询）+ audit_log 规则/行动执行，按时间升序返回。"""
    from app.models.object_binding import ObjectBinding
    from app.services.data_plane.execute_service import ExecuteService

    limit = max(5, min(int(limit or 30), 120))
    entities = _query_entities(db, domain)
    ids = {e.id for e in entities}
    if not ids:
        return {"events": [], "window": None, "counts": [], "total": 0}

    entity_by_id = {e.id: e for e in entities}
    attrs_by: dict[str, list] = {}
    for a in db.query(EntityAttribute).filter(EntityAttribute.entity_id.in_(ids)).all():
        attrs_by.setdefault(a.entity_id, []).append(a)

    relations = [r for r in db.query(EntityRelation).all()
                 if r.from_entity_id in ids and r.to_entity_id in ids]
    rel_pair = {(r.from_entity_id, r.to_entity_id): r for r in relations}

    def find_rel(a: str | None, b: str | None):
        if not a or not b:
            return None
        return rel_pair.get((a, b)) or rel_pair.get((b, a))

    bindings = db.query(ObjectBinding).filter(
        ObjectBinding.object_type_id.in_(ids),
        ObjectBinding.role == "primary",
        ObjectBinding.status == "active",
    ).all()
    asset_by = {a.id: a for a in db.query(Asset).all()}
    # 外键列名 → 实体 id（行内 *_id 列指向的本体对象）
    idcol_entity = {b.id_column: b.object_type_id for b in bindings if b.id_column}

    inst_events: list[dict] = []
    per_entity = max(3, min(15, math.ceil(limit / max(1, len(bindings)))))
    exec_svc = ExecuteService(db)

    for b in bindings:
        entity = entity_by_id.get(b.object_type_id)
        asset = asset_by.get(b.asset_id)
        if not entity or not asset or asset.kind != "table" or not asset.connection_id:
            continue
        table = (asset.locator or {}).get("table", "")
        if not _IDENT_RE.match(table or ""):
            continue

        date_cols: list[str] = []
        for a in attrs_by.get(entity.id, []):
            if a.type != "date":
                continue
            cand = a.source_field or a.name
            if cand and _IDENT_RE.match(cand) and cand not in date_cols:
                date_cols.append(cand)
        # 只取有时间戳的表进事件流；维表（无时间列）不产生伪事件
        if not date_cols:
            continue
        date_cols.sort(key=lambda c: _DATE_PRIORITY.index(c) if c in _DATE_PRIORITY else 99)

        res = None
        date_col = None
        for col in date_cols:
            try:
                r = exec_svc.execute_on_connection(
                    connection_id=asset.connection_id,
                    sql=f"SELECT * FROM {table} ORDER BY {col} DESC LIMIT :lim",
                    params={"lim": per_entity}, purpose="dashboard.ontology_events",
                )
            except Exception:
                continue
            if col not in r.columns:
                continue
            res, date_col = r, col
            break
        if res is None:
            continue

        for row in res.rows:
            rec = dict(zip(res.columns, row))
            obj_id = str(rec.get(b.id_column or "", "") or "")
            ts = _iso(rec.get(date_col))
            if not ts:
                continue
            label = (str(rec.get("description") or "").strip()
                     or str(rec.get("name") or "").strip()
                     or obj_id or entity.name_cn)
            tags = [
                {"key": k, "value": str(rec[k]), "level": _classify(rec[k])}
                for k in _TAG_FIELDS
                if k in rec and rec[k] not in (None, "")
            ][:4]
            source_id = None
            for k, v in rec.items():
                other = idcol_entity.get(k)
                if other and other != entity.id and v not in (None, ""):
                    source_id = other
                    break
            rel = find_rel(source_id, entity.id)
            level = "warning" if any(t["level"] == "warning" for t in tags) else (
                "ok" if any(t["level"] == "ok" for t in tags) else "info")
            inst_events.append({
                "id": f"inst-{entity.id}-{obj_id}-{len(inst_events)}",
                "kind": "instance",
                "entity_id": entity.id,
                "entity_name": entity.name,
                "entity_name_cn": entity.name_cn,
                "domain": entity.domain or "",
                "object_id": obj_id,
                "label": label,
                "summary": f"{entity.name_cn} {label}",
                "timestamp": ts,
                "level": level,
                "tags": tags,
                "source_entity_id": source_id,
                "source_entity_name_cn": entity_by_id[source_id].name_cn if source_id in entity_by_id else None,
                "relation_id": rel.id if rel else None,
                "relation_label": (rel.name_cn or rel.name) if rel else None,
                "rule_id": None,
            })

    # 规则 / 行动执行流水
    rule_by = {r.id: r for r in db.query(BusinessRule).all()}
    action_by = {a.id: a for a in db.query(EntityAction).all()}
    logs = db.query(AuditLog).filter(
        AuditLog.target_type.in_(["rule", "action"]),
    ).order_by(AuditLog.timestamp.desc()).limit(limit * 2).all()

    ACTION_TEXT = {"evaluate": "规则评估", "execute": "行动执行"}
    log_events: list[dict] = []
    for l in logs:
        ent_id = None
        rule_id = None
        if l.target_type == "rule":
            rule = rule_by.get(l.target_id)
            if not rule:
                continue
            ent_id, rule_id = rule.entity_id, rule.id
            summary = f"{ACTION_TEXT.get(l.action, l.action)} · {l.target_name}"
            level = "warning" if rule.priority == "high" else "info"
            tags = [{"key": "优先级", "value": rule.priority,
                     "level": "warning" if rule.priority == "high" else "info"},
                    {"key": "累计命中", "value": str(rule.trigger_count or 0), "level": "info"}]
        elif l.target_type == "action":
            act = action_by.get(l.target_id)
            if not act:
                continue
            ent_id = act.entity_id
            summary = f"行动执行 · {l.target_name}"
            level = "info"
            tags = [{"key": "行动类型", "value": act.action_type, "level": "info"}]

        if ent_id not in ids:
            continue
        e = entity_by_id[ent_id]
        # 给规则/行动事件挑一条入边，让流星沿关系轨迹飞行
        rel = next((r for r in relations if r.to_entity_id == ent_id), None) \
            or next((r for r in relations if r.from_entity_id == ent_id), None)
        src_id = None
        if rel:
            src_id = rel.from_entity_id if rel.to_entity_id == ent_id else rel.to_entity_id
        log_events.append({
            "id": f"log-{l.id}",
            "kind": "rule_hit" if l.target_type == "rule" else "action_exec",
            "entity_id": ent_id,
            "entity_name": e.name,
            "entity_name_cn": e.name_cn,
            "domain": e.domain or "",
            "object_id": l.target_id,
            "label": l.target_name or "",
            "summary": summary,
            "timestamp": _iso(l.timestamp),
            "level": level if l.status == "success" else "warning",
            "tags": tags,
            "source_entity_id": src_id,
            "source_entity_name_cn": entity_by_id[src_id].name_cn if src_id in entity_by_id else None,
            "relation_id": rel.id if rel else None,
            "relation_label": (rel.name_cn or rel.name) if rel else None,
            "rule_id": rule_id,
            "user_name": l.user_name,
        })

    # 实例事件与执行流水按比例混合，避免执行日志把业务事件挤掉
    inst_events.sort(key=lambda x: x["timestamp"] or "", reverse=True)
    log_events.sort(key=lambda x: x["timestamp"] or "", reverse=True)
    inst_sel = inst_events[:limit]
    log_sel = log_events[:max(4, limit // 3)]
    events = sorted(inst_sel + log_sel, key=lambda x: x["timestamp"] or "")
    events = events[-limit:]
    stamps = [e["timestamp"] for e in events if e["timestamp"]]
    counts: dict[str, int] = {}
    for e in events:
        counts[e["entity_id"]] = counts.get(e["entity_id"], 0) + 1

    return {
        "events": events,
        "window": {"from": min(stamps), "to": max(stamps)} if stamps else None,
        "counts": [{"entity_id": k, "entity_name_cn": entity_by_id[k].name_cn, "count": v}
                   for k, v in sorted(counts.items(), key=lambda x: -x[1])],
        "total": len(events),
    }
