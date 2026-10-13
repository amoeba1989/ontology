"""Six-step delivery workspace using existing platform resources."""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session

from app.core.deps import require_user
from app.database import get_db
from app.models.delivery_project import DeliveryProject, DeliveryEvent
from app.models.asset import Asset
from app.models.entity import OntologyEntity
from app.models.pipeline import Pipeline, PipelineRun
from app.models.version import OntologyVersion
from app.models.user import User
from app.models.rule import EntityAction
from app.schemas.action import ActionExecuteRequest
from app.services.delivery import STEPS, inspect_chain, query_object, action_fingerprint

router = APIRouter(prefix="/delivery-projects", tags=["delivery-projects"])


class ProjectConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    goal: str = Field(default="", max_length=4000)
    audience: str = Field(default="", max_length=1000)
    questions: str = Field(default="", max_length=4000)
    expected_actions: str = Field(default="", max_length=4000)
    acceptance: str = Field(default="", max_length=4000)
    asset_ids: list[str] = Field(default_factory=list, max_length=100)
    processing_mode: Literal["pipeline", "direct"] = "pipeline"
    processing_note: str = Field(default="", max_length=2000)
    pipeline_ids: list[str] = Field(default_factory=list, max_length=50)
    output_asset_ids: list[str] = Field(default_factory=list, max_length=100)
    entity_ids: list[str] = Field(default_factory=list, max_length=100)
    action_ids: list[str] = Field(default_factory=list, max_length=100)
    version_id: str | None = None
    acceptance_evidence: str = Field(default="", max_length=4000)
    example_key: str | None = None


class ProjectWrite(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    config: ProjectConfig = Field(default_factory=ProjectConfig)
    revision: int = Field(default=1, ge=1)


def project_for(db, project_id, user):
    project = db.get(DeliveryProject, project_id)
    if not project or (project.owner_id != user.id and user.role != "admin"):
        raise HTTPException(404, "项目不存在或无权访问")
    return project


def event(db, project, kind, status, message, details=None):
    db.add(DeliveryEvent(project_id=project.id, revision=project.revision,
                         kind=kind, status=status, message=message, details=details or {}))


def checks(db, project):
    issues, snapshot = inspect_chain(db, project.config)
    test = db.query(DeliveryEvent).filter_by(project_id=project.id, revision=project.revision,
                                            kind="test").order_by(DeliveryEvent.created_at.desc()).first()
    if not test or test.status != "success" or test.details.get("fingerprint") != snapshot["fingerprint"]:
        issues[5].append("请保存配置后完成一次真实数据试运行；修改配置或关联资源后需要重试")
    if not project.config.get("acceptance_evidence", "").strip():
        issues[5].append("请填写业务验收结果，确认查询结果符合需求")
    return issues, snapshot


def serialize(db, p):
    issues, _ = checks(db, p)
    return {"id": p.id, "name": p.name, "config": p.config, "revision": p.revision,
            "release_number": p.release_number,
            "published_revision": (p.release or {}).get("revision"),
            "published_at": (p.release or {}).get("published_at"),
            "updated_at": p.updated_at.isoformat() + "Z",
            "steps": [{"name": name, "ready": not errors, "issues": errors}
                      for name, errors in zip(STEPS, issues)]}


@router.get("")
def list_projects(db: Session = Depends(get_db), user: User = Depends(require_user)):
    query = db.query(DeliveryProject)
    if user.role != "admin":
        query = query.filter_by(owner_id=user.id)
    return [serialize(db, p) for p in query.order_by(DeliveryProject.updated_at.desc()).all()]


@router.get("/resources")
def resources(db: Session = Depends(get_db), user: User = Depends(require_user)):
    return {
        "assets": [{"id": a.id, "name": a.name, "status": a.status, "kind": a.kind}
                   for a in db.query(Asset).order_by(Asset.name).all()],
        "pipelines": [{"id": p.id, "name": p.name, "status": p.status, "engine": p.engine}
                      for p in db.query(Pipeline).order_by(Pipeline.name).all()],
        "entities": [{"id": e.id, "name": e.name_cn, "status": e.status}
                     for e in db.query(OntologyEntity).order_by(OntologyEntity.name).all()],
        "actions": [{"id": a.id, "name": a.name, "entity_id": a.entity_id, "status": a.status}
                    for a in db.query(EntityAction).order_by(EntityAction.name).all()],
        "versions": [{"id": v.id, "name": f"v{v.version_number} · {v.name}", "status": v.status}
                     for v in db.query(OntologyVersion).order_by(OntologyVersion.version_number.desc()).all()],
    }


@router.post("", status_code=201)
def create_project(body: ProjectWrite, db: Session = Depends(get_db), user: User = Depends(require_user)):
    p = DeliveryProject(name=body.name, config=body.config.model_dump(), owner_id=user.id)
    db.add(p)
    db.flush()
    event(db, p, "save", "success", "创建业务项目")
    db.commit()
    return serialize(db, p)


@router.get("/examples/catalog")
def example_catalog(user: User = Depends(require_user)):
    from app.services.delivery_examples import EXAMPLES
    return [{"key": key, "name": value['name'], "goal": value['goal'], "boundary": value['boundary']}
            for key, value in EXAMPLES.items()]


@router.post("/examples/{key}", status_code=201)
def example_create(key: str, db: Session = Depends(get_db), user: User = Depends(require_user)):
    from app.services.delivery_examples import EXAMPLES, create_example
    if user.role != 'admin':
        raise HTTPException(403, "请由管理员创建验收数据")
    if key not in EXAMPLES:
        raise HTTPException(404, "未知样例")
    return serialize(db, create_example(db, user, key))


@router.post("/{project_id}/run-pipelines")
def project_run_pipelines(project_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)):
    from sqlalchemy.orm import sessionmaker
    from app.services.pipeline_engine import execute_run, validate_config
    p = project_for(db, project_id, user)
    ids = p.config.get('pipeline_ids', [])
    if not ids:
        raise HTTPException(400, "项目尚未关联处理管道")
    pipelines = [db.get(Pipeline, i) for i in ids]
    if any(not item or item.engine != 'real' for item in pipelines):
        raise HTTPException(400, "只能执行已关联的真实管道")
    try:
        for item in pipelines:
            validate_config(item.config_json)
            if item.status == 'running':
                raise ValueError(f'{item.name} 正在运行，请等待完成')
    except Exception as exc:
        raise HTTPException(400, str(exc))
    for item in pipelines:
        claimed = db.query(Pipeline).filter(Pipeline.id == item.id, Pipeline.status != 'running').update(
            {'status': 'running'}, synchronize_session=False)
        if claimed != 1:
            db.rollback()
            raise HTTPException(409, "管道已由其他任务启动，请稍后重试")
        run = PipelineRun(pipeline_id=item.id)
        db.add(run); db.commit(); db.refresh(run)
        execute_run(run.id, session_factory=sessionmaker(bind=db.get_bind()))
        db.expire_all()
        run = db.get(PipelineRun, run.id)
        if run.status != 'success':
            event(db, p, 'pipeline', 'error', f'{item.name}：{run.error}', {'run_id': run.id})
            db.commit()
            raise HTTPException(400, f'{item.name} 执行失败：{run.error}')
    event(db, p, 'pipeline', 'success', f'{len(pipelines)} 条真实管道执行完成')
    db.commit()
    return serialize(db, p)


