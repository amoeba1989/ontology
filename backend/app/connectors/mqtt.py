"""MQTT 连接器（category=message_queue, type=mqtt）。

面向 minsim 仿真引擎遥测接入。基于 paho-mqtt：
- test()：同步连接 broker，收到 CONNACK rc==0 即视为连通；
- list_topics()：MQTT 无原生列举能力，返回按 topic_prefix 规范化的订阅主题
  （<prefix>/telemetry、<prefix>/event），供建资产时选择。

凭据：username/password 走 credential（plain://base64 json）。
"""
from __future__ import annotations

import threading


def _params(params: dict, credential: dict | None) -> dict:
    params = params or {}
    cred = credential or {}
    return {
        "host": params.get("host") or params.get("broker") or "",
        "port": int(params.get("port") or 1883),
        "topic_prefix": (params.get("topic_prefix") or "minsim").strip("/"),
        "client_id": params.get("client_id") or "ontology-probe",
        "qos": int(params.get("qos") or 0),
        "username": cred.get("username") or params.get("username") or "",
        "password": cred.get("password") or params.get("password") or "",
    }


class MQTTConnector:
    category = "message_queue"
    type = "mqtt"

    def test(self, *, params: dict, credential: dict | None) -> tuple[bool, str]:
        p = _params(params, credential)
        if not p["host"]:
            return False, "缺少 broker 地址（host）"
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            return False, "未安装 paho-mqtt（pip install paho-mqtt）"
        try:
            try:
                client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=p["client_id"])
            except (AttributeError, TypeError):
                client = mqtt.Client(client_id=p["client_id"])
            if p["username"]:
                client.username_pw_set(p["username"], p["password"] or None)
            result = {"rc": None}
            done = threading.Event()

            def _on_connect(_c, _u, _f, rc, *_a):
                result["rc"] = rc
                done.set()

            client.on_connect = _on_connect
            client.connect_async(p["host"], p["port"], keepalive=15)
            client.loop_start()
            try:
                got = done.wait(timeout=8)
            finally:
                client.loop_stop()
                try:
                    client.disconnect()
                except Exception:  # noqa: BLE001
                    pass
            if not got:
                return False, f"连接超时：broker {p['host']}:{p['port']} 无响应"
            if result["rc"] == 0:
                return True, f"连接成功（订阅 {p['topic_prefix']}/telemetry）"
            return False, f"CONNACK 返回码 {result['rc']}（鉴权或被拒）"
        except Exception as e:  # noqa: BLE001
            return False, f"连接失败: {e}"

    def list_topics(self, *, params: dict, credential: dict | None) -> list[str]:
        prefix = _params(params, credential)["topic_prefix"]
        return [f"{prefix}/telemetry", f"{prefix}/event"]
