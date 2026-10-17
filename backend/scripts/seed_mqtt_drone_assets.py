# -*- coding: utf-8 -*-
"""无人机 MQTT 遥测接入 · 资产与本体绑定种子（幂等）。

落地"数据接入 → 资产 → 对象绑定 → 血缘"这条链，让 /data/connections、
/data/assets、/data/lineage 反映 minsim 遥测订阅：
1) MQTT broker 连接（message_queue/mqtt）——实时订阅源；
2) 遥测落库连接（database/sqlite → drone_mqtt_landing.db）——可查询的落库层；
3) 观测/状态/目标 三张落库表注册为资产，并按属性名 1:1 绑定到无人机本体，
   生成 binds_to 血缘边。

用法：cd backend && python -m scripts.seed_mqtt_drone_assets
"""
from __future__ import annotations

import sys
from datetime import datetime

from app.database import SessionLocal
from app.models.asset import Asset
from app.models.connection import Connection
from app.models.entity import OntologyEntity
from app.models.object_binding import ObjectBinding
from app.services.data_plane.lineage_service import LineageService
from app.services.data_plane.mqtt_ingest import LANDING_DB, ensure_schema

MQTT_CONN_NAME = "无人机遥测 MQTT (minsim)"
LANDING_CONN_NAME = "无人机遥测落库"

# 本体实体 → 落库表 → 主键列
TABLES = [
    ("DroneObservation", "drone_observation", "obs_id"),
    ("DroneState", "drone_state", "target_key"),
    ("DroneTarget", "drone_target", "target_key"),
]


def _get_or_create_conn(db, **fields) -> Connection:
    conn = db.query(Connection).filter(Connection.name == fields["name"]).first()
    if not conn:
        conn = Connection(**fields)
        db.add(conn)
        db.flush()
        print(f"  + 连接 {conn.name} ({conn.id})")
    else:
        for k, v in fields.items():
            if k != "name":
                setattr(conn, k, v)
        print(f"  * 连接已存在，更新 {conn.name}")
    return conn


def main() -> int:
    db = SessionLocal()
    try:
        # 1) MQTT broker 连接（实时订阅源；启动时 lifespan 会拉起订阅者）
        _get_or_create_conn(
            db,
            name=MQTT_CONN_NAME, category="message_queue", type="mqtt",
            host="127.0.0.1", port=1883, database="",
            params={"topic_prefix": "minsim", "client_id": "ontology-ingest", "qos": 0},
            description="minsim 仿真引擎 MQTT broker，订阅 minsim/telemetry 实时遥测",
            status="active", enabled=True, writable=False,
        )

        # 2) 落库连接（sqlite，可查询）
        ensure_schema(LANDING_DB)
        landing = _get_or_create_conn(
            db,
            name=LANDING_CONN_NAME, category="database", type="sqlite",
            host="", port=0, database=str(LANDING_DB),
            params=None,
            description="MQTT 遥测降采样落库层（观测 append-only / 状态 upsert / 目标稳定对象）",
            status="active", enabled=True, writable=True, last_test_ok=True, last_test_at=datetime.utcnow(),
        )

        lineage = LineageService(db)
        n_asset = n_bind = 0
        for ent_name, table, pk in TABLES:
            ent = db.query(OntologyEntity).filter(
                OntologyEntity.name == ent_name, OntologyEntity.domain == "drone").first()
            if not ent:
                print(f"  ! 本体实体缺失，跳过：{ent_name}")
                continue
            attrs = list(ent.attributes or [])
            snapshot = [{
                "name": a.name, "type": (a.type or "string"), "nullable": not a.required,
                "is_pk": a.name == pk, "comment": a.description or "",
            } for a in attrs]

            asset = db.query(Asset).filter(
                Asset.connection_id == landing.id, Asset.name == table).first()
            if not asset:
                asset = Asset(
                    name=table, kind="table", connection_id=landing.id,
                    locator={"table": table}, schema_snapshot=snapshot,
                    schema_synced_at=datetime.utcnow(), primary_key=[pk],
                    profile={"row_count": 0, "sampled_at": datetime.utcnow().isoformat() + "Z"},
                    domain="drone", tags=["mqtt", "realtime", "drone"], status="active",
                    description=f"{ent.name_cn}（{table}）· MQTT 遥测落库表",
                )
                db.add(asset)
                db.flush()
                n_asset += 1
            else:
                asset.schema_snapshot = snapshot
                asset.primary_key = [pk]

            binding = db.query(ObjectBinding).filter(
                ObjectBinding.object_type_id == ent.id, ObjectBinding.asset_id == asset.id,
                ObjectBinding.role == "primary").first()
            if not binding:
                fm = [{"attribute_id": a.id, "source_column": a.name, "transform": None} for a in attrs]
                binding = ObjectBinding(
                    object_type_id=ent.id, asset_id=asset.id, role="primary",
                    field_mappings=fm, id_column=pk, status="active",
                )
                db.add(binding)
                db.flush()
                n_bind += 1

            lineage.upsert_binding(asset.id, ent.id, via_module="mqtt-ingest")
            print(f"  ✓ {table} → {ent_name}（{len(attrs)} 字段映射，binds_to 血缘）")

        db.commit()
        print(f"\n完成：资产 +{n_asset}｜绑定 +{n_bind}｜血缘边 {len(TABLES)}")
        print("刷新 /data/connections、/data/assets、/data/lineage 查看 MQTT 遥测接入链路。")
        print("提示：真实 broker 起来后，重启后端即自动订阅落库；离线可用 scripts.replay_mqtt_demo 回放样例。")
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