@router.post("/{project_id}/publish-ontology")
def project_publish_ontology(project_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)):
    from app.api.v1.ontology_publish import create_version, add_entities, consistency_check
    from app.api.v1.ontology_publish import CreateVersionRequest, AddEntitiesRequest
    if user.role != 'admin':
        raise HTTPException(403, "本体发布需要管理员")
    p = project_for(db, project_id, user)
    issues, _ = inspect_chain(db, p.config)
    if any(issues[:4]):
        raise HTTPException(400, '；'.join(e for group in issues[:4] for e in group))
    version = create_version(CreateVersionRequest(name=f'{p.name} / r{p.revision}', description='项目范围本体发布，不切换平台全局活动版本'), db, user)
    add_entities(version['id'], AddEntitiesRequest(entity_ids=p.config['entity_ids']), db)
    checked = consistency_check(version['id'], db)
    if not checked['passed']:
        raise HTTPException(400, f"本体一致性校验失败：{checked['summary']}")
    v = db.get(OntologyVersion, version['id'])
    v.status = 'published'; v.published_at = datetime.utcnow(); v.approved_by = user.id
    p.config = {**p.config, 'version_id': v.id}
    p.revision += 1
    event(db, p, 'ontology', 'success', f'已发布项目本体版本 v{v.version_number}')
    db.commit()
    return serialize(db, p)


@router.get("/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)):
    return serialize(db, project_for(db, project_id, user))


@router.put("/{project_id}")
def save_project(project_id: str, body: ProjectWrite, db: Session = Depends(get_db), user: User = Depends(require_user)):
    p = project_for(db, project_id, user)
    if p.revision != body.revision:
        raise HTTPException(409, "项目已被其他窗口修改，请刷新后重试")
    config = body.config.model_dump()
    if p.name != body.name or p.config != config:
        count = db.query(DeliveryProject).filter_by(id=p.id, revision=body.revision).update(
            {"name": body.name, "config": config, "revision": body.revision + 1,
             "updated_at": datetime.utcnow()}, synchronize_session=False)
        if count != 1:
            db.rollback()
            raise HTTPException(409, "项目已被其他窗口修改，请刷新后重试")
        db.refresh(p)
        event(db, p, "save", "success", "保存项目草稿")
        db.commit()
    return serialize(db, p)


@router.get("/{project_id}/events")
def events(project_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)):
    project_for(db, project_id, user)
    return [{"id": e.id, "kind": e.kind, "status": e.status, "message": e.message,
             "revision": e.revision, "created_at": e.created_at.isoformat() + "Z", "details": e.details}
            for e in db.query(DeliveryEvent).filter_by(project_id=project_id)
            .order_by(DeliveryEvent.created_at.desc()).limit(50).all()]


