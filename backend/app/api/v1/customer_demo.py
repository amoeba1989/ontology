from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.core.deps import require_user, require_admin
from app.models import DeliveryProject, Agent
from app.models.customer_demo import CustomerDemoPack
from app.services.customer_demo import demo_status
from app.services.skill_chat import chat_events

router = APIRouter(prefix="/customer-demo", tags=["customer-demo"], dependencies=[Depends(require_user)])


@router.get("/status")
def status(db: Session = Depends(get_db), user=Depends(require_user)):
    result = demo_status(db)
    result["packs"] = [p for p in result["packs"] if db.get(DeliveryProject, p["project_id"]) and
                        (user.role == "admin" or db.get(DeliveryProject, p["project_id"]).owner_id == user.id)]
    return result


@router.post("/{key}/check-ai", dependencies=[Depends(require_admin)])
def check_ai(key: str, db: Session = Depends(get_db), user=Depends(require_user)):
    from datetime import datetime
    pack = db.get(CustomerDemoPack, key)
    agent = db.get(Agent, pack.resources.get("agent_id")) if pack else None
    if not agent:
        raise HTTPException(404, "演示智能体尚未初始化")
    events = list(chat_events(db, agent, user, "请调用业务风险与规则结果技能，概括当前数据结果和需人工复核的事项。"))
    calls = [e for e in events if e.get("type") == "tool_result" and e.get("success")]
    check = {"passed": bool(calls and any(e.get("type") == "answer" for e in events)),
             "model": next((e.get("model") for e in events if e.get("type") == "model_status"), None),
             "run_ids": [e["run_id"] for e in calls], "tool_calls": len(calls),
             "checked_at": datetime.utcnow().isoformat() + "Z",
             "message": next((e.get("content") for e in events if e.get("type") == "error"), "模型 → 技能 → 数据库 → 回答已验证")}
    pack.report = {**pack.report, "ai": check}; db.commit()
    return {**check, "events": events}


@router.get("/{key}/template")
def template(key: str, db: Session = Depends(get_db), user=Depends(require_user)):
    from app.models import OntologyEntity, EntityRelation
    pack = db.get(CustomerDemoPack, key)
    project = db.get(DeliveryProject, pack.project_id) if pack else None
    if not project or (user.role != "admin" and project.owner_id != user.id):
        raise HTTPException(404, "业务模板不存在")
    entities = [db.get(OntologyEntity, eid) for eid in project.config["entity_ids"]]
    names = {e.id: e.name for e in entities}
    return {"domain": entities[0].domain, "scenario": {"name": project.name},
            "object_types": [{"name": e.name, "display_name": e.name_cn, "tier": e.tier,
                "primary_key": "id", "description": e.description,
                "properties": [{"name": a.name, "type": a.type, "required": a.required,
                    "source_table": a.source_table, "source_field": a.source_field} for a in e.attributes]} for e in entities],
            "link_types": [{"name": r.name, "display_name": r.name_cn, "source_type": names[r.from_entity_id],
                "target_type": names[r.to_entity_id], "cardinality": r.cardinality, "description": r.description}
                for r in db.query(EntityRelation).filter(EntityRelation.from_entity_id.in_(names), EntityRelation.to_entity_id.in_(names))]}
