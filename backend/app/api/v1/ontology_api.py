"""
本体语义 API — 根据本体 Schema 动态生成查询端点
"""
from __future__ import annotations

import json
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import OntologyEntity, EntityRelation
from app.core.deps import require_user
from app.services.ontology_query import get_entity, query_instances

router = APIRouter(prefix="/ontology-api", tags=["ontology-api"], dependencies=[Depends(require_user)])


class EndpointParam(BaseModel):
    name: str
    type: str
    required: bool
    description: str


class EndpointInfo(BaseModel):
    method: str
    path: str
    shortPath: str
    description: str
    params: list[EndpointParam] = []


class EndpointGroup(BaseModel):
    entity: str
    entityCn: str
    endpoints: list[EndpointInfo]


class EndpointsResponse(BaseModel):
    groups: list[EndpointGroup]


@router.get("/endpoints", response_model=EndpointsResponse)
def list_endpoints(db: Session = Depends(get_db)):
    entities = db.query(OntologyEntity).filter(OntologyEntity.status == "published").all()
    groups = []
    for entity in entities:
        eps = [
            EndpointInfo(
                method="GET",
                path=f"/ontology-api/objects/{entity.name}",
                shortPath=f"/{entity.name}",
                description=f"查询 {entity.name_cn} 实例列表",
                params=[
                    EndpointParam(name="limit", type="integer", required=False, description="返回数量限制"),
                    EndpointParam(name="offset", type="integer", required=False, description="偏移量"),
                    EndpointParam(name="filter", type="string", required=False, description="过滤条件 JSON"),
                ],
            ),
            EndpointInfo(
                method="GET",
                path=f"/ontology-api/objects/{entity.name}/{{id}}",
                shortPath=f"/{entity.name}/{{id}}",
                description=f"获取单个 {entity.name_cn} 实例详情",
                params=[
                    EndpointParam(name="id", type="string", required=True, description="实例 ID"),
                ],
            ),
            EndpointInfo(
                method="GET",
                path=f"/ontology-api/objects/{entity.name}/{{id}}/relations",
                shortPath=f"/{entity.name}/{{id}}/relations",
                description=f"遍历 {entity.name_cn} 的关联实体",
                params=[
                    EndpointParam(name="id", type="string", required=True, description="实例 ID"),
                    EndpointParam(name="rel_type", type="string", required=False, description="关系名称过滤（有向一跳）"),
                ],
            ),
        ]
        groups.append(EndpointGroup(entity=entity.name, entityCn=entity.name_cn, endpoints=eps))
    return EndpointsResponse(groups=groups)


class OntologyQueryRequest(BaseModel):
    entity_name: str
    filters: dict | None = None
    relations: list[str] | None = None
    depth: int = 1
    limit: int = 50
    offset: int = 0


@router.post("/query")
def ontology_query(req: OntologyQueryRequest, db: Session = Depends(get_db)):
    entity = get_entity(db, req.entity_name)
    if not entity:
        from fastapi import HTTPException
        raise HTTPException(404, f"实体 {req.entity_name} 不存在")

    result = {
        "entity": {"name": entity.name, "name_cn": entity.name_cn, "tier": entity.tier},
        **query_instances(db, entity, req.filters, req.limit, req.offset),
        "relations": [],
    }

    if req.relations or req.depth > 0:
        rels = db.query(EntityRelation).filter(
            (EntityRelation.from_entity_id == entity.id) | (EntityRelation.to_entity_id == entity.id)
        ).all()
        result["relations"] = [
            {"name": r.name, "rel_type": r.rel_type, "from_entity_id": r.from_entity_id, "to_entity_id": r.to_entity_id, "cardinality": r.cardinality}
            for r in rels
        ]

    return result


class RuleExecuteRequest(BaseModel):
    rule_id: str
    entity_id: str
    context: dict | None = None


@router.post("/execute-rule")
def execute_rule(req: RuleExecuteRequest, db: Session = Depends(get_db)):
    from app.models.rule import BusinessRule
    rule = db.query(BusinessRule).filter(BusinessRule.id == req.rule_id).first()
    if not rule:
        from fastapi import HTTPException
        raise HTTPException(404, "规则不存在")
    if rule.entity_id != req.entity_id:
        raise HTTPException(422, "规则与本体对象不匹配")
    from app.services.rule_engine import RuleEvaluator
    evaluator = RuleEvaluator(db)
    output = evaluator.evaluate(rule, (req.context or {}).get("user_id", ""))
    db.commit()
    return {"rule": rule.name, "entity_id": req.entity_id, "result": "executed", "output": evaluator._result_to_dict(output)}


@router.get("/objects/{name}")
def objects(name: str, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0, le=100000),
            filter: str | None = None, db: Session = Depends(get_db), user=Depends(require_user)):
    try:
        filters = json.loads(filter) if filter else {}
        if not isinstance(filters, dict):
            raise ValueError()
    except ValueError:
        raise HTTPException(422, "filter 必须为 JSON 对象")
    return query_instances(db, get_entity(db, name), filters, limit, offset, user.id)


@router.get("/objects/{name}/{object_id}")
def object_detail(name: str, object_id: str, db: Session = Depends(get_db), user=Depends(require_user)):
    data = query_instances(db, get_entity(db, name), {"$id": object_id}, 1, user_id=user.id)
    if not data["instances"]:
        raise HTTPException(404, "实例不存在")
    return data["instances"][0]


@router.get("/objects/{name}/{object_id}/relations")
def related_objects(name: str, object_id: str, rel_type: str | None = None,
                    db: Session = Depends(get_db), user=Depends(require_user)):
    from app.services.data_plane.entity_data_service import EntityDataService
    from app.models import EntityAttribute
    entity = get_entity(db, name)
    row = object_detail(name, object_id, db, user)
    source_binding = EntityDataService(db).resolve_entity_asset(entity.id)[1]
    attrs = {a.id: a.name for a in db.query(EntityAttribute).filter_by(entity_id=entity.id)}
    source_names = {m["source_column"]: attrs[m["attribute_id"]] for m in source_binding.field_mappings if m.get("attribute_id") in attrs}
    results = []
    for rel in db.query(EntityRelation).filter_by(from_entity_id=entity.id):
        if rel_type and rel.name != rel_type:
            continue
        mapping = (entity.config_json or {}).get("relation_bindings", {}).get(rel.id)
        if not mapping:
            results.append({"name": rel.name, "label": rel.name_cn, "status": "mapping_required", "instances": []})
            continue
        target = db.get(OntologyEntity, rel.to_entity_id)
        if not target or target.status != "published":
            continue
        resolved = EntityDataService(db).resolve_entity_asset(target.id)
        if not resolved:
            raise HTTPException(409, "关系目标未绑定数据资产")
        target_attrs = {a.id: a.name for a in db.query(EntityAttribute).filter_by(entity_id=target.id)}
        target_names = {m["source_column"]: target_attrs[m["attribute_id"]] for m in resolved[1].field_mappings if m.get("attribute_id") in target_attrs}
        source_attr = source_names.get(mapping["source_column"])
        target_attr = target_names.get(mapping["target_column"])
        if not source_attr or not target_attr:
            raise HTTPException(409, "关系连接字段未绑定")
        value = row.get(source_attr)
        data = query_instances(db, target, {target_attr: value}, user_id=user.id) if value is not None else {"instances": [], "count": 0}
        results.append({"name": rel.name, "label": rel.name_cn, "target": target.name_cn,
                        "target_api_name": target.name, "status": "queried", **data})
    return {"source": row, "direction": "outgoing", "depth": 1, "relations": results}
