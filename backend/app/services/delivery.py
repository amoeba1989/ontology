"""Validate the six-step chain and query real data through the shared data plane."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json

from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.connection import Connection
from app.models.entity import OntologyEntity
from app.models.object_binding import ObjectBinding
from app.models.pipeline import Pipeline, PipelineRun
from app.models.version import OntologyVersion
from app.models.rule import EntityAction


def action_fingerprint(action):
    return hashlib.sha256(json.dumps({"type": action.action_type, "config": action.type_config,
                                    "parameters": action.parameters_json, "entity_id": action.entity_id},
                                   sort_keys=True).encode()).hexdigest()


STEPS = ["需求分析", "数据源表", "数据处理", "子图建模", "本体库", "本体应用"]


def asset_contract(asset):
    return {"connection_id": asset.connection_id, "kind": asset.kind,
            "locator": asset.locator, "schema": asset.schema_snapshot,
            "sensitivity_tags": asset.sensitivity_tags}


def contract_fingerprint(snapshot: dict) -> str:
    """Hash contract content with deterministic ordering for unordered relations."""
    contract = {key: deepcopy(snapshot.get(key)) for key in
                ("config", "objects", "actions", "relations", "pipelines", "version_id")}
    contract["relations"] = sorted(contract.get("relations") or [], key=lambda relation: (
        relation.get("from_id") or "", relation.get("name") or "",
        relation.get("to_id") or "", relation.get("cardinality") or ""))
    return hashlib.sha256(json.dumps(contract, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def inspect_chain(db: Session, config: dict):
    issues = [[] for _ in STEPS]
    for key, label in [("goal", "业务目标"), ("audience", "使用者"),
                       ("questions", "核心问题"), ("acceptance", "验收条件")]:
        if not config.get(key, "").strip():
            issues[0].append(f"请填写{label}")
    sources = [db.get(Asset, i) for i in config.get("asset_ids", [])]
    outputs = [db.get(Asset, i) for i in config.get("output_asset_ids", [])]
    if not sources:
        issues[1].append("请选择至少一个源数据资产")
    for asset in sources + outputs:
        if not asset:
            issues[1].append("所选资产已删除，请重新选择")
            continue
        conn = db.get(Connection, asset.connection_id) if asset.connection_id else None
        if asset.status != "active" or not asset.schema_snapshot or not conn or not conn.enabled:
            issues[1].append(f"{asset.name}：需要有效连接、启用状态和已采集的字段结构")
        if asset.kind not in ("table", "sql_view"):
            issues[1].append(f"{asset.name}：V1 对象应用需要结构化资产")
    pipelines = [db.get(Pipeline, i) for i in config.get("pipeline_ids", [])]
    if config.get("processing_mode") == "direct":
        if not config.get("processing_note", "").strip():
            issues[2].append("直连模式需说明无需加工的原因")
        if pipelines or outputs:
            issues[2].append("直连模式请清空处理管道和输出资产")
        effective = [a for a in sources if a]
    else:
        effective = [a for a in outputs if a]
        if not pipelines or not outputs:
            issues[2].append("请选择真实处理管道及其输出资产")
        targets = set()
        for pipeline in pipelines:
            if not pipeline or pipeline.engine != "real":
                issues[2].append("模拟或已删除的管道不能用于业务交付")
                continue
            run = db.query(PipelineRun).filter_by(pipeline_id=pipeline.id).order_by(PipelineRun.started_at.desc()).first()
            if not run or run.status != "success" or pipeline.status != "success":
                issues[2].append(f"{pipeline.name}：最近一次真实运行尚未成功")
            cfg = pipeline.config_json or {}
            src = cfg.get("source", {})
            if src.get("connection_id") not in {a.connection_id for a in sources if a}:
                issues[2].append(f"{pipeline.name}：源连接不在项目数据源范围内")
            from app.services.data_plane.sql_introspect import introspect
            source_conn = db.get(Connection, src.get("connection_id")) if src.get("connection_id") else None
            parsed = introspect(src.get("query", ""), dialect=source_conn.type if source_conn else None)
            allowed = {(a.locator or {}).get("table", "").lower() for a in sources
                       if a and a.connection_id == src.get("connection_id")}
            if not parsed.ok or not parsed.is_select or not parsed.tables or any(t.split(".")[-1].lower() not in allowed for t in parsed.tables):
                issues[2].append(f"{pipeline.name}：源查询必须读取本项目选择的数据表")
            target = cfg.get("target", {})
            if target.get("write_mode", "append") == "append":
                issues[2].append(f"{pipeline.name}：重复交付请使用 upsert 或全量替换，避免追加重复记录")
            targets.add((target.get("connection_id"), target.get("table")))
        for asset in effective:
            if (asset.connection_id, (asset.locator or {}).get("table")) not in targets:
                issues[2].append(f"{asset.name}：不是所选管道的目标表")
    entities = [db.get(OntologyEntity, i) for i in config.get("entity_ids", [])]
    if not entities:
        issues[3].append("请选择业务对象")
    specs = []
    for entity in entities:
        if not entity:
            issues[3].append("所选对象已删除")
            continue
        bindings = db.query(ObjectBinding).filter_by(object_type_id=entity.id, role="primary", status="active").all()
        bindings = [b for b in bindings if b.asset_id in {a.id for a in effective}]
        if len(bindings) != 1:
            issues[3].append(f"{entity.name_cn}：需要唯一的主数据绑定，指向本项目处理结果")
            continue
        b = bindings[0]
        asset = db.get(Asset, b.asset_id)
        columns = {c["name"] for c in (asset.schema_snapshot or [])}
        attributes = {a.id: a for a in entity.attributes}
        mappings = b.field_mappings or []
        mapped = {m.get("attribute_id") for m in mappings}
        if not b.id_column or b.id_column not in columns or not mappings:
            issues[3].append(f"{entity.name_cn}：缺少有效主键或字段映射")
        if b.filter_expr or any(m.get("transform") for m in mappings):
            issues[3].append(f"{entity.name_cn}：请将过滤和转换放在数据处理步骤，V1 应用采用直接字段映射")
        if len(mapped) != len(mappings):
            issues[3].append(f"{entity.name_cn}：同一属性存在重复映射")
        if any(a.required and a.id not in mapped for a in entity.attributes):
            issues[3].append(f"{entity.name_cn}：必填属性尚未全部映射")
        if any(m.get("attribute_id") not in attributes or m.get("source_column") not in columns for m in mappings):
            issues[3].append(f"{entity.name_cn}：映射包含无效属性或来源字段")
        specs.append({"id": entity.id, "name": entity.name, "label": entity.name_cn,
                      "asset_id": asset.id, "asset_name": asset.name, "binding_id": b.id,
                      "id_column": b.id_column, "contract": asset_contract(asset),
                      "fields": [{"name": attributes[m["attribute_id"]].name,
                                  "source": m["source_column"], "type": attributes[m["attribute_id"]].type}
                                 for m in mappings if m.get("attribute_id") in attributes and m.get("source_column") in columns]})
    version = db.get(OntologyVersion, config.get("version_id")) if config.get("version_id") else None
    if not version or version.status != "published":
        issues[4].append("请选择已发布的本体版本")
    else:
        included = {e.source_entity_id for e in version.entities}
        if not set(config.get("entity_ids", [])) <= included:
            issues[4].append("所选版本未包含全部项目对象")
        for ve in version.entities:
            entity = next((e for e in entities if e and e.id == ve.source_entity_id), None)
            if entity and (entity.name != ve.name or
                           sorted((a.name, a.type, a.required) for a in entity.attributes) !=
                           sorted((a.name, a.type, a.required) for a in ve.attributes)):
                issues[4].append(f"{entity.name_cn}：当前结构与发布版本不一致，请重新发布")
    actions = []
    if config.get("expected_actions") and not config.get("action_ids"):
        issues[3].append("需求包含业务操作，请选择至少一个已配置行动")
    for action_id in config.get("action_ids", []):
        action = db.get(EntityAction, action_id)
        if not action or action.status != "active" or action.entity_id not in config.get("entity_ids", []):
            issues[3].append("行动需要已启用，并归属于本项目对象")
            continue
        if action.action_type not in ("api_call", "sql_exec"):
            issues[3].append(f"{action.name}：V1 支持真实 API 调用和参数化 SQL 行动；其他类型请先完成执行器")
        actions.append({"id": action.id, "name": action.name,
                        "parameters": action.parameters_json or [], "fingerprint": action_fingerprint(action)})
    version_entities = {e.id: e.source_entity_id for e in version.entities} if version else {}
    relations = [{"name": r.name, "from_id": version_entities.get(r.from_version_entity_id),
                  "to_id": version_entities.get(r.to_version_entity_id),
                  "cardinality": r.cardinality} for r in version.relations] if version else []
    relations = [r for r in relations if r['from_id'] in config.get('entity_ids', []) and r['to_id'] in config.get('entity_ids', [])]
    snapshot = {"config": deepcopy(config), "objects": specs, "actions": actions, "relations": relations,
                "pipelines": [{"id": p.id, "config": p.config_json} for p in pipelines if p],
                "version_id": config.get("version_id")}
    snapshot["fingerprint"] = contract_fingerprint(snapshot)
    return issues, snapshot


def query_object(db: Session, spec: dict, purpose: str, user_id: str):
    from app.services.data_plane.execute_service import ExecuteRequest, ExecuteService

    asset = db.get(Asset, spec["asset_id"])
    if not asset or asset.status != "active" or asset_contract(asset) != spec["contract"]:
        raise ValueError("数据资产结构或访问配置已改变，请重新校验并发布项目")
    # The shared executor enforces read-only SQL, masking and audit logging.
    sql = "SELECT * FROM <asset> LIMIT :lim"
    if asset.kind == "sql_view":
        view_sql = (asset.locator or {}).get("sql", "").strip().rstrip(";")
        if not view_sql:
            raise ValueError("视图缺少查询定义")
        sql = f"SELECT * FROM ({view_sql}) AS delivery_view LIMIT :lim"
    result = ExecuteService(db).execute(ExecuteRequest(
        asset_id=asset.id, sql=sql, params={"lim": 20},
        purpose=purpose, user_id=user_id, bypass_cache=True,
    ))
    index = {name: i for i, name in enumerate(result.columns)}
    wanted = {f["source"] for f in spec["fields"]} | {spec["id_column"]}
    if not wanted <= set(index):
        raise ValueError("实际数据字段与模型不一致，请同步资产结构")
    keys = [row[index[spec["id_column"]]] for row in result.rows]
    if any(k is None or k == "" for k in keys) or len({str(k) for k in keys}) != len(keys):
        raise ValueError("本次样本存在空主键或重复主键，请先处理数据")
    return {"columns": [f["name"] for f in spec["fields"]],
            "rows": [[row[index[f["source"]]] for f in spec["fields"]] for row in result.rows],
            "asset_name": asset.name, "sample_limit": 20, "queried_at": datetime.utcnow().isoformat() + "Z"}
