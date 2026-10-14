"""One persisted modeling workflow for AI proposals and manual forms."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import ValidationError
from app.database import get_db
from app.core.deps import require_user
from app.models import User, OntologyEntity, EntityAttribute, EntityRelation, BusinessRule
from app.models.modeling_draft import ModelingDraft, ModelingDraftEvent
from app.schemas.modeling_draft import DraftContent, DraftWrite, RevisionRequest
from app.services.modeling_draft import normalize_reviews, test_rule, generate_proposal, drone_template

router = APIRouter(prefix="/modeling-drafts", tags=["modeling-drafts"])


def editor(user: User = Depends(require_user)):
    if not user.is_active or user.role not in ("admin", "editor"):
        raise HTTPException(403, "建模需要编辑人员或管理员权限")
    return user


def owned(db, did, user):
    draft = db.get(ModelingDraft, did)
    if not draft or (draft.owner_id != user.id and user.role != "admin"):
        raise HTTPException(404, "草稿不存在或无权访问")
    return draft


def output(d):
    return {"id": d.id, "name": d.name, "scenario": d.scenario, "content": d.content,
            "proposal": d.proposal, "revision": d.revision, "materialized": d.materialized,
            "updated_at": d.updated_at.isoformat() + "Z"}


def change(db, draft, revision, fields, kind, details=None):
    if draft.materialized:
        raise HTTPException(409, "该草稿已入库，请在对象管理中编辑，或复制为新草稿")
    count = db.query(ModelingDraft).filter_by(id=draft.id, revision=revision).update(
        {**fields, "revision": revision + 1, "updated_at": datetime.utcnow()}, synchronize_session=False)
    if count != 1:
        db.rollback()
        raise HTTPException(409, "草稿已被其他窗口修改，请刷新后重试")
    db.add(ModelingDraftEvent(draft_id=draft.id, revision=revision + 1, kind=kind, details=details or {}))
    db.commit(); db.refresh(draft)
    return output(draft)


@router.get("")
def list_drafts(db: Session = Depends(get_db), user=Depends(editor)):
    query = db.query(ModelingDraft)
    if user.role != "admin":
        query = query.filter_by(owner_id=user.id)
    return [{"id": d.id, "name": d.name, "revision": d.revision, "imported": bool(d.materialized)}
            for d in query.order_by(ModelingDraft.updated_at.desc()).all()]


@router.get("/catalog")
def catalog(db: Session = Depends(get_db), user=Depends(editor)):
    return [{"id": e.id, "name": e.name, "label": e.name_cn, "description": e.description or "",
             "attributes": [{"name": a.name, "label": a.description or a.name, "type": a.type if a.type in ("string", "number", "boolean", "date", "json") else "string", "required": a.required,
                             "unit": (a.constraints_json or {}).get("unit", "")} for a in e.attributes]}
            for e in db.query(OntologyEntity).order_by(OntologyEntity.name).all()]


@router.get("/templates/drone")
def example(user=Depends(editor)):
    return drone_template()


@router.post("", status_code=201)
def create(body: DraftWrite, db: Session = Depends(get_db), user=Depends(editor)):
    draft = ModelingDraft(name=body.name, scenario=body.scenario, owner_id=user.id,
                          content=normalize_reviews(body.content))
    db.add(draft); db.flush()
    db.add(ModelingDraftEvent(draft_id=draft.id, revision=1, kind="created", details={"source": "form"}))
    db.commit(); db.refresh(draft)
    return output(draft)


@router.get("/{did}")
def get(did: str, db: Session = Depends(get_db), user=Depends(editor)):
    return output(owned(db, did, user))


@router.put("/{did}")
def save(did: str, body: DraftWrite, db: Session = Depends(get_db), user=Depends(editor)):
    draft = owned(db, did, user)
    content = normalize_reviews(body.content, draft.content)
    if body.scenario != draft.scenario:
        for r in content["rules"]:
            r["status"] = "pending"; r["confirmed"] = False
    return change(db, draft, body.revision, {"name": body.name, "scenario": body.scenario, "content": content, "proposal": None}, "saved")


@router.post("/{did}/generate")
def generate(did: str, body: RevisionRequest, db: Session = Depends(get_db), user=Depends(editor)):
    draft = owned(db, did, user)
    if draft.revision != body.revision or draft.materialized:
        raise HTTPException(409, "草稿状态已变化，请刷新")
    if not draft.scenario.strip():
        raise HTTPException(422, "请先填写业务场景")
    try:
        proposal = generate_proposal(db, draft)
    except ValidationError:
        raise HTTPException(422, "AI 输出的对象、引用或规则格式未通过校验，原草稿已保留，请调整场景后重试")
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except Exception as exc:
        raise HTTPException(502, "模型调用失败，请检查配置、额度与连通性（" + type(exc).__name__ + "）")
    return change(db, draft, body.revision, {"proposal": proposal}, "ai_proposed", {"model": proposal["model"]})


@router.post("/{did}/apply-proposal")
def apply_proposal(did: str, body: RevisionRequest, db: Session = Depends(get_db), user=Depends(editor)):
    draft = owned(db, did, user)
    if not draft.proposal or draft.proposal.get("base_revision") != body.revision - 1:
        raise HTTPException(409, "建议不存在或已过期，请重新生成")
    content = DraftContent.model_validate(draft.proposal["content"])
    return change(db, draft, body.revision, {"content": normalize_reviews(content), "proposal": None}, "ai_applied")


@router.post("/{did}/test-rules")
def test_rules(did: str, body: RevisionRequest, db: Session = Depends(get_db), user=Depends(editor)):
    draft = owned(db, did, user)
    if draft.revision != body.revision:
        raise HTTPException(409, "请刷新草稿后测试")
    results = [test_rule(r) for r in DraftContent.model_validate(draft.content).rules]
    db.add(ModelingDraftEvent(draft_id=did, revision=draft.revision, kind="rule_test", details={"results": results}))
    db.commit()
    return {"revision": draft.revision, "results": results, "scope": "用户配置的正反样例测试，非全量业务数据验证"}


class ReviewRequest(RevisionRequest):
    rule_ids: list[str]
    decision: str


@router.post("/{did}/review")
def review(did: str, body: ReviewRequest, db: Session = Depends(get_db), user=Depends(editor)):
    draft = owned(db, did, user)
    content = DraftContent.model_validate(draft.content)
    selected = [r for r in content.rules if r.id in body.rule_ids]
    if not selected or len(selected) != len(set(body.rule_ids)) or body.decision not in ("accepted", "rejected", "pending"):
        raise HTTPException(422, "请选择有效规则及审核操作")
    for rule in selected:
        if body.decision == "accepted" and (not rule.confirmed or not rule.basis.strip() or not rule.assumptions.strip() or not test_rule(rule)["passed"]):
            raise HTTPException(422, f"{rule.name}：需填写依据与适用前提、确认条件，并通过正反样例测试")
        rule.status = body.decision
    return change(db, draft, body.revision, {"content": content.model_dump(), "proposal": None}, "reviewed",
                  {"rule_ids": body.rule_ids, "decision": body.decision, "reviewer": user.id})


@router.get("/{did}/events")
def events(did: str, db: Session = Depends(get_db), user=Depends(editor)):
    owned(db, did, user)
    return [{"kind": e.kind, "revision": e.revision, "details": e.details, "created_at": e.created_at.isoformat() + "Z"}
            for e in db.query(ModelingDraftEvent).filter_by(draft_id=did).order_by(ModelingDraftEvent.created_at.desc()).limit(30)]


@router.post("/{did}/materialize")
def materialize(did: str, body: RevisionRequest, db: Session = Depends(get_db), user=Depends(editor)):
    draft = owned(db, did, user)
    if draft.materialized:
        return output(draft)
    if draft.revision != body.revision:
        raise HTTPException(409, "草稿已变化，请刷新")
    content = DraftContent.model_validate(draft.content)
    if not content.entities or any(not e.attributes for e in content.entities):
        raise HTTPException(422, "每个对象至少需要一个属性")
    if any(r.status == "pending" for r in content.rules):
        raise HTTPException(422, "请先接受或拒绝所有待审核规则")
    if any(r.status == "accepted" and (not r.confirmed or not test_rule(r)["passed"]) for r in content.rules):
        raise HTTPException(422, "已接受规则的样例或适用前提尚未验证")
    try:
        # Claim the revision before creating resources; a concurrent request cannot duplicate them.
        claimed = db.query(ModelingDraft).filter_by(id=did, revision=body.revision).update({"revision": body.revision + 1}, synchronize_session=False)
        if claimed != 1:
            raise HTTPException(409, "草稿已变化，请刷新")
        ids, rule_ids, relation_ids = {}, [], []
        for obj in content.entities:
            entity = db.get(OntologyEntity, obj.reuse_id) if obj.reuse_id else None
            if obj.reuse_id:
                if not entity or entity.name != obj.name:
                    raise HTTPException(422, "复用对象不存在或英文标识不一致")
                attrs = {a.name: a.type for a in entity.attributes}
                if any(attrs.get(a.name) != a.type for a in obj.attributes):
                    raise HTTPException(422, f"{obj.label} 的复用属性不一致，请在对象管理中修改原对象")
            else:
                if db.query(OntologyEntity).filter_by(name=obj.name).first():
                    raise HTTPException(409, f"对象 {obj.name} 已存在，请选择复用，避免重复创建")
                entity = OntologyEntity(name=obj.name, name_cn=obj.label, description=obj.description, tier=3,
                    status="active", created_by=user.id, config_json={"draft_id": did})
                db.add(entity); db.flush()
                for attr in obj.attributes:
                    db.add(EntityAttribute(entity_id=entity.id, name=attr.name, type=attr.type, required=attr.required,
                        description=attr.description or attr.label, constraints_json={"unit": attr.unit, "label": attr.label}))
            ids[obj.name] = entity.id
        db.flush()
        for rel in content.relations:
            existing = db.query(EntityRelation).filter_by(from_entity_id=ids[rel.source], to_entity_id=ids[rel.target], name=rel.name).first()
            if existing and existing.cardinality != rel.cardinality:
                raise HTTPException(409, "已有关系基数与草稿不一致，请先核对")
            if not existing:
                existing = EntityRelation(name=rel.name, name_cn=rel.label, from_entity_id=ids[rel.source], to_entity_id=ids[rel.target], cardinality=rel.cardinality, rel_type="association")
                db.add(existing); db.flush()
            relation_ids.append(existing.id)
        for rule in content.rules:
            if rule.status != "accepted":
                continue
            item = BusinessRule(entity_id=ids[rule.entity], name=rule.name, status="draft", condition_expr=str([c.model_dump() for c in rule.clauses]),
                action_desc="检查数据约束；绑定数据验证后再启用", description=rule.basis,
                rule_meta_json={"engine": "constraint_v1", "draft_id": did, "definition": rule.model_dump(), "reviewed_by": user.id})
            db.add(item); db.flush(); rule_ids.append(item.id)
        fields = {"entity_ids": list(ids.values()), "rule_ids": rule_ids, "relation_ids": relation_ids,
                  "at": datetime.utcnow().isoformat() + "Z", "next_step": "绑定数据、验证并发布"}
        db.query(ModelingDraft).filter_by(id=did).update({"materialized": fields, "proposal": None}, synchronize_session=False)
        db.add(ModelingDraftEvent(draft_id=did, revision=body.revision + 1, kind="materialized", details=fields))
        db.commit(); db.refresh(draft)
        return output(draft)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "对象被其他操作创建，请刷新并选择复用")
    except Exception:
        db.rollback()
        raise
