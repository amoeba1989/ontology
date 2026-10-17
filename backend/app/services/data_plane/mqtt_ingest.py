# -*- coding: utf-8 -*-
"""无人机 minsim MQTT 遥测接入：解析 → 降采样 → 幂等 → 三层落库（观测/状态/目标）。

契约来源：docs/mqtt使用说明.md + docs/mqtt消息.txt（minsim 仿真引擎 telemetry 报文）。

设计要点（对齐项目记忆中的 minsim 对接契约）：
- 报文块化：实体按 blocks 位掩码携带 transform/motion/flight/faction/rf_link/health/jammer，
  未置位块整块省略，解析时先判 blocks 位再取字段；
- 三层防膨胀：DroneObservation（append-only，降采样后落库）→ DroneState（按 target_key upsert
  最新帧）→ DroneTarget（稳定对象，scenario_id+entity_name 作 target_key）；
- 引擎实体 id 仅单次运行内唯一，禁止作持久主键；稳定标识 = scenario_id + entity_name；
- 幂等键 = client + scenario_id + tick + entity_id（obs_id），重复帧 INSERT OR IGNORE；
- 降采样：telemetry 50Hz 全量推送，观测层默认按 target_key 每 sample_interval 只落 1 帧；
- 截断：reported_count < entity_count 或 truncated=true 只记监控标记，不崩溃。

解析/落库为纯函数，不依赖 broker，可被实时消费者与离线回放自测（scripts/replay_mqtt_demo.py）共用。
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[3]
LANDING_DB = BACKEND_ROOT / "drone_mqtt_landing.db"

# blocks 位掩码（minsim 约定）
BLOCK_TRANSFORM = 1
BLOCK_MOTION = 2
BLOCK_FLIGHT = 4
BLOCK_FACTION = 8
BLOCK_RF_LINK = 16
BLOCK_HEALTH = 32
BLOCK_JAMMER = 64

DDL = """
CREATE TABLE IF NOT EXISTS drone_observation(
  obs_id TEXT PRIMARY KEY, client TEXT, scenario_id INTEGER, scenario_name TEXT,
  tick INTEGER, sim_time_s REAL, sim_entity_id INTEGER, entity_name TEXT, blocks INTEGER,
  latitude_deg REAL, longitude_deg REAL, altitude_m REAL, yaw_deg REAL, pitch_deg REAL, roll_deg REAL,
  speed_mps REAL, motion_mode INTEGER, airspeed_mps REAL, faction_side INTEGER,
  gnss_locked INTEGER, rc_linked INTEGER, telemetry_linked INTEGER, gnss_sir_db REAL, rc_sir_db REAL,
  hp REAL, max_hp REAL, destroyed INTEGER, observed_at TEXT
);
CREATE TABLE IF NOT EXISTS drone_state(
  target_key TEXT PRIMARY KEY, scenario_id INTEGER, entity_name TEXT,
  state_latitude_deg REAL, state_longitude_deg REAL, state_altitude_m REAL, state_speed_mps REAL,
  state_motion_mode INTEGER, state_faction_side INTEGER, state_last_tick INTEGER,
  gnss_locked INTEGER, rc_linked INTEGER, telemetry_linked INTEGER, gnss_sir_db REAL, rc_sir_db REAL,
  hp REAL, max_hp REAL, destroyed INTEGER, inside_zone TEXT, state_updated_at TEXT
);
CREATE TABLE IF NOT EXISTS drone_target(
  target_key TEXT PRIMARY KEY, scenario_id INTEGER, entity_name TEXT,
  tracking_status TEXT, first_seen_at TEXT, last_seen_at TEXT
);
CREATE TABLE IF NOT EXISTS mqtt_message_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT, kind TEXT, client TEXT,
  scenario_id INTEGER, tick INTEGER, received_at TEXT, payload TEXT
);
"""

# 观测层列顺序（与 DDL 一致），落库/回放共用
_OBS_COLS = [
    "obs_id", "client", "scenario_id", "scenario_name", "tick", "sim_time_s", "sim_entity_id",
    "entity_name", "blocks", "latitude_deg", "longitude_deg", "altitude_m", "yaw_deg", "pitch_deg",
    "roll_deg", "speed_mps", "motion_mode", "airspeed_mps", "faction_side", "gnss_locked",
    "rc_linked", "telemetry_linked", "gnss_sir_db", "rc_sir_db", "hp", "max_hp", "destroyed", "observed_at",
]
_STATE_COLS = [
    "target_key", "scenario_id", "entity_name", "state_latitude_deg", "state_longitude_deg",
    "state_altitude_m", "state_speed_mps", "state_motion_mode", "state_faction_side", "state_last_tick",
    "gnss_locked", "rc_linked", "telemetry_linked", "gnss_sir_db", "rc_sir_db", "hp", "max_hp",
    "destroyed", "inside_zone", "state_updated_at",
]
_TARGET_COLS = ["target_key", "scenario_id", "entity_name", "tracking_status", "first_seen_at", "last_seen_at"]


def _bit(blocks: int, mask: int) -> bool:
    try:
        return bool(int(blocks) & mask)
    except (TypeError, ValueError):
        return False


def _flag(v) -> int | None:
    return None if v is None else (1 if v else 0)


def _now_iso(now: datetime | None) -> str:
    return (now or datetime.now(timezone.utc)).isoformat()


def parse_telemetry(payload: dict, *, now: datetime | None = None) -> dict:
    """把一条 telemetry 报文拆成 观测/状态/目标 三层行（不做降采样，纯映射）。"""
    ts = _now_iso(now)
    scenario_id = payload.get("scenario_id")
    scenario_name = payload.get("scenario_name")
    client = payload.get("client") or ""
    tick = payload.get("tick")
    sim_time = payload.get("sim_time_s")

    observations: list[dict] = []
    states: list[dict] = []
    targets: list[dict] = []

    for ent in payload.get("entities", []) or []:
        name = ent.get("name")
        if name is None:
            continue
        eid = ent.get("id")
        blocks = ent.get("blocks", 0)
        target_key = f"{scenario_id}:{name}"
        obs_id = f"{client}:{scenario_id}:{tick}:{eid}"

        obs = {c: None for c in _OBS_COLS}
        obs.update(obs_id=obs_id, client=client, scenario_id=scenario_id, scenario_name=scenario_name,
                   tick=tick, sim_time_s=sim_time, sim_entity_id=eid, entity_name=name,
                   blocks=blocks, observed_at=ts)

        st = {c: None for c in _STATE_COLS}
        st.update(target_key=target_key, scenario_id=scenario_id, entity_name=name,
                  state_last_tick=tick, state_updated_at=ts)

        if _bit(blocks, BLOCK_TRANSFORM) and isinstance(ent.get("transform"), dict):
            tr = ent["transform"]
            obs.update(latitude_deg=tr.get("latitude_deg"), longitude_deg=tr.get("longitude_deg"),
                       altitude_m=tr.get("altitude_m"), yaw_deg=tr.get("yaw_deg"),
                       pitch_deg=tr.get("pitch_deg"), roll_deg=tr.get("roll_deg"))
            st.update(state_latitude_deg=tr.get("latitude_deg"), state_longitude_deg=tr.get("longitude_deg"),
                      state_altitude_m=tr.get("altitude_m"))
        if _bit(blocks, BLOCK_MOTION) and isinstance(ent.get("motion"), dict):
            mo = ent["motion"]
            obs.update(speed_mps=mo.get("speed_mps"), motion_mode=mo.get("mode"))
            st.update(state_speed_mps=mo.get("speed_mps"), state_motion_mode=mo.get("mode"))
        if _bit(blocks, BLOCK_FLIGHT) and isinstance(ent.get("flight"), dict):
            obs.update(airspeed_mps=ent["flight"].get("airspeed_mps"))
        if _bit(blocks, BLOCK_FACTION) and isinstance(ent.get("faction"), dict):
            side = ent["faction"].get("side")
            obs.update(faction_side=side)
            st.update(state_faction_side=side)
        if _bit(blocks, BLOCK_RF_LINK) and isinstance(ent.get("rf_link"), dict):
            rf = ent["rf_link"]
            gl, rl, tl = _flag(rf.get("gnss_locked")), _flag(rf.get("rc_linked")), _flag(rf.get("telemetry_linked"))
            obs.update(gnss_locked=gl, rc_linked=rl, telemetry_linked=tl,
                       gnss_sir_db=rf.get("gnss_sir_db"), rc_sir_db=rf.get("rc_sir_db"))
            st.update(gnss_locked=gl, rc_linked=rl, telemetry_linked=tl,
                      gnss_sir_db=rf.get("gnss_sir_db"), rc_sir_db=rf.get("rc_sir_db"))
        if _bit(blocks, BLOCK_HEALTH) and isinstance(ent.get("health"), dict):
            he = ent["health"]
            des = _flag(he.get("destroyed"))
            obs.update(hp=he.get("hp"), max_hp=he.get("max_hp"), destroyed=des)
            st.update(hp=he.get("hp"), max_hp=he.get("max_hp"), destroyed=des)

        observations.append(obs)
        states.append(st)
        targets.append({c: None for c in _TARGET_COLS} | dict(
            target_key=target_key, scenario_id=scenario_id, entity_name=name,
            tracking_status="tracking", first_seen_at=ts, last_seen_at=ts))

    truncated = payload.get("truncated", False) or (
        payload.get("reported_count") is not None
        and payload.get("entity_count") is not None
        and int(payload["reported_count"]) < int(payload["entity_count"]))
    return {"observations": observations, "states": states, "targets": targets,
            "truncated": bool(truncated)}


def ensure_schema(db_path: Path | str = LANDING_DB) -> None:
    con = sqlite3.connect(str(db_path))
    try:
        con.executescript(DDL)
        con.commit()
    finally:
        con.close()


# 降采样窗口：进程内记录每个 target_key 上次落观测的时刻（wall clock）
_last_obs_at: dict[str, float] = {}
_land_lock = threading.Lock()


def land_payload(payload: dict, *, db_path: Path | str = LANDING_DB,
                 sample_interval_s: float = 1.0, now: datetime | None = None) -> dict:
    """解析并落库一条 telemetry。观测层按 target_key 降采样 + obs_id 幂等；状态/目标层 upsert。"""
    parsed = parse_telemetry(payload, now=now)
    ensure_schema(db_path)
    con = sqlite3.connect(str(db_path))
    obs_written = 0
    try:
        stamp = time.monotonic()
        for obs in parsed["observations"]:
            tk = f"{obs['scenario_id']}:{obs['entity_name']}"
            if sample_interval_s > 0:
                with _land_lock:
                    last = _last_obs_at.get(tk, 0.0)
                    if stamp - last < sample_interval_s:
                        continue
                    _last_obs_at[tk] = stamp
            vals = [obs.get(c) for c in _OBS_COLS]
            con.execute(
                f"INSERT OR IGNORE INTO drone_observation({','.join(_OBS_COLS)}) "
                f"VALUES({','.join('?' * len(_OBS_COLS))})", vals)
            obs_written += con.execute("SELECT changes()").fetchone()[0]

        for st in parsed["states"]:
            vals = [st.get(c) for c in _STATE_COLS]
            upd = ",".join(f"{c}=excluded.{c}" for c in _STATE_COLS if c != "target_key")
            con.execute(
                f"INSERT INTO drone_state({','.join(_STATE_COLS)}) VALUES({','.join('?' * len(_STATE_COLS))}) "
                f"ON CONFLICT(target_key) DO UPDATE SET {upd}", vals)

        for t in parsed["targets"]:
            vals = [t.get(c) for c in _TARGET_COLS]
            con.execute(
                f"INSERT INTO drone_target({','.join(_TARGET_COLS)}) VALUES({','.join('?' * len(_TARGET_COLS))}) "
                f"ON CONFLICT(target_key) DO UPDATE SET last_seen_at=excluded.last_seen_at, "
                f"tracking_status=excluded.tracking_status", vals)

        con.execute(
            "INSERT INTO mqtt_message_log(topic,kind,client,scenario_id,tick,received_at,payload) "
            "VALUES(?,?,?,?,?,?,?)",
            ("telemetry", "telemetry", payload.get("client") or "", payload.get("scenario_id"),
             payload.get("tick"), _now_iso(now), json.dumps(payload, ensure_ascii=False)[:2000]))
        con.commit()
    finally:
        con.close()
    return {"observations": obs_written, "states": len(parsed["states"]),
            "targets": len(parsed["targets"]), "truncated": parsed["truncated"]}


def log_event(payload: dict, *, db_path: Path | str = LANDING_DB, now: datetime | None = None) -> None:
    """引擎业务事件（如 1001 会话超限）只记日志，不建业务对象。"""
    ensure_schema(db_path)
    con = sqlite3.connect(str(db_path))
    try:
        con.execute(
            "INSERT INTO mqtt_message_log(topic,kind,client,scenario_id,tick,received_at,payload) "
            "VALUES(?,?,?,?,?,?,?)",
            ("event", "event", payload.get("client") or "", payload.get("scenario_id"),
             payload.get("tick"), _now_iso(now), json.dumps(payload, ensure_ascii=False)[:2000]))
        con.commit()
    finally:
        con.close()


class MqttTelemetrySubscriber:
    """实时消费者：订阅 <prefix>/telemetry 与 <prefix>/event，回调落库。

    broker 不可达时不抛异常（后台重连），保证不拖垮应用启动。
    """

    def __init__(self, *, host: str, port: int = 1883, topic_prefix: str = "minsim",
                 client_id: str = "ontology-ingest", qos: int = 0,
                 username: str | None = None, password: str | None = None,
                 sample_interval_s: float = 1.0, db_path: Path | str = LANDING_DB) -> None:
        self.host = host
        self.port = int(port or 1883)
        self.topic_prefix = (topic_prefix or "minsim").strip("/")
        self.client_id = client_id or "ontology-ingest"
        self.qos = int(qos or 0)
        self.username = username
        self.password = password
        self.sample_interval_s = float(sample_interval_s)
        self.db_path = db_path
        self._client = None
        self.received = 0

    def _on_connect(self, client, _userdata, _flags, rc, *_args):
        if rc == 0:
            client.subscribe(f"{self.topic_prefix}/telemetry", qos=self.qos)
            client.subscribe(f"{self.topic_prefix}/event", qos=self.qos)

    def _on_message(self, _client, _userdata, msg):
        import json as _json
        try:
            payload = _json.loads(msg.payload.decode("utf-8"))
        except Exception:  # noqa: BLE001
            return
        topic = msg.topic or ""
        try:
            if topic.endswith("/telemetry"):
                land_payload(payload, db_path=self.db_path, sample_interval_s=self.sample_interval_s)
            else:
                log_event(payload, db_path=self.db_path)
            self.received += 1
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception("MQTT 落库失败（已忽略该帧）")

    def start(self) -> bool:
        """后台连接并订阅；成功返回 True。缺依赖或连不上返回 False（不抛）。"""
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            return False
        try:
            try:  # paho-mqtt 2.x 需要 callback_api_version
                client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=self.client_id)
            except (AttributeError, TypeError):  # 1.x
                client = mqtt.Client(client_id=self.client_id)
            if self.username:
                client.username_pw_set(self.username, self.password or None)
            client.on_connect = self._on_connect
            client.on_message = self._on_message
            client.reconnect_delay_set(min_delay=1, max_delay=30)
            client.connect_async(self.host, self.port, keepalive=30)
            client.loop_start()
            self._client = client
            return True
        except Exception:  # noqa: BLE001
            return False

    def stop(self) -> None:
        if self._client is not None:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:  # noqa: BLE001
                pass
            self._client = None
