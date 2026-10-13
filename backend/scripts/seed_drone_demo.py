# -*- coding: utf-8 -*-
"""无人机反制场景种子脚本。

与边海空情场景共用同一套演示表结构（target/sensor/behavior_event/assessment），
新建本地库 drone_demo.db + 连接「反制演示库」，并经 HTTP API 幂等灌入本体层：
对象类（DroneTarget/DetectSensor/FlightEvent/ThreatAssessment）、映射、关系、
行动（反制指令通报/空域预警发布）、规则、智能体「无人机反制研判智能体」。

用法：后端运行时直接 `python scripts/seed_drone_demo.py`
（自动以 admin/bonc 登录取 token，也可 SEED_TOKEN=<jwt> 覆盖）。可重复执行。
"""
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.environ.get("SEED_BASE", "http://localhost:8001/api/v1")
HERE = Path(__file__).resolve().parent
DB_PATH = Path(os.environ["DEMO_DB_DIR"]) / "drone_demo.db" if os.environ.get("DEMO_DB_DIR") \
    else HERE.parent / "drone_demo.db"

TOKEN = os.environ.get("SEED_TOKEN", "")


def req(method, path, body=None):
    url = BASE + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    r = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        print(f"  ! {method} {path} -> {e.code}: {detail[:300]}")
        return None


if not TOKEN:
    r = req("POST", "/auth/login", {"username": "admin", "password": "bonc"})
    if not r or not r.get("token"):
        sys.exit("自动登录失败，请手动提供 SEED_TOKEN")
    TOKEN = r["token"]
    print("[auth] 以 admin 登录成功")


# ── 1. 本地 SQLite 演示库（表结构与 mil_demo.db 完全一致） ──
DDL = """
CREATE TABLE IF NOT EXISTS target (
    target_id TEXT PRIMARY KEY, name TEXT NOT NULL, target_type TEXT,
    threat_level TEXT DEFAULT 'unknown', last_known_location TEXT DEFAULT '',
    speed_knots REAL DEFAULT 0, heading_deg REAL DEFAULT 0, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS sensor (
    sensor_id TEXT PRIMARY KEY, name TEXT NOT NULL, sensor_type TEXT,
    coverage_radius_km REAL DEFAULT 0, is_active INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS behavior_event (
    event_id TEXT PRIMARY KEY, target_id TEXT NOT NULL, event_type TEXT,
    description TEXT, confidence REAL DEFAULT 0.5, observed_at TEXT
);
CREATE TABLE IF NOT EXISTS assessment (
    assessment_id TEXT PRIMARY KEY, target_id TEXT NOT NULL, threat_assessment TEXT,
    ooda_phase TEXT, recommended_action TEXT, assessed_by TEXT DEFAULT '研判席', assessed_at TEXT
);
CREATE TABLE IF NOT EXISTS command_decision (
    decision_id TEXT PRIMARY KEY, target_id TEXT NOT NULL, assessment_id TEXT,
    confirmed_threat TEXT NOT NULL, selected_action_id TEXT, selected_action_name TEXT,
    order_text TEXT DEFAULT '', decided_by TEXT DEFAULT '指挥员', decided_at TEXT NOT NULL
);
"""