@router.post("/{project_id}/test")
def test_project(project_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)):
    p = project_for(db, project_id, user)
    issues, snapshot = inspect_chain(db, p.config)
    if any(issues[:5]):
        raise HTTPException(400, "；".join(error for group in issues[:5] for error in group))
    samples = []
    try:
        for spec in snapshot["objects"]:
            samples.append({"entity": spec["label"], **query_object(db, spec, "delivery.test", user.id)})
        event(db, p, "test", "success", f"{len(samples)} 个对象真实取样成功（每个最多 20 行）",
              {"fingerprint": snapshot["fingerprint"], "rows": [len(s["rows"]) for s in samples]})
        db.commit()
    except Exception as exc:
        db.rollback()
        event(db, p, "test", "error", str(exc)[:500])
        db.commit()
        raise HTTPException(400, f"真实数据试运行失败：{str(exc)[:500]}")
    return {"samples": samples, "project": serialize(db, p)}


@router.post("/{project_id}/publish")
def publish_project(project_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)):
    p = project_for(db, project_id, user)
    issues, snapshot = checks(db, p)
    if any(issues):
        raise HTTPException(400, "；".join(error for group in issues for error in group))
    if (p.release or {}).get("fingerprint") == snapshot["fingerprint"] and (p.release or {}).get("revision") == p.revision:
        return serialize(db, p)
    p.release_number += 1
    p.release = {**snapshot, "revision": p.revision, "name": p.name,
                 "published_at": datetime.utcnow().isoformat() + "Z"}
    event(db, p, "publish", "success", f"发布对象查询应用 v{p.release_number}")
    db.commit()
    return serialize(db, p)


@router.get("/{project_id}/runtime")
def runtime(project_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)):
    p = project_for(db, project_id, user)
    if not p.release:
        raise HTTPException(409, "项目尚未发布")
    return {"name": p.release["name"], "release_number": p.release_number,
            "published_at": p.release["published_at"], "goal": p.release["config"]["goal"],
            "objects": [{"id": o["id"], "label": o["label"], "asset_name": o["asset_name"]}
                        for o in p.release["objects"]],
            "actions": [{"id": a["id"], "name": a["name"], "parameters": a["parameters"]}
                        for a in p.release.get("actions", [])], "relations": p.release.get("relations", [])}


@router.post("/{project_id}/runtime/actions/{action_id}")
async def runtime_action(project_id: str, action_id: str, body: ActionExecuteRequest,
                         db: Session = Depends(get_db), user: User = Depends(require_user)):
    from app.api.v1.actions import execute_action
    p = project_for(db, project_id, user)
    spec = next((a for a in (p.release or {}).get("actions", []) if a["id"] == action_id), None)
    action = db.get(EntityAction, action_id)
    if not spec or not action:
        raise HTTPException(404, "应用中没有这个行动")
    if action.status != "active" or action_fingerprint(action) != spec["fingerprint"]:
        raise HTTPException(409, "行动已停用或配置已改变，请重新校验发布")
    for param in spec["parameters"]:
        if param.get("required", True) and (param["name"] not in body.params or body.params[param["name"]] is None):
            raise HTTPException(400, f"缺少必填参数：{param['name']}")
    try:
        result = await execute_action(action_id, body, db, user)
        success = result.success if hasattr(result, "success") else result["success"]
        event(db, p, "action-test" if body.dry_run else "action", "success" if success else "error",
              f"{'试运行' if body.dry_run else '执行'}行动：{action.name}", {"release_number": p.release_number})
        db.commit()
        return result
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        event(db, p, "action", "error", str(exc)[:500])
        db.commit()
        raise HTTPException(400, str(exc)[:500])


@router.get("/{project_id}/runtime/{entity_id}")
def runtime_query(project_id: str, entity_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)):
    p = project_for(db, project_id, user)
    spec = next((o for o in (p.release or {}).get("objects", []) if o["id"] == entity_id), None)
    if not spec:
        raise HTTPException(404, "应用中没有这个对象")
    try:
        result = query_object(db, spec, "delivery.runtime", user.id)
        event(db, p, "query", "success", f"查询 {spec['label']}，返回 {len(result['rows'])} 行",
              {"release_number": p.release_number})
        db.commit()
        return result
    except Exception as exc:
        db.rollback()
        event(db, p, "query", "error", str(exc)[:500])
        db.commit()
        raise HTTPException(400, str(exc)[:500])
