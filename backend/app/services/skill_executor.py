"""
内置 Skill 执行器 — 将场景验证的业务逻辑封装为可复用的 skill 函数
每个 skill 函数签名: (params: dict, db: Session) -> dict
返回统一格式: { success: bool, summary: str, data: dict }
"""
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import OntologyEntity, BusinessRule
from app.services.data_plane.entity_data_service import EntityDataService
from app.services.rule_engine import RuleEvaluator

logger = logging.getLogger(__name__)

SKILL_REGISTRY: dict[str, callable] = {}


def register_skill(code_ref: str):
    def decorator(fn):
        SKILL_REGISTRY[code_ref] = fn
        return fn
    return decorator


def execute_skill(code_ref: str, params: dict, db: Session) -> dict:
    fn = SKILL_REGISTRY.get(code_ref)
    if fn:
        try:
            return fn(params, db)
        except Exception as e:
            logger.error(f"Skill {code_ref} 执行失败: {e}")
            return {"success": False, "summary": f"执行失败: {e}", "data": {}}
    # Fallback: check for generated skill
    from app.models.skill import Skill
    skill = db.query(Skill).filter(Skill.code_ref == code_ref, Skill.skill_type == "generated", Skill.status == "active").first()
    if skill:
        return execute_generated_skill(skill, params, db)
    return {"success": False, "summary": f"未知 skill: {code_ref}", "data": {}}


SKILL_STREAM_REGISTRY: dict[str, callable] = {}


def register_skill_stream(code_ref: str):
    def decorator(fn):
        SKILL_STREAM_REGISTRY[code_ref] = fn
        return fn
    return decorator


def has_skill_stream(code_ref: str) -> bool:
    return code_ref in SKILL_STREAM_REGISTRY


def execute_skill_stream(code_ref: str, params: dict, db: Session):
    fn = SKILL_STREAM_REGISTRY.get(code_ref)
    if not fn:
        result = execute_skill(code_ref, params, db)
        yield {"step": "result", "status": "complete", "summary": result.get("summary", ""), "data": result.get("data", {})}
        return
    try:
        yield from fn(params, db)
    except Exception as e:
        logger.error(f"Skill stream {code_ref} 执行失败: {e}")
        yield {"step": "error", "status": "error", "message": str(e)}




def execute_skill_tool_call(tool_type: str, tool_config: dict, params: dict, db: Session) -> dict:
    """Execute a rule or function tool referenced by a skill."""
    if tool_type == "rule":
        rule_id = tool_config.get("rule_id")
        if not rule_id:
            return {"success": False, "summary": "Missing rule_id", "data": {}}
        rule = db.query(BusinessRule).get(rule_id)
        if not rule:
            return {"success": False, "summary": f"Rule {rule_id} not found", "data": {}}
        user_id = params.get("user_id", "")
        evaluator = RuleEvaluator(db)
        result = evaluator.evaluate(rule, user_id)
        db.commit()
        return {
            "success": True,
            "summary": f"Rule '{result.rule_name}' {'triggered' if result.triggered else 'not triggered'}",
            "data": {
                "triggered": result.triggered,
                "confidence": result.confidence,
                "risk_level": result.risk_level,
                "matched_count": result.matched_count,
                "total_count": result.total_count,
            },
        }

    elif tool_type == "function":
        from app.services.function_executor import FunctionExecutor
        callable_name = tool_config.get("callable_name")
        func_id = tool_config.get("function_id")
        executor = FunctionExecutor(db)
        if callable_name:
            result = executor.execute_by_callable_name(callable_name, params)
        elif func_id:
            from app.models.function import OntologyFunction
            func = db.get(OntologyFunction, func_id)
            if not func:
                return {"success": False, "summary": f"Function {func_id} not found", "data": {}}
            result = executor.execute(func, params)
        else:
            return {"success": False, "summary": "Missing callable_name or function_id", "data": {}}

        return {
            "success": result.success,
            "summary": f"Function returned: {result.value}" if result.success else f"Error: {result.error}",
            "data": {"value": result.value, "execution_ms": result.execution_ms},
        }

    return {"success": False, "summary": f"Unknown tool type: {tool_type}", "data": {}}


def execute_generated_skill(skill, params: dict, db) -> dict:
    """Execute a generated skill by running its tools in sandbox."""
    from app.models.skill_tool import SkillTool
    from app.services.skill_sandbox import execute_in_sandbox

    tools = db.query(SkillTool).filter(SkillTool.skill_id == skill.id).all()
    results = {}
    for tool in tools:
        try:
            output = execute_in_sandbox(tool.code, tool.name, params)
            results[tool.name] = {"success": True, "output": output}
        except Exception as e:
            results[tool.name] = {"success": False, "error": str(e)}

    return {
        "success": all(r["success"] for r in results.values()),
        "summary": f"Executed {len(tools)} tools",
        "data": results,
    }
