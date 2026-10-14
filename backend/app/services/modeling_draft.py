"""Deterministic rule checks and AI proposals; model output never executes code."""
import json
import operator
from app.schemas.modeling_draft import DraftContent, DraftRule


def evaluate_constraint(rule: DraftRule, values: dict):
    outcomes = []
    comparisons = {"eq": operator.eq, "ne": operator.ne, "gt": operator.gt, "gte": operator.ge, "lt": operator.lt, "lte": operator.le}
    for clause in rule.clauses:
        actual = values.get(clause.field)
        try:
            if clause.operator == "required":
                passed = actual is not None and actual != ""
            elif actual is None:
                passed = False
            elif clause.operator == "in":
                passed = actual in clause.value
            elif clause.operator in ("gt", "gte", "lt", "lte") and type(actual) not in (int, float):
                passed = False
            else:
                passed = comparisons[clause.operator](actual, clause.value)
        except (TypeError, ValueError):
            passed = False
        outcomes.append({"field": clause.field, "actual": actual, "operator": clause.operator,
                         "expected": clause.value, "passed": bool(passed)})
    return {"valid": bool(outcomes) and all(c["passed"] for c in outcomes), "conditions": outcomes}


def test_rule(rule):
    cases = [{"label": e.label, "expected": e.expected, **evaluate_constraint(rule, e.values)} for e in rule.examples]
    for case in cases:
        case["passed"] = case["valid"] == case["expected"]
    coverage = {e.expected for e in rule.examples} == {True, False}
    return {"rule_id": rule.id, "passed": bool(rule.clauses) and coverage and all(c["passed"] for c in cases),
            "positive_and_negative": coverage, "cases": cases}


def normalize_reviews(content, previous=None):
    """Client-supplied accepted flags cannot bypass review or survive semantic edits."""
    old = {r["id"]: r for r in (previous or {}).get("rules", [])}
    old_entities = {e["name"]: e for e in (previous or {}).get("entities", [])}
    data = content.model_dump()
    for rule in data["rules"]:
        before = old.get(rule["id"])
        same = before and {k: v for k, v in before.items() if k not in ("status", "confirmed")} == {k: v for k, v in rule.items() if k not in ("status", "confirmed")}
        entity = next(e for e in data["entities"] if e["name"] == rule["entity"])
        if same and old_entities.get(rule["entity"]) == entity:
            rule["status"] = before["status"]
            if before["status"] == "accepted" and not rule["confirmed"]:
                rule["status"] = "pending"
        else:
            rule["status"] = "pending"
            rule["confirmed"] = False
    return data


def generate_proposal(db, draft, client=None):
    from app.models import OntologyEntity
    from app.services.llm_resolver import _resolve_model_from_db, _SCENE_FALLBACKS, _create_client
    config = _resolve_model_from_db(db, "ontology") or _SCENE_FALLBACKS["ontology"]
    if not all(config.get(k) for k in ("api_key", "base_url", "model")):
        raise ValueError("尚未配置建模模型，请在系统配置中设置 DeepSeek 或兼容接口")
    existing = [{"id": e.id, "name": e.name, "label": e.name_cn,
                 "attributes": [{"name": a.name, "type": a.type} for a in e.attributes]}
                for e in db.query(OntologyEntity).order_by(OntologyEntity.name).limit(100).all()]
    prompt = ("你是通用业务本体建模助手。按用户场景生成可编辑草稿，不能执行任何业务行动。"
              "优先复用提供的已有对象（reuse_id必须来自目录，属性只能引用已有属性）。完整保留有用的当前草稿，补充对象、属性、关系和规则。"
              "规则是数据必须满足的约束，clauses之间为AND；examples.expected=true表示合格，false表示违反。每条规则提供正反两个样例。"
              "推荐规则全部pending且confirmed=false，origin=ai；basis说明依据是否仅为模型建议，禁止虚构标准条款。"
              "说明适用前提、单位、例外；无法确定的阈值不要编造，写入questions。高度必须区分离地与海拔；跨介质设备不适用普通航空设备的环境假设。"
              "属性英文标识snake_case，对象PascalCase，关系camelCase。返回符合下面JSON Schema的单个JSON对象，不输出Markdown。\n"
              + json.dumps(DraftContent.model_json_schema(), ensure_ascii=False))
    owned = client is None
    client = client or _create_client(config["api_key"], config["base_url"]).with_options(timeout=90, max_retries=0)
    try:
        response = client.chat.completions.create(model=config["model"], messages=[{"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps({"scenario": draft.scenario, "current_draft": draft.content, "existing_objects": existing}, ensure_ascii=False)}],
            response_format={"type": "json_object"}, temperature=0.2, max_tokens=8000)
        raw = response.choices[0].message.content or ""
        if response.choices[0].finish_reason == "length":
            raise ValueError("AI 输出超过长度限制，请缩小场景范围后重试")
        content = DraftContent.model_validate_json(raw)
        if not content.entities:
            raise ValueError("AI 未生成对象，请补充业务目标")
        allowed = {e["id"]: e for e in existing}
        for e in content.entities:
            if e.reuse_id and (e.reuse_id not in allowed or allowed[e.reuse_id]["name"] != e.name):
                raise ValueError("AI 引用了目录外的对象，请重新生成")
        for rule in content.rules:
            rule.status = "pending"; rule.confirmed = False; rule.origin = "ai"
        return {"content": content.model_dump(), "model": config["model"], "base_revision": draft.revision}
    finally:
        if owned:
            client.close()


def drone_template():
    """Explicit sample, never presented as a live AI generation."""
    def attr(name, label, typ="string", unit="", description=""):
        return {"name": name, "label": label, "type": typ, "unit": unit, "description": description}
    data = {"entities": [
        {"name": "Aircraft", "label": "无人机", "attributes": [attr("identifier", "设备标识"), attr("name", "名称"), attr("model", "机型"), attr("height_agl", "离地高度", "number", "米", "必须来自明确标注AGL的观测值，不能用海拔高度代替")]},
        {"name": "Airspace", "label": "空域", "attributes": [attr("identifier", "空域编号"), attr("name", "名称"), attr("category", "空域类别")]},
        {"name": "ResponseFacility", "label": "处置设施", "attributes": [attr("identifier", "设施编号"), attr("name", "名称"), attr("status", "运行状态")]}
    ], "relations": [{"name": "observedIn", "label": "观测所在空域", "source": "Aircraft", "target": "Airspace", "cardinality": "N:N"}],
    "rules": [{"id": "agl-nonnegative", "name": "离地高度非负", "entity": "Aircraft", "kind": "common", "origin": "template",
        "basis": "演示规则模板，待业务确认；不是法律或飞行许可判断", "assumptions": "高度为以米计的离地高度AGL；数据已完成传感器误差处理",
        "exceptions": "海拔高度、传感器误差和跨介质设备需另行建模", "clauses": [{"field": "height_agl", "operator": "gte", "value": 0}],
        "examples": [{"label": "正常离地高度", "values": {"height_agl": 30}, "expected": True}, {"label": "负离地高度", "values": {"height_agl": -5}, "expected": False}]}],
    "questions": ["空域边界、有效时段和许可信息来自哪里？", "无人机位置是否具有观测时间与坐标系？", "哪些规则需要生成告警，哪些只标记数据异常？"]}
    return DraftContent.model_validate(data).model_dump()
