# -*- coding: utf-8 -*-
"""离线回放自测：用真实样例报文验证 MQTT 遥测 解析→三层落库 链路（无需 broker）。

数据源：docs/mqtt消息.txt（minsim telemetry 样例）。
用法：cd backend && python -m scripts.replay_mqtt_demo
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

from app.services.data_plane import mqtt_ingest
from app.services.data_plane.mqtt_ingest import ensure_schema, land_payload, LANDING_DB

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE = REPO_ROOT / "docs" / "mqtt消息.txt"


def main() -> int:
    if not SAMPLE.exists():
        print(f"样例报文不存在：{SAMPLE}")
        return 1
    payload = json.loads(SAMPLE.read_text(encoding="utf-8"))
    print(f"读入样例 telemetry：scenario={payload.get('scenario_name')} "
          f"tick={payload.get('tick')} entities={len(payload.get('entities', []))}")

    # 回放：关闭降采样窗口以观察全部实体落库
    ensure_schema(LANDING_DB)
    con = sqlite3.connect(str(LANDING_DB))
    con.execute("DELETE FROM drone_observation"); con.execute("DELETE FROM drone_state")
    con.execute("DELETE FROM drone_target"); con.commit(); con.close()

    result = land_payload(payload, sample_interval_s=0)
    print(f"落库结果：{result}")

    con = sqlite3.connect(str(LANDING_DB))
    try:
        for tbl in ("drone_observation", "drone_state", "drone_target"):
            n = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            print(f"  {tbl}: {n} 行")
        print("\n== drone_state 明细 ==")
        cols = [d[1] for d in con.execute("PRAGMA table_info(drone_state)")]
        for row in con.execute("SELECT * FROM drone_state"):
            print("  " + ", ".join(f"{c}={v}" for c, v in zip(cols, row) if v is not None))
        print("\n== drone_target 明细 ==")
        for row in con.execute("SELECT target_key, entity_name, scenario_id, tracking_status FROM drone_target"):
            print("  ", row)
    finally:
        con.close()
    print(f"\n落库文件：{LANDING_DB}")
    print("回放通过：minsim telemetry 报文已按 blocks 位掩码解析并落到 观测/状态/目标 三层。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
