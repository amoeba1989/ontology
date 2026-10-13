"""军事演示库种子脚本：重建 mil_demo.db（target/sensor/behavior_event/assessment/command_decision）"""
import os
import sqlite3
from pathlib import Path

DB = Path(os.environ.get("DEMO_DB_DIR", "")) / "mil_demo.db" if os.environ.get("DEMO_DB_DIR") \
    else Path(__file__).resolve().parent.parent / "mil_demo.db"

con = sqlite3.connect(DB)
con.executescript(
    """
    CREATE TABLE IF NOT EXISTS target (
        target_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        target_type TEXT,
        threat_level TEXT DEFAULT 'unknown',
        last_known_location TEXT DEFAULT '',
        speed_knots REAL DEFAULT 0,
        heading_deg REAL DEFAULT 0,
        updated_at TEXT
    );
    CREATE TABLE IF NOT EXISTS sensor (
        sensor_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        sensor_type TEXT,
        coverage_radius_km REAL DEFAULT 0,
        is_active INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS behavior_event (
        event_id TEXT PRIMARY KEY,
        target_id TEXT NOT NULL,
        event_type TEXT,
        description TEXT,
        confidence REAL DEFAULT 0.5,
        observed_at TEXT
    );
    CREATE TABLE IF NOT EXISTS assessment (
        assessment_id TEXT PRIMARY KEY,
        target_id TEXT NOT NULL,
        threat_assessment TEXT,
        ooda_phase TEXT,
        recommended_action TEXT,
        assessed_by TEXT DEFAULT '研判席',
        assessed_at TEXT
    );
    CREATE TABLE IF NOT EXISTS command_decision (
        decision_id TEXT PRIMARY KEY,
        target_id TEXT NOT NULL,
        assessment_id TEXT,
        confirmed_threat TEXT NOT NULL,
        selected_action_id TEXT,
        selected_action_name TEXT,
        order_text TEXT DEFAULT '',
        decided_by TEXT DEFAULT '指挥员',
        decided_at TEXT NOT NULL
    );
    """
)
con.execute("DELETE FROM behavior_event")
con.execute("DELETE FROM assessment")
con.execute("DELETE FROM command_decision")
con.execute("DELETE FROM target")
con.execute("DELETE FROM sensor")

con.executemany(
    "INSERT INTO target VALUES (?,?,?,?,?,?,?,?)",
    [
        ("T-01", "蓝海货运轮", "商船", "friendly", "近海航道 A3", 12.0, 95, "2026-10-13 09:30:00"),
        ("T-02", "不明快速小艇", "快艇", "unknown", "管控区边界 B7", 32.0, 210, "2026-10-13 10:15:00"),
        ("T-03", "低空侦察无人机", "无人机", "critical", "管控区上空 C2", 85.0, 180, "2026-10-13 10:42:00"),
        ("T-04", "海警巡逻艇", "执法船", "friendly", "近海航道 A1", 18.0, 45, "2026-10-13 10:05:00"),
    ],
)
con.executemany(
    "INSERT INTO sensor VALUES (?,?,?,?,?)",
    [
        ("S-01", "对海警戒雷达站", "雷达", 120, 1),
        ("S-02", "光电跟踪仪", "光电", 45, 1),
        ("S-03", "AIS 基站", "AIS", 80, 1),
        ("S-04", "电子侦察车", "ESM", 60, 0),
    ],
)
con.executemany(
    "INSERT INTO behavior_event VALUES (?,?,?,?,?,?)",
    [
        ("EVT-A101", "T-01", "常规航行", "按计划航线匀速航行，AIS 信号正常", 0.95, "2026-10-13 09:28:00"),
        ("EVT-A201", "T-02", "切入航道", "突然改变航向切入商船航道，未开启 AIS 应答", 0.82, "2026-10-13 10:02:00"),
        ("EVT-A202", "T-02", "高速机动", "航速由 18 节提升至 32 节，呈 S 形机动", 0.88, "2026-10-13 10:11:00"),
        ("EVT-A203", "T-02", "抵近侦察", "在管控区边界外 2 海里徘徊，航迹呈侦察搜索样式", 0.75, "2026-10-13 10:13:00"),
        ("EVT-A301", "T-03", "侵入管控区", "低空进入管控区上空，未申报飞行计划", 0.92, "2026-10-13 10:38:00"),
        ("EVT-A302", "T-03", "悬停侦察", "在我方要点上空悬停盘旋，光电信号显示挂载可疑吊舱", 0.9, "2026-10-13 10:40:00"),
        ("EVT-A401", "T-04", "例行巡逻", "沿既定巡逻线航行，通信应答正常", 0.97, "2026-10-13 10:03:00"),
    ],
)
con.executemany(
    "INSERT INTO assessment VALUES (?,?,?,?,?,?,?)",
    [
        ("ASM-B201", "T-02", "hostile", "orient", "警告驱离", "研判席", "2026-10-13 10:20:00"),
    ],
)
con.commit()
con.close()
print(f"seeded {DB}")
