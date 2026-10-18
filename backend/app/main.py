from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.version import APP_VERSION
from app.database import engine, SessionLocal
from app.db_compat import ensure_legacy_schema_compat
from app.models import *  # noqa: F401,F403 — 确保所有模型注册
from app.database import Base
from app.api.v1.entities import router as entities_router
from app.api.v1.auth import router as auth_router, seed_admin
from app.api.v1.delivery import router as delivery_router


def _seed_system_config(db):
    """初始化默认系统配置项（幂等：已存在则跳过）"""
    from app.models.system_config import SystemConfig
    defaults = [
        # basic
        ("basic", "system_name", "本体管理平台", "系统名称"),
        ("basic", "language", "zh-CN", "界面语言"),
        ("basic", "timezone", "Asia/Shanghai", "系统时区"),
        # auth
        ("auth", "password_min_length", "8", "密码最小长度"),
        ("auth", "password_complexity", "upper,lower,digit", "密码复杂度要求"),
        ("auth", "session_timeout", "30", "会话超时（分钟）"),
        ("auth", "sso_enabled", "false", "是否启用 SSO"),
        ("auth", "sso_provider", "oidc", "SSO 提供商（oidc/saml/ldap）"),
        ("auth", "client_id", "", "SSO Client ID"),
        ("auth", "client_secret", "", "SSO Client Secret"),
        # storage
        ("storage", "backend", "local", "存储后端（local/minio/oss）"),
        ("storage", "local_path", "./uploads", "本地文件存储路径"),
        ("storage", "max_upload_mb", "50", "最大上传大小（MB）"),
        ("storage", "allowed_types", ".owl,.rdf,.ttl,.csv,.xlsx,.json,.docx,.pdf", "允许的文件类型"),
        # ai（默认 DeepSeek，密钥在 .env 的 LLM_API_KEY 配置即可）
        ("ai", "model", "deepseek-flash", "LLM 模型"),
        ("ai", "api_key", "", "API Key"),
        ("ai", "api_secret", "", "API Secret（部分模型需要）"),
        ("ai", "base_url", "https://api.deepseek.com", "API Base URL"),
        ("ai", "temperature", "0.7", "Temperature（0.0-2.0）"),
        ("ai", "max_tokens", "4096", "最大 Token 数"),
        ("ai", "top_p", "1.0", "Top P 采样"),
        ("ai", "timeout_seconds", "60", "请求超时（秒）"),
        # notification
        ("notification", "smtp_host", "", "SMTP 服务器地址"),
        ("notification", "smtp_port", "465", "SMTP 端口"),
        ("notification", "smtp_encryption", "ssl", "加密方式（ssl/tls/none）"),
        ("notification", "smtp_username", "", "SMTP 用户名"),
        ("notification", "smtp_password", "", "SMTP 密码"),
        ("notification", "smtp_from_name", "本体管理平台", "发件人名称"),
        ("notification", "webhook_url", "", "Webhook URL"),
        ("notification", "webhook_secret", "", "Webhook 签名密钥"),
        # mqtt（无人机 minsim 遥测接入全局默认，连接级 params 可覆盖）
        ("mqtt", "topic_prefix", "minsim", "MQTT 主题前缀"),
        ("mqtt", "telemetry_topic", "minsim/telemetry", "遥测订阅主题"),
        ("mqtt", "event_topic", "minsim/event", "事件订阅主题"),
        ("mqtt", "default_qos", "0", "默认订阅 QoS"),
        ("mqtt", "sample_rate_hz", "1", "观测层落库降采样频率（Hz）"),
        ("mqtt", "idempotency_fields", "client,scenario_id,tick,entity_id", "观测幂等键字段"),
        ("mqtt", "stable_key_fields", "scenario_id,entity_name", "目标稳定标识字段"),
        ("mqtt", "out_of_order_window", "500", "乱序容忍窗口（tick 数）"),
        ("mqtt", "truncation_policy", "log-only", "截断处理策略（log-only=只记监控事件不崩溃）"),
    ]
    existing = {r.key for r in db.query(SystemConfig.key).all()}
    added = 0
    for group, key, value, desc in defaults:
        if key not in existing:
            db.add(SystemConfig(group=group, key=key, value=value, description=desc))
            added += 1

    # 初始化默认 AI 模型列表（JSON）
    if "ai.models" not in existing:
        import json
        default_models = json.dumps([
            {
                "id": "deepseek-flash",
                "name": "DeepSeek Flash",
                "provider": "DeepSeek",
                "model_id": "deepseek-flash",
                "api_key": "",
                "base_url": "https://api.deepseek.com",
                "temperature": 0.7,
                "max_tokens": 4096,
                "scenes": ["ontology", "agent", "data", "general"],
                "is_default": True,
            },
            {
                "id": "claude-sonnet",
                "name": "Claude Sonnet 4",
                "provider": "Anthropic",
                "model_id": "claude-sonnet-4-20250514",
                "api_key": "",
                "base_url": "https://api.anthropic.com",
                "temperature": 0.7,
                "max_tokens": 4096,
                "scenes": ["ontology", "general"],
                "is_default": False,
            },
            {
                "id": "claude-opus",
                "name": "Claude Opus 4",
                "provider": "Anthropic",
                "model_id": "claude-opus-4-20250514",
                "api_key": "",
                "base_url": "https://api.anthropic.com",
                "temperature": 0.5,
                "max_tokens": 8192,
                "scenes": ["ontology"],
                "is_default": False,
            },
            {
                "id": "gpt-4o",
                "name": "GPT-4o",
                "provider": "OpenAI",
                "model_id": "gpt-4o",
                "api_key": "",
                "base_url": "https://api.openai.com",
                "temperature": 0.7,
                "max_tokens": 4096,
                "scenes": ["agent", "data"],
                "is_default": False,
            },
            {
                "id": "deepseek-v3",
                "name": "DeepSeek V3",
                "provider": "DeepSeek",
                "model_id": "deepseek-chat",
                "api_key": "",
                "base_url": "https://api.deepseek.com",
                "temperature": 0.7,
                "max_tokens": 4096,
                "scenes": ["data", "general"],
                "is_default": False,
            },
        ], ensure_ascii=False)
        db.add(SystemConfig(group="ai", key="ai.models", value=default_models, description="AI 模型列表"))
        added += 1

    if added:
        db.commit()
        logger.info(f"系统配置初始化完成：新增 {added} 项")

