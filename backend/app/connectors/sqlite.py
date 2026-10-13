from __future__ import annotations

import sqlite3
from typing import Any

from app.connectors import ConnectorRegistry


@ConnectorRegistry.register("sqlite")
class SQLiteConnector:
    """本地 SQLite 文件连接器（演示/开发/边缘部署场景）。

    约定：Connection.database 字段存放 SQLite 文件路径；host/port/username/password 忽略。
    占位符沿用平台统一的 :name 风格 —— sqlite3 原生支持命名参数，无需转换。
    """

    def connect(self, *, host: str, port: int, username: str,
                password: str, database: str) -> Any:
        if not database:
            raise ValueError("sqlite 连接需要 database 字段为文件路径")
        # check_same_thread=False：ConnectionService 的连接池会在多个线程间复用同一连接
        # （如真实 ETL 管道在后台线程执行），sqlite3 默认的同线程限制会在此报错。
        # 池的借还本身有锁；演示级并发下安全。
        conn = sqlite3.connect(database, timeout=5, check_same_thread=False)
        return conn

    def close(self, conn: Any) -> None:
        conn.close()

    def quote_identifier(self) -> str:
        return '"'

    def list_tables(self, conn: Any, database: str) -> list[str]:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        tables = [row[0] for row in cur.fetchall()]
        cur.close()
        return tables

    def list_databases(self, conn: Any) -> list[str]:
        return ["main"]

    def preview_table(self, conn: Any, table_name: str, limit: int = 20) -> dict:
        cur = conn.execute(f'SELECT * FROM "{table_name}" LIMIT {int(limit)}')
        columns = [desc[0] for desc in cur.description]
        rows = [list(row) for row in cur.fetchall()]
        cur.close()
        return {"table": table_name, "columns": columns, "rows": rows}

    def get_table_schema(self, conn: Any, table_name: str, database: str) -> list[dict]:
        cur = conn.execute(f'PRAGMA table_info("{table_name}")')
        columns = []
        for row in cur.fetchall():
            # row: (cid, name, type, notnull, dflt_value, pk)
            columns.append({
                "name": row[1],
                "type": (row[2] or "text").lower(),
                "nullable": not row[3],
                "comment": "",
                "is_pk": bool(row[5]),
            })
        cur.close()
        return columns

    def execute_sql(self, conn: Any, sql: str) -> dict:
        cur = conn.execute(sql)
        columns = [desc[0] for desc in cur.description] if cur.description else []
        rows = [list(row) for row in cur.fetchall()]
        cur.close()
        return {"columns": columns, "rows": rows, "rowCount": len(rows)}

    def execute_sql_with_params(self, conn: Any, sql: str, params: dict) -> dict:
        cur = conn.execute(sql, params)
        columns = [desc[0] for desc in cur.description] if cur.description else []
        rows = [list(row) for row in cur.fetchall()]
        cur.close()
        return {"columns": columns, "rows": rows, "rowCount": len(rows)}
