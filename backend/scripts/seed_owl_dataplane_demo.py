# -*- coding: utf-8 -*-
"""对齐 OWL 本体的数据面演示种子（幂等，确定性入库数据，非运行期随机）。

为 drone / shopping 两个场景的每个本体实体，在其属性基础上生成一张演示源表，
写入若干确定性样例行，并在平台库登记：连接 → 资产 → 对象绑定（→ 血缘 binds_to 边）
→ mock 管道。从而 /data/connections、/data/assets、/data/pipeline、/data/lineage
四个页面都有与本体一致的真实可查数据，且不新增/污染本体实体。

用法：cd backend && python -m scripts.seed_owl_dataplane_demo
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

from app.database import SessionLocal
from app.models.asset import Asset
from app.models.connection import Connection
from app.models.entity import OntologyEntity
from app.models.object_binding import ObjectBinding
from app.models.pipeline import Pipeline
from app.services.data_plane.lineage_service import LineageService

BACKEND_ROOT = Path(__file__).resolve().parents[1]
GEN_AT = datetime(2026, 10, 1, 8, 0, 0)  # 固定基准时刻，保证确定性
ROWS_PER_TABLE = 4

DOMAINS = {
    "drone": {"conn_name": "无人机反制数据演示库", "db": "drone_dataplane_demo.db", "color": "#f59e0b"},
    "shopping": {"conn_name": "电商数据演示库", "db": "shopping_dataplane_demo.db", "color": "#2E5BFF"},
}

# 本体属性 type → SQLite 列类型
SQL_TYPE = {
    "string": "TEXT", "text": "TEXT", "number": "REAL", "float": "REAL",
    "integer": "INTEGER", "int": "INTEGER", "boolean": "INTEGER", "bool": "INTEGER",
    "date": "TEXT", "datetime": "TEXT",
}


def _demo_value(attr, i: int):
    """按属性名/类型生成确定性样例值（同一入参恒等输出）。"""
    name, t = attr.name, (attr.type or "string").lower()
    if t in ("integer", "int"):
        return i + 1
    if t in ("number", "float"):
        return round((i + 1) * 1.5, 2)
    if t in ("boolean", "bool"):
        return i % 2
    if t in ("date", "datetime"):
        return (GEN_AT + timedelta(days=i)).strftime("%Y-%m-%d %H:%M:%S")
    # 字符串：常见枚举列给可读值，其余用 名称_序号
    enums = ((attr.constraints_json or {}).get("enumValues")) if isinstance(attr.constraints_json, dict) else None
    if enums:
        return enums[i % len(enums)]
    low = name.lower()
    if "status" in low:
        return ["active", "pending", "done", "closed"][i % 4]
    return f"{name}_{i + 1}"


def _build_demo_db(db_path: Path, entities) -> None:
    con = sqlite3.connect(db_path)
    try:
        for e in entities:
            table = e.name
            attrs = list(e.attributes or [])
            if not attrs:
                continue
            cols = ", ".join(f'"{a.name}" {SQL_TYPE.get((a.type or "string").lower(), "TEXT")}' for a in attrs)
            con.execute(f'DROP TABLE IF EXISTS "{table}"')
            con.execute(f'CREATE TABLE "{table}" ({cols})')
            ph = ",".join("?" * len(attrs))
            for i in range(ROWS_PER_TABLE):
                vals = [_demo_value(a, i) for a in attrs]
                con.execute(f'INSERT INTO "{table}" VALUES ({ph})', vals)
        con.commit()
    finally:
        con.close()


def _pk_column(e) -> str | None:
    cfg = e.config_json or {}
    if isinstance(cfg, dict) and cfg.get("primary_key"):
        return cfg["primary_key"]
    for a in (e.attributes or []):
        if a.required:
            return a.name
    return (e.attributes[0].name if e.attributes else None)


def main() -> int:
    db = SessionLocal()
    try:
        total_binding = total_asset = total_lineage = total_pipe = 0
        for domain, meta in DOMAINS.items():
            entities = db.query(OntologyEntity).filter(OntologyEntity.domain == domain).all()
            if not entities:
                print(f"[{domain}] 无实体，跳过")
                continue

            db_path = BACKEND_ROOT / meta["db"]
            _build_demo_db(db_path, entities)
            print(f"[{domain}] 演示库 {db_path.name} 建表 {len(entities)} 张")

            # 连接（幂等按名）
            conn = db.query(Connection).filter(Connection.name == meta["conn_name"]).first()
            if not conn:
                conn = Connection(
                    name=meta["conn_name"], category="database", type="sqlite",
                    host="", port=0, database=str(db_path),
                    description=f"{domain} 场景数据面演示库（按本体属性自动建表）",
                    status="active", enabled=True, last_test_ok=True, last_test_at=datetime.utcnow(),
                )
                db.add(conn)
                db.flush()
                print(f"[{domain}] 新建连接 {conn.id}")
            else:
                conn.database = str(db_path)

            lineage = LineageService(db)
            for e in entities:
                attrs = list(e.attributes or [])
                if not attrs:
                    continue
                table = e.name

                # 资产（幂等：同连接同名）
                asset = db.query(Asset).filter(Asset.connection_id == conn.id, Asset.name == table).first()
                snapshot = [
                    {"name": a.name, "type": (a.type or "string"), "nullable": not a.required,
                     "is_pk": a.name == _pk_column(e), "comment": a.description or ""}
                    for a in attrs
                ]
                if not asset:
                    asset = Asset(
                        name=table, kind="table", connection_id=conn.id,
                        locator={"table": table}, schema_snapshot=snapshot,
                        schema_synced_at=datetime.utcnow(), primary_key=[_pk_column(e)] if _pk_column(e) else None,
                        profile={"row_count": ROWS_PER_TABLE, "sampled_at": datetime.utcnow().isoformat() + "Z"},
                        domain=domain, tags=["demo", domain], status="active",
                        description=f"{e.name_cn}（{table}）演示资产",
                    )
                    db.add(asset)
                    db.flush()
                    total_asset += 1

                # 绑定（幂等：object_type+asset+role 唯一）
                binding = db.query(ObjectBinding).filter(
                    ObjectBinding.object_type_id == e.id, ObjectBinding.asset_id == asset.id,
                    ObjectBinding.role == "primary",
                ).first()
                if not binding:
                    fm = [{"attribute_id": a.id, "source_column": a.name, "transform": None} for a in attrs]
                    binding = ObjectBinding(
                        object_type_id=e.id, asset_id=asset.id, role="primary",
                        field_mappings=fm, id_column=_pk_column(e), status="active",
                    )
                    db.add(binding)
                    db.flush()
                    total_binding += 1

                # 血缘边：asset → object_type（binds_to）
                lineage.upsert_binding(asset.id, e.id, via_module="demo-seed")
                total_lineage += 1

                # mock 管道（幂等按名；steps 必须是字符串标签，与 PipelineOut/worker 一致）
                pipe_name = f"[{e.name_cn}] 接入演示管道"
                step_labels = ["Extract", "Transform", "Load"]
                pipe = db.query(Pipeline).filter(Pipeline.name == pipe_name).first()
                if not pipe:
                    db.add(Pipeline(
                        name=pipe_name, description=f"演示：从 {table} 抽取并加载到 {e.name}",
                        source=table, target=f"ontology:{e.name}",
                        datasource_id=conn.id,
                        steps=step_labels,
                        tags=["demo", domain], engine="mock", status="idle", step_duration_ms=1200,
                    ))
                    total_pipe += 1
                elif any(not isinstance(s, str) for s in (pipe.steps or [])):
                    # 自愈：修正历史误写的 dict 步骤（否则 /pipelines 序列化 500）
                    pipe.steps = step_labels
                    total_pipe += 1

        db.commit()
        print(f"\n完成：资产 +{total_asset}｜绑定 +{total_binding}｜血缘边 {total_lineage}｜管道 +{total_pipe}")
        print("刷新 /data/connections、/data/assets、/data/pipeline、/data/lineage 查看。")
        return 0
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        import traceback
        traceback.print_exc()
        print(f"执行失败已回滚：{exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
