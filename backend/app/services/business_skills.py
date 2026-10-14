"""Read-only skills over published delivery contracts. No model-generated SQL."""
import time
from fastapi import HTTPException
from app.models import Skill, DeliveryProject, User
from app.models.customer_demo import SkillRun
from app.services.delivery import inspect_chain, query_object


def check_access(db, skill, user):
    project = db.get(DeliveryProject, (skill.config_json or {}).get("project_id"))
    if not user or not project or (user.role != "admin" and project.owner_id != user.id):
        raise HTTPException(403, "无权使用该项目技能")
    return project


def validate_params(schema, params):
    if not isinstance(params, dict):
        raise ValueError("技能参数必须是对象")
    props = (schema or {}).get("properties", {})
    if set(params) - set(props):
        raise ValueError("存在未定义的技能参数")
    for key in (schema or {}).get("required", []):
        if key not in params:
            raise ValueError(f"缺少参数：{key}")
    for key, value in params.items():
        spec = props[key]
        if spec.get("type") == "string" and not isinstance(value, str):
            raise ValueError(f"{key} 必须是字符串")
        if "enum" in spec and value not in spec["enum"]:
            raise ValueError(f"{key} 不在允许范围内")


def run_business_skill(db, skill: Skill, params: dict, user: User, source="manual"):
    project = check_access(db, skill, user)
    if skill.status != "active" or skill.current_version < 1:
        raise HTTPException(409, "技能尚未发布或已废弃")
    started = time.monotonic()
    try:
        validate_params(skill.input_schema, params)
        if not project.release:
            raise ValueError("请先发布业务应用")
        issues, snapshot = inspect_chain(db, project.release["config"])
        if any(issues[:5]) or snapshot["fingerprint"] != project.release["fingerprint"]:
            raise ValueError("发布后的数据契约已改变，请重新校验并发布")
        specs = project.release["objects"]
        mode = (skill.config_json or {}).get("operation")
        if mode in ("query", "findings"):
            entity_id = (skill.config_json or {}).get("entity_id")
            spec = next((s for s in specs if s["id"] == entity_id), None) if mode == "findings" else next((s for s in specs if s["label"] == params.get("object")), None)
            if not spec:
                raise ValueError("对象不在该技能已发布的查询范围内")
            data = query_object(db, spec, "skill." + mode, user.id)
            summary = f"{spec['label']}：本次查询返回 {len(data['rows'])} 行，最多 {data['sample_limit']} 行。"
        elif mode == "quality":
            checks = []
            for spec in specs:
                sample = query_object(db, spec, "skill.quality", user.id)
                checks.append({"object": spec["label"], "sample_rows": len(sample["rows"]), "status": "passed"})
            data = {"checks": checks, "scope": "发布契约、字段映射、取样主键非空与唯一性；每对象最多20行，不代表全量质量合格"}
            summary = f"{len(checks)} 个对象的发布契约及数据取样检查通过。"
        else:
            raise ValueError("不支持的技能执行器")
        result = {"success": True, "summary": summary, "data": data, "project_id": project.id,
                  "release_number": project.release_number, "synthetic": bool(project.config.get("example_key"))}
    except (ValueError, HTTPException) as exc:
        result = {"success": False, "summary": str(getattr(exc, "detail", exc)), "data": {}}
    except Exception:
        # Driver exceptions may contain connection parameters; never return them to a model/UI.
        result = {"success": False, "summary": "数据读取失败，请检查数据源连接和执行审计", "data": {}}
    run = SkillRun(skill_id=skill.id, skill_version=skill.current_version, user_id=user.id,
                   source=source, params=params, result=result, status="success" if result["success"] else "failed",
                   duration_ms=int((time.monotonic() - started) * 1000))
    db.add(run); db.commit(); db.refresh(run)
    return {**result, "run_id": run.id}
