"""Request-local scene filtering for ontology read views; not an authorization boundary."""
from fastapi import HTTPException
from sqlalchemy import and_, event, or_
from sqlalchemy.orm import with_loader_criteria


SCOPED_PREFIXES = (
    "/entities", "/rules", "/actions", "/functions", "/studio", "/ontology", "/ontology-publish",
    "/dashboard/ontology-scene", "/dashboard/ontology-events",
    "/object-bindings", "/assets", "/lineage", "/mapping", "/agents",
)


def scene_entity_ids(db, scene_id):
    from app.models import OntologyEntity
    from app.models.scene_registry import SceneRegistry
    scene = db.get(SceneRegistry, scene_id)
    if not scene or scene.status != 'enabled':
        raise HTTPException(404, '所选本体场景不存在或已停用，请重新选择')
    assets = scene.assets or {}
    domains, classes = assets.get('domains') or [], assets.get('object_classes') or []
    if not all(isinstance(items, list) and all(isinstance(v, str) for v in items) for items in (domains, classes)):
        raise HTTPException(422, '场景的领域和对象类型配置必须是字符串列表')
    return [r[0] for r in db.query(OntologyEntity.id).filter(or_(
        OntologyEntity.domain.in_(domains), OntologyEntity.name.in_(classes), OntologyEntity.id.in_(classes))).all()]


def install_scene_scope(db, scene_id):
    from app.models import OntologyEntity, EntityAttribute, EntityRelation, BusinessRule, EntityAction
    from app.models.function import OntologyFunction
    from app.models.scene_registry import SceneRegistry
    from app.models.object_binding import ObjectBinding
    from app.models.asset import Asset
    from app.models.agent import Agent
    from app.models.trace import AgentTrace
    from app.models.lineage_edge import LineageEdge
    from app.models.audit import AuditLog
    from app.models.version import OntologyVersion, OntologyVersionEntity, OntologyVersionAttribute, OntologyVersionRelation

    scene = db.get(SceneRegistry, scene_id)
    if not scene or scene.status != "enabled":
        raise HTTPException(404, "所选本体场景不存在或已停用，请重新选择")
    assets = scene.assets or {}
    domains = assets.get("domains") or []
    ids = scene_entity_ids(db, scene_id)
    rule_ids = [r[0] for r in db.query(BusinessRule.id).filter(BusinessRule.entity_id.in_(ids)).all()]
    action_ids = [r[0] for r in db.query(EntityAction.id).filter(EntityAction.entity_id.in_(ids)).all()]
    bound_assets = [r[0] for r in db.query(ObjectBinding.asset_id).filter(ObjectBinding.object_type_id.in_(ids)).all()]
    asset_ids = [r[0] for r in db.query(Asset.id).filter(or_(Asset.domain.in_(domains), Asset.id.in_(bound_assets))).all()]
    explicit_agents = assets.get("agent_ids") or []
    agent_ids = [aid for aid, entity_ids in db.query(Agent.id, Agent.entity_ids).all()
                 if aid in explicit_agents or set(entity_ids or []) & set(ids)]
    snapshots = db.query(OntologyVersionEntity.id, OntologyVersionEntity.version_id).filter(OntologyVersionEntity.source_entity_id.in_(ids)).all()
    snapshot_ids = [row[0] for row in snapshots]
    version_ids = [row[1] for row in snapshots]
    allowed = {"asset": asset_ids, "object_type": ids, "rule": rule_ids, "action": action_ids}
    def edge_side(kind, identifier):
        return or_(*(and_(kind == name, identifier.in_(values)) for name, values in allowed.items()))
    filters = [
        (OntologyEntity, OntologyEntity.id.in_(ids)),
        (EntityAttribute, EntityAttribute.entity_id.in_(ids)),
        (EntityRelation, and_(EntityRelation.from_entity_id.in_(ids), EntityRelation.to_entity_id.in_(ids))),
        (BusinessRule, BusinessRule.entity_id.in_(ids)),
        (EntityAction, EntityAction.entity_id.in_(ids)),
        (OntologyFunction, OntologyFunction.entity_id.in_(ids)),
        (ObjectBinding, ObjectBinding.object_type_id.in_(ids)),
        (Asset, Asset.id.in_(asset_ids)),
        (Agent, Agent.id.in_(agent_ids)),
        (AgentTrace, AgentTrace.agent_id.in_(agent_ids)),
        (AuditLog, AuditLog.target_id.in_([*ids, *rule_ids, *action_ids, *asset_ids, *agent_ids])),
        (OntologyVersion, or_(OntologyVersion.scene_id == scene_id, OntologyVersion.id.in_(version_ids))),
        (OntologyVersionEntity, OntologyVersionEntity.id.in_(snapshot_ids)),
        (OntologyVersionAttribute, OntologyVersionAttribute.version_entity_id.in_(snapshot_ids)),
        (OntologyVersionRelation, and_(OntologyVersionRelation.from_version_entity_id.in_(snapshot_ids),
                                      OntologyVersionRelation.to_version_entity_id.in_(snapshot_ids))),
        (LineageEdge, and_(edge_side(LineageEdge.source_kind, LineageEdge.source_id),
                          edge_side(LineageEdge.target_kind, LineageEdge.target_id))),
    ]
    options = [with_loader_criteria(model, condition, include_aliases=True) for model, condition in filters]
    def apply_scope(state):
        if state.is_select and not state.is_relationship_load and not state.is_column_load:
            state.statement = state.statement.options(*options)
    event.listen(db, "do_orm_execute", apply_scope)
    return apply_scope
