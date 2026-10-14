"""Skills CRUD API"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models.skill import Skill
from app.core.deps import require_user, require_admin
from app.models import User

router = APIRouter(prefix="/skills", tags=["skills"], dependencies=[Depends(require_user)])


class SkillCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    skill_type: Optional[str] = "custom"
    config_json: Optional[dict] = None
    code_ref: Optional[str] = ""


class SkillUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config_json: Optional[dict] = None
    code_ref: Optional[str] = None
    status: Optional[str] = None


def _skill_out(s: Skill) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "description": s.description,
        "skill_type": s.skill_type,
        "config_json": s.config_json or {},
        "code_ref": s.code_ref,
        "status": s.status,
        "current_version": s.current_version,
        "input_schema": s.input_schema,
        "output_schema": s.output_schema,
        "prompt_template": s.prompt_template or "",
        "tools": s.tools,
        "test_cases": s.test_cases,
        "asset_refs": s.asset_refs,
        "created_by": s.created_by or "",
        "reviewed_by": s.reviewed_by or "",
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


@router.get("")
def list_skills(status: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Skill)
    if status:
        q = q.filter(Skill.status == status)
    else:
        q = q.filter(Skill.status.in_(["active", "draft"]))
    return [_skill_out(s) for s in q.all()]


@router.post("", status_code=201, dependencies=[Depends(require_admin)])
def create_skill(body: SkillCreate, db: Session = Depends(get_db)):
    s = Skill(**body.model_dump())
    db.add(s)
    db.commit()
    db.refresh(s)
    return _skill_out(s)


@router.get("/{sid}")
def get_skill(sid: str, db: Session = Depends(get_db)):
    s = db.get(Skill, sid)
    if not s:
        raise HTTPException(404, "Skill not found")
    return _skill_out(s)


@router.put("/{sid}", dependencies=[Depends(require_admin)])
def update_skill(sid: str, body: SkillUpdate, db: Session = Depends(get_db)):
    s = db.get(Skill, sid)
    if not s:
        raise HTTPException(404, "Skill not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(s, k, v)
    db.commit()
    db.refresh(s)
    return _skill_out(s)


@router.delete("/{sid}", dependencies=[Depends(require_admin)])
def delete_skill(sid: str, db: Session = Depends(get_db)):
    s = db.get(Skill, sid)
    if not s:
        raise HTTPException(404, "Skill not found")
    db.delete(s)
    db.commit()
    return {"ok": True}


from app.services.skill_version_service import (
    list_versions, rollback_skill,
)


@router.get("/{sid}/versions")
def get_versions(sid: str, db: Session = Depends(get_db)):
    s = db.get(Skill, sid)
    if not s:
        raise HTTPException(404, "Skill not found")
    return list_versions(sid, db)


class RollbackRequest(BaseModel):
    target_version: int


@router.post("/{sid}/rollback", dependencies=[Depends(require_admin)])
def rollback(sid: str, body: RollbackRequest, db: Session = Depends(get_db)):
    s = db.get(Skill, sid)
    if not s:
        raise HTTPException(404, "Skill not found")
    try:
        rollback_skill(s, body.target_version, db)
        return _skill_out(s)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{sid}/deprecate", dependencies=[Depends(require_admin)])
def deprecate(sid: str, db: Session = Depends(get_db)):
    s = db.get(Skill, sid)
    if not s:
        raise HTTPException(404, "Skill not found")
    s.status = "deprecated"
    db.commit()
    return _skill_out(s)


class SkillExecute(BaseModel):
    params: dict = {}


@router.post("/{sid}/execute")
def execute(sid: str, body: SkillExecute, db: Session = Depends(get_db), user: User = Depends(require_user)):
    from app.services.business_skills import run_business_skill
    skill = db.get(Skill, sid)
    if not skill:
        raise HTTPException(404, "技能不存在")
    if skill.skill_type != "configured":
        raise HTTPException(409, "该技能尚未接入受控的业务执行器")
    return run_business_skill(db, skill, body.params, user)


@router.get("/{sid}/runs")
def runs(sid: str, db: Session = Depends(get_db), user: User = Depends(require_user)):
    from app.models.customer_demo import SkillRun
    from app.services.business_skills import check_access
    skill = db.get(Skill, sid)
    if not skill:
        raise HTTPException(404, "技能不存在")
    if skill.skill_type == "configured":
        check_access(db, skill, user)
    rows = db.query(SkillRun).filter_by(skill_id=sid).order_by(SkillRun.created_at.desc()).limit(20).all()
    return [{"id": r.id, "status": r.status, "source": r.source, "skill_version": r.skill_version,
             "params": r.params, "result": r.result, "duration_ms": r.duration_ms,
             "created_at": r.created_at.isoformat() + "Z"} for r in rows]


@router.get("/runtime/model-status")
def model_status(db: Session = Depends(get_db)):
    from app.services.llm_resolver import agent_model_status
    return agent_model_status(db)
