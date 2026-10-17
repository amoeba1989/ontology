# -*- coding: utf-8 -*-
"""无人机黑飞场景 OWL 本体导入脚本。

读取项目根目录 owl/drone-black-flight-ontology.owl（对齐 docs/mqtt消息.txt 遥测契约），
经 app.services.file_import.parse_owl_ontology 解析落库，并补齐 OWL 无法表达的
平台语义：tier 分层、primary_key、required、枚举约束、关系真实基数、domain 场景归属。

幂等保证：
- 8 个目标实体全部已存在 → 跳过解析，仅执行补齐（补齐为幂等更新，可重复执行）；
- 部分存在 → 拒绝导入并提示人工处理（OWL 属性导入无去重，避免属性翻倍）；
- 全部不存在 → 正常解析导入 + 补齐。

用法：cd backend && python scripts/import_drone_owl.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

OWL_PATH = ROOT / "owl" / "drone-black-flight-ontology.owl"

from sqlalchemy.orm import Session  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models.entity import OntologyEntity, EntityAttribute  # noqa: E402
from app.models.relation import EntityRelation  # noqa: E402
from app.services.file_import import parse_owl_ontology  # noqa: E402

DOMAIN = "drone"
NAMESPACE = "drone"

# ── 平台语义补齐配置（确定性映射，非随机） ──────────────────────────

TIERS = {
    "DroneTarget": 1, "DroneObservation": 1, "DroneState": 1,
    "ProtectedZone": 2, "FlightAuthorization": 2, "JammerDevice": 2,
    "RiskAssessment": 3, "WarningEvent": 3,
}

PRIMARY_KEYS = {
    "DroneTarget": "target_key", "DroneObservation": "obs_id",
    "DroneState": "target_key", "ProtectedZone": "zone_id",
    "FlightAuthorization": "auth_id", "JammerDevice": "device_id",
    "RiskAssessment": "assessment_id", "WarningEvent": "event_id",
}

# required 标记：主键 + 场景标识字段
REQUIRED_ATTRS = {
    "DroneTarget": ["target_key", "scenario_id", "entity_name"],
    "DroneObservation": ["obs_id", "scenario_id", "tick", "entity_name"],
    "DroneState": ["target_key"],
    "ProtectedZone": ["zone_id", "zone_name"],
    "FlightAuthorization": ["auth_id", "auth_target_key", "valid_until"],
    "JammerDevice": ["device_id"],
    "RiskAssessment": ["assessment_id", "risk_score"],
    "WarningEvent": ["event_id", "warning_type", "priority"],
}

# 枚举约束（minsim 遥测契约中的取值映射）
ENUM_ATTRS = {
    ("DroneState", "state_motion_mode"): {
        "enumValues": ["0", "1", "2", "3", "4", "5", "6"],
        "enumLabels": ["静止", "巡航", "失控", "下坠", "返航", "已摧毁", "沿航路"],
    },
    ("DroneState", "state_faction_side"): {
        "enumValues": ["0", "1", "2"],
        "enumLabels": ["中立", "红方", "蓝方"],
    },
    ("DroneTarget", "tracking_status"): {
        "enumValues": ["tracking", "lost"],
        "enumLabels": ["跟踪中", "已丢失"],
    },
    ("ProtectedZone", "zone_type"): {
        "enumValues": ["core", "backup", "restricted"],
        "enumLabels": ["核心管制区", "备用区", "限制区"],
    },
    ("FlightAuthorization", "auth_status"): {
        "enumValues": ["valid", "expired", "revoked"],
        "enumLabels": ["有效", "已过期", "已撤销"],
    },
    ("JammerDevice", "jammer_style"): {
        "enumValues": ["0", "1", "2"],
        "enumLabels": ["阻塞", "瞄准(点频)", "扫频"],
    },
    ("RiskAssessment", "risk_level"): {
        "enumValues": ["low", "medium", "high", "critical"],
        "enumLabels": ["低", "中", "高", "极高"],
    },
    ("WarningEvent", "warning_type"): {
        "enumValues": ["zone_intrusion", "no_authorization", "approach",
                       "gnss_lost", "rc_lost", "destruction"],
        "enumLabels": ["保护区侵入", "无授权飞行", "接近趋势",
                       "导航失锁", "遥控中断", "目标毁伤"],
    },
    ("WarningEvent", "priority"): {
        "enumValues": ["P0", "P1", "P2"],
        "enumLabels": ["P0 紧急", "P1 重要", "P2 一般"],
    },
    ("WarningEvent", "event_status"): {
        "enumValues": ["open", "processing", "closed"],
        "enumLabels": ["待处置", "处置中", "已关闭"],
    },
}

# 关系真实基数（OWL 解析器固定落 1:N，此处按建模语义修正）
RELATION_CARDINALITY = {
    "observed_by": "N:1",       # DroneObservation → DroneTarget
    "current_state": "1:1",     # DroneTarget → DroneState
    "inside_zone": "N:1",       # DroneState → ProtectedZone
    "authorized_by": "N:1",     # DroneTarget → FlightAuthorization
    "assessed_target": "N:1",   # RiskAssessment → DroneTarget
    "triggered_event": "1:N",   # RiskAssessment → WarningEvent
}


def enrich(db: Session) -> dict:
    """幂等补齐 tier / primary_key / required / enum / 基数 / domain。"""
    stats = {"tier": 0, "pk": 0, "required": 0, "enum": 0, "cardinality": 0}

    for name, tier in TIERS.items():
        ent = db.query(OntologyEntity).filter(OntologyEntity.name == name).first()
        if not ent:
            continue
        changed = False
        if ent.tier != tier:
            ent.tier = tier
            changed = True
        if ent.domain != DOMAIN:
            ent.domain = DOMAIN
            changed = True
        schema = dict(ent.config_json or {})
        pk = PRIMARY_KEYS.get(name)
        if pk and schema.get("primary_key") != pk:
            schema["primary_key"] = pk
            schema["namespace"] = schema.get("namespace") or NAMESPACE
            ent.config_json = schema
            changed = True
        if changed:
            stats["tier" if ent.tier == tier else "pk"] += 1
        db.flush()

        # 属性级补齐（required / enum）
        attrs = {a.name: a for a in db.query(EntityAttribute)
                 .filter(EntityAttribute.entity_id == ent.id).all()}
        for attr_name in REQUIRED_ATTRS.get(name, []):
            a = attrs.get(attr_name)
            if a and not a.required:
                a.required = True
                stats["required"] += 1
        for (ent_name, attr_name), enum_cfg in ENUM_ATTRS.items():
            if ent_name != name:
                continue
            a = attrs.get(attr_name)
            if not a:
                continue
            merged = dict(a.constraints_json or {})
            if merged.get("enumValues") != enum_cfg["enumValues"]:
                merged.update(enum_cfg)
                a.constraints_json = merged
                stats["enum"] += 1

    # 关系基数补齐
    rels = db.query(EntityRelation).filter(
        EntityRelation.name.in_(RELATION_CARDINALITY.keys())).all()
    for r in rels:
        target_card = RELATION_CARDINALITY.get(r.name)
        if target_card and r.cardinality != target_card:
            r.cardinality = target_card
            if r.rel_type in ("has_many", "subclass"):
                r.rel_type = "directed"
            stats["cardinality"] += 1

    db.flush()
    return stats


def main() -> None:
    if not OWL_PATH.exists():
        sys.exit(f"OWL 文件不存在: {OWL_PATH}")
    content = OWL_PATH.read_bytes()

    db = SessionLocal()
    try:
        target_names = list(TIERS.keys())
        existing = {
            e.name: e for e in
            db.query(OntologyEntity).filter(OntologyEntity.name.in_(target_names)).all()
        }
        missing = [n for n in target_names if n not in existing]
        with_attrs = [n for n, e in existing.items()
                      if db.query(EntityAttribute)
                      .filter(EntityAttribute.entity_id == e.id).count() > 0]

        if not missing:
            print(f"[skip] {len(existing)} 个实体均已存在，跳过 OWL 解析，仅执行语义补齐…")
        elif existing and not all(n in with_attrs for n in existing):
            # 部分导入过：属性无去重，避免重复，交人工处理
            names = "、".join(existing.keys())
            sys.exit(f"[abort] 检测到部分实体已存在（{names}），"
                     f"OWL 属性导入无去重，请人工核对后清理再导或全量重跑。")
        else:
            result = parse_owl_ontology(content, "xml", db)
            print(f"[import] 实体 +{result.entities_created}（跳过 {result.entities_skipped}）· "
                  f"属性 +{result.attributes_created} · 关系 +{result.relations_created}")
            if result.errors:
                for err in result.errors:
                    print(f"  ! {err}")

        stats = enrich(db)
        db.commit()
        print(f"[enrich] tier/domain/pk 补齐 {stats['tier'] + stats['pk']} 项 · "
              f"required {stats['required']} 项 · 枚举 {stats['enum']} 项 · "
              f"关系基数 {stats['cardinality']} 条")
        print("[done] 无人机黑飞本体已入库：", "、".join(target_names))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