from app.api.v1.rules import router as rules_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.copilot import router as copilot_router
from app.api.v1.relations import router as relations_router
# datasources_router 已废弃，数据接入统一走 data_plane/connections + assets
from app.api.v1.scene_data import routers as scene_data_routers
from app.api.v1.models import router as models_router
from app.api.v1.agents import router as agents_router, open_router as agents_open_router
from app.api.v1.skills import router as skills_router
from app.api.v1.skill_gen import router as skill_gen_router
from app.api.v1.registry import router as registry_router
from app.api.v1.resolution import router as resolution_router
from app.api.v1.governance import router as governance_router
from app.api.v1.prompt_templates import router as prompt_templates_router
from app.api.v1.ai_ontology import router as ai_ontology_router
from app.api.v1.builder import router as builder_router
from app.api.v1.business_documents import router as business_documents_router
from app.api.v1.ontology_api import router as ontology_api_router
from app.api.v1.osdk import router as osdk_router
from app.api.v1.ontology_publish import router as ontology_publish_router
from app.api.v1.traces import router as traces_router
from app.api.v1.evals import router as evals_router
from app.api.v1.actions import router as actions_router
from app.api.v1.functions import router as functions_router
from app.api.v1.monitor import router as monitor_router
from app.api.v1.studio import router as studio_router
from app.api.v1.pipelines import router as pipelines_router, start_worker as start_pipeline_worker
from app.api.v1.aip_scenes import router as aip_scenes_router
from app.api.v1.scene_registry import router as scene_registry_router
from app.api.v1.aip_executions import router as aip_executions_router
from app.api.v1.ai_builder_v2 import router as ai_builder_v2_router
from app.api.v1.aip_webhooks import router as aip_webhooks_router
from app.api.v1.doc_builder import router as doc_builder_router
from app.api.v1.ontology_mapping import router as ontology_mapping_router
from app.api.v1.system_config import router as system_config_router

