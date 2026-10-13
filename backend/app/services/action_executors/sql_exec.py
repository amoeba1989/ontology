from .base import BaseActionExecutor, ExecutionResult


class SqlExecExecutor(BaseActionExecutor):
    def __init__(self, db=None, user_id=None):
        self.db = db
        self.user_id = user_id

    async def execute(self, type_config: dict, params: dict, dry_run: bool = False) -> ExecutionResult:
        from app.database import SessionLocal
        from app.models.connection import Connection
        from app.services.data_plane.execute_service import ExecuteService
        from app.services.data_plane.sql_introspect import introspect

        connection_id = type_config.get("connection_id")
        sql = type_config.get("sql", "")
        if "$" in sql:
            return ExecutionResult(success=False, message="SQL 行动请使用 :name 参数绑定，替换旧的 $name 字符串模板")
        db = self.db if self.db is not None else SessionLocal()
        try:
            conn = db.get(Connection, connection_id) if connection_id else None
            if not conn or not conn.enabled:
                raise ValueError("数据连接不存在或未启用")
            parsed = introspect(sql, dialect=conn.type)
            if not parsed.ok or parsed.is_ddl or not (parsed.is_select or parsed.is_dml):
                raise ValueError("SQL 安全校验失败：仅支持单条查询或数据写入语句")
            if parsed.is_dml and not conn.writable:
                raise ValueError("数据连接未开启写入权限")
            missing = [p for p in parsed.placeholders if p not in params]
            if missing:
                raise ValueError("缺少参数：" + ", ".join(missing))
            if dry_run:
                return ExecutionResult(success=True, message="[Dry Run] 参数与连接配置校验通过，尚未写入数据",
                                       output={"connection_id": connection_id, "parameters": parsed.placeholders})
            result = ExecuteService(db).execute_on_connection(
                connection_id=connection_id, sql=sql, params=params,
                purpose="action.sql_exec", write=parsed.is_dml, user_id=self.user_id,
            )
            return ExecutionResult(success=True, message="SQL 已执行，请刷新对象数据核对业务结果",
                                   output={"columns": result.columns, "rows": result.rows[:20]})
        except Exception as exc:
            return ExecutionResult(success=False, message=str(exc))
        finally:
            if self.db is None:
                db.close()

    @classmethod
    def get_config_schema(cls) -> dict:
        return {
            "connection_id": {"type": "string", "required": True, "description": "数据源连接 ID"},
            "sql": {"type": "string", "required": True, "description": "SQL 语句，使用 :param 参数绑定"},
        }

    @classmethod
    def get_label(cls) -> str:
        return "执行 SQL"

    @classmethod
    def get_description(cls) -> str:
        return "在指定数据源上执行 SQL 语句"