ROWS = {
    "target": [
        ("T-11", "黑蜂-03", "多旋翼", "hostile", "核心禁区上空 K2", 54, 210, "2026-10-13 11:05:00"),
        ("T-12", "灰影-11", "固定翼", "unknown", "管制区边界 W5", 78, 145, "2026-10-13 11:20:00"),
        ("T-13", "信鸽-A7", "无人直升机", "friendly", "巡逻航线 L1", 60, 90, "2026-10-13 10:50:00"),
        ("T-14", "夜枭-21", "固定翼", "critical", "体育中心上空 N8", 95, 300, "2026-10-13 11:32:00"),
    ],
    "sensor": [
        ("S-11", "低空补盲雷达", "雷达", 15, 1),
        ("S-12", "无线电频谱侦测车", "射频侦测", 8, 1),
        ("S-13", "光电跟踪球", "光电", 5, 1),
        ("S-14", "便携式干扰枪", "反制", 2, 1),
    ],
    "behavior_event": [
        ("EVT-D101", "T-11", "闯入核心禁区", "低空闯入核心禁区上空，未申报飞行计划，射频信号显示图传链路活跃", 0.93, "2026-10-13 11:02:00"),
        ("EVT-D102", "T-11", "悬停拍摄", "在要害设施上空悬停，光电确认挂载云台相机并持续对准拍摄", 0.90, "2026-10-13 11:06:00"),
        ("EVT-D103", "T-12", "边缘徘徊", "沿管制区边界来回徘徊，高度约 120 米，期间曾短暂越界", 0.72, "2026-10-13 11:18:00"),
        ("EVT-D104", "T-13", "例行巡逻", "执行既有空中巡逻航线，应答机信号正常", 0.96, "2026-10-13 10:50:00"),
        ("EVT-D105", "T-14", "未申报夜航", "夜间未申报飞行，关闭灯光与应答机，呈静默突防剖面", 0.89, "2026-10-13 11:30:00"),
        ("EVT-D106", "T-14", "抵近要害", "抵近体育中心上空约 80 米悬停，光电发现疑似投掷物挂载", 0.91, "2026-10-13 11:33:00"),
    ],
    "assessment": [
        ("ASM-D101", "T-11", "hostile", "orient", "警告驱离", "研判席", "2026-10-13 11:10:00"),
        ("ASM-D104", "T-14", "critical", "orient", "立即反制", "研判席", "2026-10-13 11:36:00"),
    ],
}