# ── Data Plane（M1 新增 7 个 router）──
from app.api.v1.data_plane.connections import router as dp_connections_router
from app.api.v1.data_plane.assets import router as dp_assets_router
from app.api.v1.data_plane.execute import router as dp_execute_router
from app.api.v1.data_plane.probes import router as dp_probes_router
from app.api.v1.data_plane.lineage import router as dp_lineage_router
from app.api.v1.data_plane.events import router as dp_events_router
from app.api.v1.data_plane.audit import router as dp_audit_router
from app.api.v1.data_plane.object_bindings import router as dp_bindings_router
from app.api.v1.data_plane.quality import router as dp_quality_router
from app.api.v1.data_plane.mapping import router as dp_mapping_router
from app.api.v1.data_plane.compat import install as install_compat_middleware

logger = logging.getLogger(__name__)


@asynccontextmanager
def _seed_scene_registry(db):
    """场景中心默认导航项（幂等：已存在则跳过）。

    平台当前聚焦两个业务场景：无人机黑飞反制 + 电商。引用对象取各自 domain
    下的真实本体实体名（数据驱动，非硬编码）；无对应工作台页的场景 route 置空。
    """
    from app.models.scene_registry import SceneRegistry
    from app.models.entity import OntologyEntity
    if db.query(SceneRegistry).count() > 0:
        return

    def _names(domain: str) -> list[str]:
        rows = (
            db.query(OntologyEntity)
            .filter(OntologyEntity.domain == domain)
            .order_by(OntologyEntity.tier, OntologyEntity.name)
            .all()
        )
        return [e.name for e in rows]

    db.add(SceneRegistry(
        id="scene_drone",
        name="无人机黑飞反制",
        description="基于无人机目标/观测/状态/飞行授权/反制设备/保护区/风险评估/预警事件本体，组织低慢小黑飞目标的侦-判-反闭环处置",
        icon="🛡️", color="#f59e0b", route="/workspace/space", sort_order=0,
        assets={"object_classes": _names("drone"), "domains": ["drone"]},
    ))
    db.add(SceneRegistry(
        id="scene_shopping",
        name="电商场景",
        description="以顾客/商品/订单/购物车项/优惠券/支付流水/订单风险评估/风控预警事件八大本体构建电商语义网络，覆盖用户行为、商品与订单全生命周期治理",
        icon="🛒", color="#2E5BFF", route=None, sort_order=1,
        assets={"object_classes": _names("shopping"), "domains": ["shopping"]},
    ))
    db.commit()
    logger.info("场景注册表初始化完成")


