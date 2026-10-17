# -*- coding: utf-8 -*-
"""无人机 MQTT 遥测消费者引导：为每个「启用的 mqtt 连接」拉起一个订阅者。

- 全局默认取 system_config group=mqtt（topic_prefix / sample_rate_hz / default_qos）；
- 连接级 params 覆盖（topic_prefix / client_id / qos / sample_interval_s）；
- broker 不可达时订阅者内部后台重连，不影响应用启动；
- 无启用的 mqtt 连接时什么都不做（零副作用）。
"""
from __future__ import annotations

import logging

from app.database import SessionLocal
from app.models.connection import Connection
from app.models.system_config import SystemConfig
from app.services.data_plane.mqtt_ingest import MqttTelemetrySubscriber

logger = logging.getLogger(__name__)

# connection_id → subscriber
_subscribers: dict[str, MqttTelemetrySubscriber] = {}


def _mqtt_defaults(db) -> dict:
    rows = db.query(SystemConfig).filter(SystemConfig.group == "mqtt").all()
    cfg = {r.key: r.value for r in rows}
    try:
        rate = float(cfg.get("sample_rate_hz") or 1)
    except (TypeError, ValueError):
        rate = 1.0
    return {
        "topic_prefix": cfg.get("topic_prefix") or "minsim",
        "qos": int(cfg.get("default_qos") or 0),
        "sample_interval_s": (1.0 / rate) if rate > 0 else 0.0,
    }


def _credential_of(conn: Connection) -> dict:
    """连接凭据明文解析（plain://<base64 json>）；失败返回空。"""
    import base64
    import json
    ref = conn.credential_ref or ""
    if ref.startswith("plain://"):
        try:
            return json.loads(base64.b64decode(ref[len("plain://"):]).decode("utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def start_mqtt_consumers() -> int:
    """为所有启用的 mqtt 连接启动订阅者，返回启动数量。"""
    db = SessionLocal()
    try:
        defaults = _mqtt_defaults(db)
        conns = db.query(Connection).filter(
            Connection.category == "message_queue",
            Connection.type == "mqtt",
            Connection.enabled.is_(True),
            Connection.status == "active",
        ).all()
        started = 0
        for conn in conns:
            if conn.id in _subscribers:
                continue
            params = conn.params or {}
            cred = _credential_of(conn)
            sub = MqttTelemetrySubscriber(
                host=conn.host or params.get("host") or params.get("broker") or "",
                port=conn.port or params.get("port") or 1883,
                topic_prefix=params.get("topic_prefix") or defaults["topic_prefix"],
                client_id=params.get("client_id") or f"ontology-ingest-{conn.id[:8]}",
                qos=int(params.get("qos", defaults["qos"])),
                username=cred.get("username") or params.get("username"),
                password=cred.get("password") or params.get("password"),
                sample_interval_s=float(params.get("sample_interval_s", defaults["sample_interval_s"])),
            )
            if not sub.host:
                logger.warning("MQTT 连接「%s」缺少 broker 地址，跳过", conn.name)
                continue
            if sub.start():
                _subscribers[conn.id] = sub
                started += 1
                logger.info("MQTT 遥测订阅已启动：%s → %s/%s", conn.name, sub.topic_prefix, "telemetry")
        return started
    finally:
        db.close()


def stop_mqtt_consumers() -> None:
    for cid, sub in list(_subscribers.items()):
        try:
            sub.stop()
        except Exception:  # noqa: BLE001
            pass
        _subscribers.pop(cid, None)