def build_demo_db():
    fresh = not DB_PATH.exists()
    con = sqlite3.connect(DB_PATH)
    con.executescript(DDL)
    if not fresh:
        have = {
            r[0]
            for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if not {"target", "sensor", "behavior_event", "assessment"} <= have:
            con.close()
            sys.exit(f"库结构异常: {DB_PATH}")
        con.close()
        print(f"[db] 已存在，跳过: {DB_PATH}")
        return
    for table, rows in ROWS.items():
        ph = ",".join("?" * len(rows[0]))
        con.executemany(f"INSERT INTO {table} VALUES ({ph})", rows)
        print(f"[db] {table}: {len(rows)} 行")
    con.commit()
    con.close()
    print(f"[db] 演示库就绪: {DB_PATH}")


# ── 2. 连接 + 资产 ───────────────────────────────────────
TABLES = {
    "DroneTarget": "target",
    "DetectSensor": "sensor",
    "FlightEvent": "behavior_event",
    "ThreatAssessment": "assessment",
}
ID_COLS = {
    "target": "target_id",
    "sensor": "sensor_id",
    "behavior_event": "event_id",
    "assessment": "assessment_id",
}


def enum(values, labels):
    return {"enumValues": values, "enumLabels": labels}


def seed_connection():
    # The connection name is Chinese, so searching for the English scenario key
    # does not return an existing connection. List connections and match the
    # stable name explicitly to keep repeated deployments idempotent.
    existing = req("GET", "/connections") or []
    for c in existing:
        if c.get("name") == "反制演示库":
            print("[conn] 已存在，复用:", c["id"])
            return c["id"]
    c = req("POST", "/connections", {
        "name": "反制演示库", "category": "database", "type": "sqlite",
        "host": "", "port": 0, "database": str(DB_PATH),
        "description": "无人机反制演示库（target/sensor/behavior_event/assessment）",
    })
    if not c:
        sys.exit("连接创建失败，终止")
    t = req("POST", f"/connections/{c['id']}/test")
    print("[conn] 创建:", c["id"], "连通性:", t)
    return c["id"]


def seed_assets(conn_id):
    assets = {}
    existing = req("GET", f"/assets?connection_id={conn_id}") or []
    have = {a["name"]: a["id"] for a in existing}
    for table in set(TABLES.values()):
        if table in have:
            assets[table] = have[table]
            continue
        a = req("POST", "/assets", {
            "name": table, "kind": "table", "connection_id": conn_id,
            "locator": {"table": table}, "domain": "military",
            "tags": ["drone"], "description": f"无人机反制演示表 {table}",
        })
        if a:
            assets[table] = a["id"]
    print("[assets]", len(assets), "张表已登记")
    return assets


# ── 3. 对象类 + 映射 + 关系 ──────────────────────────────
ENTITIES = [
    {
        "name": "DroneTarget", "name_cn": "无人机目标", "tier": 1, "domain": "military",
        "description": "低慢小无人机目标，按威胁等级动态列管并组织反制",
        "config_json": {"primary_key": "target_id"},
        "attributes": [
            {"name": "target_id", "type": "string", "required": True, "description": "无人机编号"},
            {"name": "name", "type": "string", "required": True, "description": "目标代号"},
            {"name": "target_type", "type": "string", "description": "机型类别",
             "constraints_json": enum(["多旋翼", "固定翼", "无人直升机", "巡飞弹"],
                                      ["多旋翼", "固定翼", "无人直升机", "巡飞弹"])},
            {"name": "threat_level", "type": "string", "description": "威胁等级",
             "constraints_json": enum(["hostile", "critical", "unknown", "friendly"],
                                      ["敌对", "严重威胁", "不明", "友好"])},
            {"name": "last_known_location", "type": "string", "description": "最后已知位置"},
            {"name": "speed_knots", "type": "number", "description": "巡航速度(km/h)"},
            {"name": "heading_deg", "type": "number", "description": "航向(度)"},
            {"name": "updated_at", "type": "date", "description": "情报更新时间"},
        ],
    },
    {
        "name": "DetectSensor", "name_cn": "侦测装备", "tier": 2, "domain": "military",
        "description": "低空防御体系内的侦测与反制装备（雷达/射频/光电/干扰）",
        "config_json": {"primary_key": "sensor_id"},
        "attributes": [
            {"name": "sensor_id", "type": "string", "required": True, "description": "装备编号"},
            {"name": "name", "type": "string", "required": True, "description": "装备名称"},
            {"name": "sensor_type", "type": "string", "description": "装备体制",
             "constraints_json": enum(["雷达", "射频侦测", "光电", "反制"],
                                      ["雷达", "射频侦测", "光电", "反制"])},
            {"name": "coverage_radius_km", "type": "number", "description": "覆盖半径(km)"},
            {"name": "is_active", "type": "boolean", "description": "是否在役"},
        ],
    },
    {
        "name": "FlightEvent", "name_cn": "飞行事件", "tier": 2, "domain": "military",
        "description": "侦测装备捕获的单次飞行行为事件，带置信度",
        "config_json": {"primary_key": "event_id"},
        "attributes": [
            {"name": "event_id", "type": "string", "required": True, "description": "事件编号"},
            {"name": "target_id", "type": "string", "required": True, "description": "所属无人机"},
            {"name": "event_type", "type": "string", "description": "行为类型"},
            {"name": "description", "type": "string", "description": "事件描述"},
            {"name": "confidence", "type": "number", "description": "0-1 置信度"},
            {"name": "observed_at", "type": "date", "required": True, "description": "观测时刻"},
        ],
    },
    {
        "name": "ThreatAssessment", "name_cn": "威胁研判", "tier": 3, "domain": "military",
        "description": "对无人机目标的威胁研判结论，驱动反制处置决策",
        "config_json": {"primary_key": "assessment_id"},
        "attributes": [
            {"name": "assessment_id", "type": "string", "required": True, "description": "研判编号"},
            {"name": "target_id", "type": "string", "required": True, "description": "被研判无人机"},
            {"name": "threat_assessment", "type": "string", "description": "威胁判定",
             "constraints_json": enum(["hostile", "critical", "unknown", "friendly"],
                                      ["敌对", "严重威胁", "不明", "友好"])},
            {"name": "ooda_phase", "type": "string", "description": "OODA 阶段",
             "constraints_json": enum(["observe", "orient", "decide", "act"],
                                      ["观察", "判断", "决策", "行动"])},
            {"name": "recommended_action", "type": "string", "description": "建议处置"},
            {"name": "assessed_by", "type": "string", "description": "研判席位"},
            {"name": "assessed_at", "type": "date", "required": True, "description": "研判时间"},
        ],
    },
]

RELATIONS = [
    ("DroneTarget", "FlightEvent", "drone_has_flight_event", "产生飞行事件", "has_many", "1:N",
     "无人机目标被侦测后产生的飞行行为事件"),
    ("FlightEvent", "ThreatAssessment", "event_grounds_assessment", "支撑研判", "has_many", "1:N",
     "飞行事件作为威胁研判的行为证据"),
    ("DroneTarget", "ThreatAssessment", "drone_has_assessment", "接受威胁研判", "has_many", "1:N",
     "无人机目标的威胁研判结论"),
    ("DetectSensor", "DroneTarget", "sensor_watches_drone", "监视目标", "has_many", "1:N",
     "侦测装备对空域内无人机目标的监视覆盖"),
]


def seed_entities():
    by_name = {}
    existing = req("GET", "/entities") or []
    for e in existing:
        if e["name"] in TABLES:
            by_name[e["name"]] = e["id"]
    for spec in ENTITIES:
        if spec["name"] in by_name:
            continue
        r = req("POST", "/entities", spec)
        if r:
            by_name[spec["name"]] = r["id"]
            print(f"[entity] {spec['name']}({spec['name_cn']}) 已建")
    return by_name


def seed_mappings(assets, entities_by_name):
    for name, eid in entities_by_name.items():
        table = TABLES.get(name)
        if not table or table not in assets:
            continue
        detail = req("GET", f"/entities/{eid}")
        attrs = detail.get("attributes", [])
        if not attrs:
            continue
        if all(a.get("source_field") for a in attrs):
            print(f"[mapping] {name} 已映射，跳过")
            continue
        fm = [{"attribute_id": a["id"], "source_column": a["name"]} for a in attrs]
        r = req("POST", "/mapping/apply", {
            "object_type_id": eid, "asset_id": assets[table],
            "field_mappings": fm, "id_column": ID_COLS[table], "role": "primary",
        })
        print(f"[mapping] {name} -> {table}:", (r or {}).get("action"))


def seed_relations(entities_by_name):
    rels = req("GET", "/relations") or []
    have = {(x["from_entity_id"], x["to_entity_id"], x["name"]) for x in rels}
    for f_name, t_name, rel, rel_cn, rel_type, card, desc in RELATIONS:
        f, t = entities_by_name.get(f_name), entities_by_name.get(t_name)
        if not f or not t:
            print(f"[relation] 跳过 {rel}：缺实体 {f_name}/{t_name}")
            continue
        if (f, t, rel) in have or (t, f, rel) in have:
            continue
        r = req("POST", "/relations", {
            "from_entity_id": f, "to_entity_id": t, "name": rel, "name_cn": rel_cn,
            "rel_type": rel_type, "cardinality": card, "description": desc,
        })
        if r:
            print(f"[relation] {f_name} -[{rel_cn} {card}]-> {t_name} 已建")


# ── 4. 行动 / 规则 / 智能体 ──────────────────────────────
def seed_logic(entities_by_name):
    actions = req("GET", "/actions") or []
    by_name = {a["name"]: a["id"] for a in actions}
    ta_id = entities_by_name.get("ThreatAssessment")

    if "反制指令通报" not in by_name and ta_id:
        r = req("POST", "/actions", {
            "name": "反制指令通报", "category": "domain",
            "entity_id": ta_id, "action_type": "notification",
            "type_config": {
                "channel": "system", "recipient": "反制值班席",
                "message_template": "无人机 $target_id 威胁等级 $threat_level（研判 $threat_assessment），建议下达反制指令",
            },
            "description": "威胁研判确认后向反制值班席通报，下达反制指令",
        })
        if r:
            by_name["反制指令通报"] = r["id"]
            print("[action] 反制指令通报 已建")
    if "空域预警发布" not in by_name and ta_id:
        r = req("POST", "/actions", {
            "name": "空域预警发布", "category": "domain",
            "entity_id": ta_id, "action_type": "notification",
            "type_config": {
                "channel": "system", "recipient": "空域管制组",
                "message_template": "对无人机 $target_id 发布空域预警，提示周边航空器注意规避",
            },
            "description": "发现未申报无人机时向空域管制组发布预警",
        })
        if r:
            by_name["空域预警发布"] = r["id"]
            print("[action] 空域预警发布 已建")

    rules = req("GET", "/rules") or []
    have_rules = {r["name"] for r in rules}
    specs = [
        {
            "entity_id": ta_id,
            "name": "严重威胁无人机自动反制",
            "description": "威胁判定为严重威胁的无人机，自动通报反制值班席下达反制指令",
            "conditions_json": [
                {"field": "ThreatAssessment.threat_assessment", "operator": "==",
                 "value": "critical", "display": "威胁研判.威胁判定"},
            ],
            "action_id": by_name.get("反制指令通报"),
            "action_desc": "命中后通报反制值班席下达反制指令",
            "priority": "high", "status": "active", "tags": ["drone", "反制"],
        },
        {
            "entity_id": ta_id,
            "name": "敌对无人机发布空域预警",
            "description": "威胁判定为敌对的无人机，向空域管制组发布预警",
            "conditions_json": [
                {"field": "ThreatAssessment.threat_assessment", "operator": "==",
                 "value": "hostile", "display": "威胁研判.威胁判定"},
            ],
            "action_id": by_name.get("空域预警发布"),
            "action_desc": "命中后向空域管制组发布预警",
            "priority": "high", "status": "active", "tags": ["drone", "反制"],
        },
        {
            "entity_id": ta_id,
            "name": "不明无人机加强侦测",
            "description": "威胁判定为不明的无人机，安排侦测装备加强盯防",
            "conditions_json": [
                {"field": "ThreatAssessment.threat_assessment", "operator": "==",
                 "value": "unknown", "display": "威胁研判.威胁判定"},
            ],
            "action_id": None,
            "action_desc": "命中后调度侦测装备加强盯防并持续积累行为证据",
            "priority": "medium", "status": "active", "tags": ["drone", "侦测"],
        },
    ]
    for spec in specs:
        if not spec["entity_id"] or spec["name"] in have_rules:
            continue
        r = req("POST", "/rules", spec)
        if r:
            print("[rule]", spec["name"], "已建")


def seed_agent(entities_by_name):
    agents = req("GET", "/agents") or []
    if any(a["name"] == "无人机反制研判智能体" for a in agents):
        print("[agent] 无人机反制研判智能体 已存在")
        return
    req("POST", "/agents", {
        "name": "无人机反制研判智能体",
        "description": "绑定无人机反制本体四对象，辅助完成观察-判断-决策-行动反制闭环",
        "tags": ["drone", "ooda"],
        "entity_ids": list(entities_by_name.values()),
        "system_prompt": (
            "你是低空无人机反制研判助手。基于 DroneTarget/DetectSensor/FlightEvent/ThreatAssessment "
            "本体回答态势问题，输出建议时注明 OODA 阶段；处置建议按 警告驱离/干扰迫降/捕获取证 区分。"
        ),
        "tools_config": {},
    })
    print("[agent] 无人机反制研判智能体 已建")


def main():
    build_demo_db()
    conn_id = seed_connection()
    assets = seed_assets(conn_id)
    entities_by_name = seed_entities()
    seed_mappings(assets, entities_by_name)
    seed_relations(entities_by_name)
    seed_logic(entities_by_name)
    seed_agent(entities_by_name)
    for name, eid in entities_by_name.items():
        r = req("PUT", f"/entities/{eid}", {"status": "published"})
        print(f"[publish] {name} ->", (r or {}).get("status"))
    cov = req("GET", "/mapping/coverage") or []
    ids = set(entities_by_name.values())
    print("[coverage]", [(c["object_type_id"][:8], f"{c['mapped']}/{c['total']}")
                         for c in cov if c["object_type_id"] in ids])
    print("无人机反制场景种子完成。")


if __name__ == "__main__":
    main()