async def lifespan(app: FastAPI):
    from app.services.db_migrations import upgrade_incremental_schema
    upgrade_incremental_schema(engine)
    # 启动：建表 + 初始化管理员
    Base.metadata.create_all(bind=engine)
    ensure_legacy_schema_compat(engine)

    # 迁移：schema_json → config_json 列重命名
    with engine.connect() as conn:
        from sqlalchemy import text, inspect as sa_inspect
        inspector = sa_inspect(engine)
        for tbl in ("ontology_entities", "ontology_version_entities"):
            if tbl in inspector.get_table_names():
                cols = {c["name"] for c in inspector.get_columns(tbl)}
                if "schema_json" in cols and "config_json" not in cols:
                    conn.execute(text(f"ALTER TABLE {tbl} RENAME COLUMN schema_json TO config_json"))
        conn.commit()

    # 迁移：scene_registry 表增加 assets_json 列（场景引用的本体资产）
    with engine.connect() as conn:
        from sqlalchemy import text, inspect as sa_inspect
        inspector = sa_inspect(engine)
        if "scene_registry" in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns("scene_registry")}
            if "assets_json" not in cols:
                conn.execute(text("ALTER TABLE scene_registry ADD COLUMN assets_json JSON"))
                conn.commit()
                logger.info("scene_registry.assets_json 列迁移完成")

    # SQLite 迁移：datasources 表增加 table_name / record_count 列
    with engine.connect() as conn:
        from sqlalchemy import text, inspect as sa_inspect
        inspector = sa_inspect(engine)
        if "datasources" in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns("datasources")}
            if "table_name" not in cols:
                conn.execute(text("ALTER TABLE datasources ADD COLUMN table_name VARCHAR(200) DEFAULT ''"))
            if "record_count" not in cols:
                conn.execute(text("ALTER TABLE datasources ADD COLUMN record_count INTEGER DEFAULT 0"))
                if "table_count" in cols:
                    conn.execute(text("UPDATE datasources SET record_count = table_count"))
            # 旧 table_count 列有 NOT NULL 约束，需保留默认值以兼容
            if "table_count" in cols:
                try:
                    conn.execute(text("UPDATE datasources SET table_count = 0 WHERE table_count IS NULL"))
                except Exception:
                    pass
            if "enabled" not in cols:
                conn.execute(text("ALTER TABLE datasources ADD COLUMN enabled TINYINT(1) DEFAULT 0"))
            if "source_category" not in cols:
                conn.execute(text("ALTER TABLE datasources ADD COLUMN source_category VARCHAR(20) DEFAULT 'database'"))
            if "file_path" not in cols:
                conn.execute(text("ALTER TABLE datasources ADD COLUMN file_path VARCHAR(500)"))
            if "file_type" not in cols:
                conn.execute(text("ALTER TABLE datasources ADD COLUMN file_type VARCHAR(20)"))
            if "api_url" not in cols:
                conn.execute(text("ALTER TABLE datasources ADD COLUMN api_url VARCHAR(500)"))
            if "api_method" not in cols:
                conn.execute(text("ALTER TABLE datasources ADD COLUMN api_method VARCHAR(10) DEFAULT 'GET'"))
            if "api_headers" not in cols:
                conn.execute(text("ALTER TABLE datasources ADD COLUMN api_headers JSON"))
            if "api_body" not in cols:
                conn.execute(text("ALTER TABLE datasources ADD COLUMN api_body TEXT"))
            if "mq_topic" not in cols:
                conn.execute(text("ALTER TABLE datasources ADD COLUMN mq_topic VARCHAR(200)"))
            if "mq_group" not in cols:
                conn.execute(text("ALTER TABLE datasources ADD COLUMN mq_group VARCHAR(200)"))
            if "poll_interval" not in cols:
                conn.execute(text("ALTER TABLE datasources ADD COLUMN poll_interval INTEGER DEFAULT 60"))
            if "parsed_content" not in cols:
                conn.execute(text("ALTER TABLE datasources ADD COLUMN parsed_content TEXT"))
            conn.commit()

        # business_rules 表增加结构化列
        if "business_rules" in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns("business_rules")}
            if "conditions_json" not in cols:
                conn.execute(text("ALTER TABLE business_rules ADD COLUMN conditions_json JSON"))
            if "rule_meta_json" not in cols:
                conn.execute(text("ALTER TABLE business_rules ADD COLUMN rule_meta_json JSON"))
            # 规则元数据扩展列（与 models/rule.py BusinessRule 对齐）
            if "description" not in cols:
                conn.execute(text("ALTER TABLE business_rules ADD COLUMN description TEXT"))
            if "tags" not in cols:
                conn.execute(text("ALTER TABLE business_rules ADD COLUMN tags JSON"))
            if "input_params" not in cols:
                conn.execute(text("ALTER TABLE business_rules ADD COLUMN input_params JSON"))
            if "output_schema" not in cols:
                conn.execute(text("ALTER TABLE business_rules ADD COLUMN output_schema JSON"))
            if "action_id" not in cols:
                conn.execute(text("ALTER TABLE business_rules ADD COLUMN action_id VARCHAR(36)"))
            conn.commit()

        # entity_actions 表增加结构化列（旧字段兼容 + 新字段迁移）
        if "entity_actions" in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns("entity_actions")}
            for col in ("parameters_json", "preconditions_json", "effects_json", "action_meta_json"):
                if col not in cols:
                    conn.execute(text(f"ALTER TABLE entity_actions ADD COLUMN {col} JSON"))
            # description 列（与 models/rule.py EntityAction 对齐）
            if "description" not in cols:
                conn.execute(text("ALTER TABLE entity_actions ADD COLUMN description TEXT"))
            # 新 schema 列（Task-11 重构）
            if "category" not in cols:
                conn.execute(text("ALTER TABLE entity_actions ADD COLUMN category VARCHAR(20) DEFAULT 'domain'"))
            if "action_type" not in cols:
                conn.execute(text("ALTER TABLE entity_actions ADD COLUMN action_type VARCHAR(30)"))
            if "type_config" not in cols:
                conn.execute(text("ALTER TABLE entity_actions ADD COLUMN type_config JSON"))
            if "output_schema" not in cols:
                conn.execute(text("ALTER TABLE entity_actions ADD COLUMN output_schema JSON"))
            if "updated_at" not in cols:
                conn.execute(text("ALTER TABLE entity_actions ADD COLUMN updated_at DATETIME"))
            # 旧 type 列已被 action_type 取代，设为 nullable 避免 INSERT 报错
            if "type" in cols:
                try:
                    conn.execute(text("ALTER TABLE entity_actions MODIFY COLUMN `type` VARCHAR(50) NULL"))
                    conn.commit()
                except Exception:
                    pass
            conn.commit()
            # 数据迁移：为旧行填充 category / action_type（幂等）
            result = conn.execute(
                text("SELECT COUNT(*) FROM entity_actions WHERE category IS NULL OR action_type IS NULL")
            )
            legacy_count = result.scalar()
            if legacy_count and legacy_count > 0:
                conn.execute(
                    text(
                        "UPDATE entity_actions"
                        " SET category = 'domain', action_type = 'custom_script'"
                        " WHERE category IS NULL OR action_type IS NULL"
                    )
                )
                conn.commit()
                logger.info(f"entity_actions 数据迁移完成：{legacy_count} 条旧记录已补全 category/action_type")

        # entity_attributes 表增加映射字段
        if "entity_attributes" in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns("entity_attributes")}
            if "source_table" not in cols:
                conn.execute(text("ALTER TABLE entity_attributes ADD COLUMN source_table VARCHAR(200)"))
            if "source_field" not in cols:
                conn.execute(text("ALTER TABLE entity_attributes ADD COLUMN source_field VARCHAR(200)"))
            if "data_status" not in cols:
                conn.execute(text("ALTER TABLE entity_attributes ADD COLUMN data_status VARCHAR(20) DEFAULT '未确认来源'"))
            conn.commit()

        # agents 表增加 nodes_json / edges_json 列
        if "agents" in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns("agents")}
            if "nodes_json" not in cols:
                conn.execute(text("ALTER TABLE agents ADD COLUMN nodes_json JSON"))
            if "edges_json" not in cols:
                conn.execute(text("ALTER TABLE agents ADD COLUMN edges_json JSON"))
            if "ontology_version_id" not in cols:
                conn.execute(text("ALTER TABLE agents ADD COLUMN ontology_version_id VARCHAR(36)"))
            if "ontology_stale" not in cols:
                conn.execute(text("ALTER TABLE agents ADD COLUMN ontology_stale TINYINT(1) NOT NULL DEFAULT 0"))
            if "ontology_stale_detail" not in cols:
                conn.execute(text("ALTER TABLE agents ADD COLUMN ontology_stale_detail JSON"))
            conn.commit()

        # aip_scenes 表增加 ontology_stale 相关列
        if "aip_scenes" in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns("aip_scenes")}
            if "ontology_version_id" not in cols:
                conn.execute(text("ALTER TABLE aip_scenes ADD COLUMN ontology_version_id VARCHAR(36)"))
            if "ontology_stale" not in cols:
                conn.execute(text("ALTER TABLE aip_scenes ADD COLUMN ontology_stale TINYINT(1) NOT NULL DEFAULT 0"))
            if "ontology_stale_detail" not in cols:
                conn.execute(text("ALTER TABLE aip_scenes ADD COLUMN ontology_stale_detail JSON"))
            conn.commit()

        # audit_log 表补充 details / status 列
        if "audit_log" in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns("audit_log")}
            if "details" not in cols:
                conn.execute(text("ALTER TABLE audit_log ADD COLUMN details TEXT"))
            if "status" not in cols:
                conn.execute(text("ALTER TABLE audit_log ADD COLUMN status VARCHAR(16) DEFAULT 'success'"))
            conn.commit()

        # skills 表增加技能平台扩展列
        if "skills" in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns("skills")}
            if "current_version" not in cols:
                conn.execute(text("ALTER TABLE skills ADD COLUMN current_version INTEGER DEFAULT 0"))
            if "input_schema" not in cols:
                conn.execute(text("ALTER TABLE skills ADD COLUMN input_schema JSON"))
            if "output_schema" not in cols:
                conn.execute(text("ALTER TABLE skills ADD COLUMN output_schema JSON"))
            if "prompt_template" not in cols:
                conn.execute(text("ALTER TABLE skills ADD COLUMN prompt_template TEXT"))
            if "tools" not in cols:
                conn.execute(text("ALTER TABLE skills ADD COLUMN tools JSON"))
            if "test_cases" not in cols:
                conn.execute(text("ALTER TABLE skills ADD COLUMN test_cases JSON"))
            if "asset_refs" not in cols:
                conn.execute(text("ALTER TABLE skills ADD COLUMN asset_refs JSON"))
            if "created_by" not in cols:
                conn.execute(text("ALTER TABLE skills ADD COLUMN created_by VARCHAR(100) DEFAULT ''"))
            if "reviewed_by" not in cols:
                conn.execute(text("ALTER TABLE skills ADD COLUMN reviewed_by VARCHAR(100) DEFAULT ''"))
            conn.commit()

        # ontology_entities 表增加 publish_config 列
        if "ontology_entities" in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns("ontology_entities")}
            if "publish_config" not in cols:
                conn.execute(text("ALTER TABLE ontology_entities ADD COLUMN publish_config JSON"))
            conn.commit()

        # users 表增加 email / is_active / last_login_at / updated_at 列
        if "users" in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns("users")}
            if "email" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(100)"))
            if "is_active" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN is_active TINYINT(1) DEFAULT 1"))
            if "last_login_at" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN last_login_at DATETIME"))
            if "updated_at" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN updated_at DATETIME"))
            conn.commit()

        # ontology_functions 表增加扩展列（与 models/function.py 对齐）
        if "ontology_functions" in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns("ontology_functions")}
            if "callable_name" not in cols:
                conn.execute(text("ALTER TABLE ontology_functions ADD COLUMN callable_name VARCHAR(100)"))
            if "tags" not in cols:
                conn.execute(text("ALTER TABLE ontology_functions ADD COLUMN tags JSON"))
            conn.commit()

        # pipelines 表增加真实 ETL 引擎列（与 models/pipeline.py 对齐）
        if "pipelines" in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns("pipelines")}
            if "engine" not in cols:
                conn.execute(text("ALTER TABLE pipelines ADD COLUMN engine VARCHAR(20) DEFAULT 'mock'"))
            if "config_json" not in cols:
                conn.execute(text("ALTER TABLE pipelines ADD COLUMN config_json JSON"))
            conn.commit()

        # pipeline_runs 表增加真实执行统计列
        if "pipeline_runs" in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns("pipeline_runs")}
            if "records_read" not in cols:
                conn.execute(text("ALTER TABLE pipeline_runs ADD COLUMN records_read INTEGER DEFAULT 0"))
            if "records_written" not in cols:
                conn.execute(text("ALTER TABLE pipeline_runs ADD COLUMN records_written INTEGER DEFAULT 0"))
            if "error" not in cols:
                conn.execute(text("ALTER TABLE pipeline_runs ADD COLUMN error TEXT"))
            if "log_tail" not in cols:
                conn.execute(text("ALTER TABLE pipeline_runs ADD COLUMN log_tail TEXT"))
            conn.commit()

        # ontology_entities 表增加业务场景列（与 models/entity.py 对齐）
        if "ontology_entities" in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns("ontology_entities")}
            if "domain" not in cols:
                conn.execute(text("ALTER TABLE ontology_entities ADD COLUMN domain VARCHAR(50)"))
            conn.commit()

        # entity_relations 表增加中文关系标识（三维关系标签读它，name 退回机读标识）
        if "entity_relations" in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns("entity_relations")}
            if "name_cn" not in cols:
                conn.execute(text("ALTER TABLE entity_relations ADD COLUMN name_cn VARCHAR(50)"))
            conn.commit()

    db = SessionLocal()
    try:
        seed_admin(db)
        _seed_system_config(db)
        _seed_scene_registry(db)
    finally:
        db.close()

    # Neo4j 初始化暂时跳过（需要修复 numpy/pandas 版本冲突后启用）
    # 基础功能（实体CRUD、规则、看板）不依赖 Neo4j
    logger.info("服务启动完成（Neo4j 待配置）")

    # 启动 AIP 调度器（schedule 触发器轮询）
    try:
        from app.services.aip.scheduler import start_scheduler
        start_scheduler()
    except Exception as e:
        logger.warning(f"AIP 调度器启动失败: {e}")

    # 注册 Data Plane 跨模块事件 handler
    try:
        from app.services.data_plane.event_handlers import register_event_handlers
        register_event_handlers()
        logger.info("Data Plane 事件 handler 已注册")
    except Exception as e:
        logger.warning(f"Data Plane 事件 handler 注册失败: {e}")

    start_pipeline_worker()

    # 启动无人机 MQTT 遥测消费者（仅当存在启用的 mqtt 连接；broker 不可达不影响启动）
    try:
        from app.services.data_plane.mqtt_bootstrap import start_mqtt_consumers
        n = start_mqtt_consumers()
        if n:
            logger.info("MQTT 遥测消费者已启动：%d 个连接", n)
    except Exception as e:
        logger.warning(f"MQTT 消费者启动失败: {e}")

    # 启动监控采集器
    try:
        from app.services.monitor.collector import start_collector
        await start_collector()
        logger.info("监控采集器已启动")
    except Exception as e:
        logger.warning(f"监控采集器启动失败: {e}")

    yield

    # 关闭 MQTT 消费者
    try:
        from app.services.data_plane.mqtt_bootstrap import stop_mqtt_consumers
        stop_mqtt_consumers()
    except Exception as e:
        logger.warning(f"MQTT 消费者关闭失败: {e}")


