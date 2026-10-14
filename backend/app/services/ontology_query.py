"""Bound ontology queries with validated identifiers and parameterized values."""
import re
from fastapi import HTTPException
from app.models import OntologyEntity, EntityAttribute
from app.services.data_plane.entity_data_service import EntityDataService
from app.services.data_plane.execute_service import ExecuteRequest, ExecuteService


def query_instances(db, entity, filters=None, limit=50, offset=0, user_id=None):
    resolved = EntityDataService(db).resolve_entity_asset(entity.id)
    if not resolved:
        raise HTTPException(409, "本体对象尚未绑定有效的数据资产")
    asset, binding = resolved
    attrs = {a.id: a.name for a in db.query(EntityAttribute).filter_by(entity_id=entity.id)}
    mapping = {attrs[m["attribute_id"]]: m["source_column"] for m in (binding.field_mappings or []) if m.get("attribute_id") in attrs}
    clauses, params = [], {"limit": max(1, min(int(limit), 200)), "offset": max(0, min(int(offset), 100000))}
    for i, (name, value) in enumerate((filters or {}).items()):
        column = binding.id_column if name == "$id" else mapping.get(name)
        if not column or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", column):
            raise HTTPException(422, "过滤字段未绑定或不是合法字段")
        if isinstance(value, (list, dict)):
            raise HTTPException(422, "只支持单值等值过滤")
        clauses.append(f"{column} IS NULL" if value is None else f"{column} = :p{i}")
        if value is not None:
            params[f"p{i}"] = value
    sql = "SELECT * FROM <asset>" + (" WHERE " + " AND ".join(clauses) if clauses else "") + " LIMIT :limit OFFSET :offset"
    result = ExecuteService(db).execute(ExecuteRequest(asset_id=asset.id, sql=sql, params=params,
        purpose="ontology.api", user_id=user_id, bypass_cache=True))
    records = [dict(zip(result.columns, row)) for row in result.rows]
    if any(c not in result.columns for c in mapping.values()):
        raise HTTPException(409, "数据结构与本体映射不一致，请同步元数据")
    return {"instances": [{name: row[col] for name, col in mapping.items()} for row in records],
            "count": len(records), "limit": params["limit"], "offset": params["offset"], "asset_id": asset.id}


def get_entity(db, name):
    entity = db.query(OntologyEntity).filter_by(name=name, status="published").first()
    if not entity:
        raise HTTPException(404, "已发布本体对象不存在")
    return entity