app = FastAPI(
    title="本体驱动智能策略平台 API",
    version=APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data Plane 兼容层：给 deprecated 路由添加 Deprecation / Sunset / Link 响应头
install_compat_middleware(app)

app.include_router(entities_router, prefix="/api/v1")
app.include_router(rules_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")
app.include_router(copilot_router, prefix="/api/v1")
app.include_router(relations_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
# app.include_router(datasources_router, prefix="/api/v1")  # 已废弃
for _scene_router in scene_data_routers:
    app.include_router(_scene_router, prefix="/api/v1")
app.include_router(models_router, prefix="/api/v1")
app.include_router(agents_router, prefix="/api/v1")
app.include_router(agents_open_router, prefix="/api/v1")
app.include_router(skills_router, prefix="/api/v1")
app.include_router(resolution_router, prefix="/api/v1")
app.include_router(governance_router, prefix="/api/v1")
app.include_router(prompt_templates_router, prefix="/api/v1")
app.include_router(ai_ontology_router, prefix="/api/v1")
app.include_router(ontology_api_router, prefix="/api/v1")
app.include_router(osdk_router, prefix="/api/v1")
app.include_router(ontology_publish_router, prefix="/api/v1")
app.include_router(traces_router, prefix="/api/v1")
app.include_router(evals_router, prefix="/api/v1")
app.include_router(actions_router, prefix="/api/v1")
app.include_router(functions_router, prefix="/api/v1")
app.include_router(monitor_router, prefix="/api/v1")
app.include_router(studio_router, prefix="/api/v1")
app.include_router(pipelines_router, prefix="/api/v1")
app.include_router(delivery_router, prefix="/api/v1")
from app.api.v1.customer_demo import router as customer_demo_router
app.include_router(customer_demo_router, prefix="/api/v1")
from app.api.v1.modeling_drafts import router as modeling_drafts_router
app.include_router(modeling_drafts_router, prefix="/api/v1")
from app.api.v1.owl_editor import router as owl_editor_router
app.include_router(owl_editor_router, prefix="/api/v1")
app.include_router(aip_scenes_router, prefix="/api/v1")
app.include_router(scene_registry_router, prefix="/api/v1")
app.include_router(aip_executions_router, prefix="/api/v1")
app.include_router(aip_webhooks_router, prefix="/api/v1")
app.include_router(builder_router, prefix="/api/v1")
app.include_router(business_documents_router, prefix="/api/v1")

# ── Data Plane router 挂载 ──
app.include_router(dp_connections_router, prefix="/api/v1")
app.include_router(dp_assets_router, prefix="/api/v1")
app.include_router(dp_execute_router, prefix="/api/v1")
app.include_router(dp_probes_router, prefix="/api/v1")
app.include_router(dp_lineage_router, prefix="/api/v1")
app.include_router(dp_events_router, prefix="/api/v1")
app.include_router(dp_audit_router, prefix="/api/v1")
app.include_router(dp_bindings_router, prefix="/api/v1")
app.include_router(dp_quality_router, prefix="/api/v1")
app.include_router(dp_mapping_router, prefix="/api/v1")
app.include_router(ai_builder_v2_router, prefix="/api/v1")
app.include_router(doc_builder_router, prefix="/api/v1")
app.include_router(ontology_mapping_router, prefix="/api/v1")
app.include_router(skill_gen_router, prefix="/api/v1")
app.include_router(registry_router, prefix="/api/v1")
app.include_router(system_config_router, prefix="/api/v1")


@app.get("/api/health")
def health():
    return {"status": "ok"}
