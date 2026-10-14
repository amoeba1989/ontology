"""Idempotent, isolated customer demonstration; never reseed existing source rows."""
from datetime import datetime
from uuid import uuid5, NAMESPACE_URL

from app.models import (User, Connection, DeliveryProject, OntologyEntity, EntityRelation, Asset, ObjectBinding,
                        Skill, Agent, AipScene, BusinessDocument, SceneRegistry, OntologyFunction, BusinessRule)
from app.models.customer_demo import CustomerDemoPack
from app.services.delivery_examples import EXAMPLES, create_example
from app.services.business_skills import run_business_skill


def stable_id(key, resource):
    return str(uuid5(NAMESPACE_URL, "ontology/customer-demo/v1/" + key + "/" + resource))


def install_customer_demo(db):
    from app.api.v1.delivery import project_run_pipelines, project_publish_ontology, test_project, publish_project
    from app.services.skill_version_service import publish_skill
    from app.services.data_plane.lineage_service import LineageService
    from app.services.data_plane.quality_rule_service import QualityRuleService
    from app.models.quality_rule import QualityRule
    from app.services.data_plane.execute_service import ExecuteService, ExecuteRequest
    from app.services.rule_engine import RuleEvaluator
    from app.services.function_executor import FunctionExecutor
    from app.api.v1.aip_scenes import publish_scene
    from app.services.aip.scene_runner import create_execution_row, run_scene_stream

    user = db.query(User).filter_by(role="admin").order_by(User.created_at).first()
    if not user:
        raise ValueError("请先完成管理员账号初始化")
    for key, spec in EXAMPLES.items():
        pack = db.get(CustomerDemoPack, key)
        if pack and pack.status == "ready":
            continue
        if not pack:
            create_example(db, user, key, managed_key=key)
            pack = db.get(CustomerDemoPack, key)
        project = db.get(DeliveryProject, pack.project_id)
        if not project:
            raise ValueError(f"演示项目 {key} 已被删除，请先处理安装记录，避免覆盖或重复创建")
        # Reuse its original owner on resumption.
        owner = db.get(User, project.owner_id)
        entities = [db.get(OntologyEntity, eid) for eid in project.config["entity_ids"]]
        findings = entities[-1]
        if not project.release:
            project.name = spec["name"] + " · 客户演示（合成数据）"
            for entity in entities:
                entity.domain = spec["name"]
                entity.status = "published"
            relations = db.query(EntityRelation).filter(EntityRelation.from_entity_id.in_(project.config["entity_ids"])).all()
            table_entities = dict(zip([*spec["tables"], "findings"], entities))
            for src, target, predicate, source_key, target_key in spec["relations"]:
                rel = next(r for r in relations if r.name == predicate and r.from_entity_id == table_entities[src].id and r.to_entity_id == table_entities[target].id)
                rel.name_cn = f"{table_entities[src].name_cn} → {table_entities[target].name_cn}"
                rel.cardinality = "1:N" if source_key == "id" and target_key != "id" else "N:1" if target_key == "id" else "N:N"
                entity = table_entities[src]
                configs = dict(entity.config_json or {})
                configs["relation_bindings"] = {**configs.get("relation_bindings", {}), rel.id: {"source_column": source_key, "target_column": target_key}}
                entity.config_json = configs
            db.commit()
            # Runs only the isolated demo database's pipelines, never existing customer pipelines.
            project_run_pipelines(project.id, db, owner)
            if not project.config.get("version_id"):
                project_publish_ontology(project.id, db, owner)
            project.config = {**project.config, "acceptance_evidence": f"自动化样例验收：真实管道、对象取样及初始规则结果应为 {spec['expected_findings']} 条；不代表实际客户业务验收。"}
            project.revision += 1
            db.commit()
            tested = test_project(project.id, db, owner)
            actual = len(tested["samples"][-1]["rows"])
            if actual != spec["expected_findings"]:
                raise ValueError(f"{key} 初始规则结果异常：{actual}")
            publish_project(project.id, db, owner)
        for entity in entities:
            binding = db.query(ObjectBinding).filter_by(object_type_id=entity.id, role="primary").first()
            LineageService(db).upsert_binding(binding.asset_id, entity.id, via_module="customer-demo")
        for asset_id in [*project.config["asset_ids"], *project.config["output_asset_ids"]]:
            asset = db.get(Asset, asset_id)
            counted = ExecuteService(db).execute(ExecuteRequest(asset_id=asset_id, sql="SELECT COUNT(*) AS n FROM <asset>",
                params={}, purpose="demo.profile", user_id=owner.id, bypass_cache=True))
            asset.profile = {**(asset.profile or {}), "row_count": counted.rows[0][0], "sampled_at": datetime.utcnow().isoformat() + "Z"}
            db.commit()
        quality = QualityRuleService(db)
        for asset_id in project.config["output_asset_ids"]:
            rule = db.query(QualityRule).filter_by(asset_id=asset_id, kind="pk_uniqueness").first()
            if not rule:
                rule = quality.create_rule(asset_id=asset_id, name="演示对象主键唯一性", kind="pk_uniqueness", column_name="id", user_id=owner.id)
            state = quality.evaluate(rule.id)
            if state.status != "healthy":
                raise ValueError(f"{key} 数据质量检查未通过：{state.status}")
        skill_ids = []
        for operation, label, desc in [("findings", "业务风险与规则结果", "查询当前业务规则结果与原因，支持证据溯源"),
                ("query", "本体对象查询", "按业务对象名称查询实际数据库记录"),
                ("quality", "交付链路检查", "检查已发布契约、字段映射以及对象取样主键质量")]:
            sid = stable_id(key, operation)
            skill = db.get(Skill, sid)
            if not skill:
                schema = {"type": "object", "properties": {}, "additionalProperties": False}
                if operation == "query":
                    schema["properties"] = {"object": {"type": "string", "enum": [e.name_cn for e in entities], "description": "要查询的业务对象"}}
                    schema["required"] = ["object"]
                skill = Skill(id=sid, name=spec["name"] + " · " + label, description=desc + "。合成演示数据。" + spec["boundary"],
                    skill_type="configured", status="draft", current_version=0, code_ref=f"demo.{key}.{operation}",
                    config_json={"project_id": project.id, "entity_id": findings.id, "operation": operation},
                    input_schema=schema, output_schema={"type": "object", "description": "真实查询结果、取样范围、应用版本和执行记录编号"},
                    asset_refs={"asset_ids": project.config["output_asset_ids"], "entity_ids": project.config["entity_ids"]},
                    created_by=owner.id, prompt_template="请先调用技能，再根据查询证据回答；人工复核在应用中操作。",
                    test_cases=[{"params": {"object": entities[0].name_cn} if operation == "query" else {}, "expected": "success=true；返回数据库数据与运行记录"}])
                db.add(skill); db.commit()
            if not skill.current_version:
                publish_skill(skill, "发布受控数据库查询技能", owner.id, db)
            result = run_business_skill(db, skill, skill.test_cases[0]["params"], owner, "installation")
            if not result["success"]:
                raise ValueError(result["summary"])
            skill_ids.append(sid)
        aid = stable_id(key, "agent")
        if not db.get(Agent, aid):
            db.add(Agent(id=aid, name=spec["name"] + "助手", description="调用已发布技能读取合成数据库，使用系统已配置的大模型生成有依据的回答。",
                tags=["客户演示", "数据库技能"], entity_ids=project.config["entity_ids"], ontology_version_id=project.config["version_id"],
                system_prompt=spec["goal"] + "\n" + spec["boundary"], tools_config={"skill_ids": skill_ids, "project_id": project.id,
                    "model_preference": "deepseek", "suggested_questions": [spec["questions"], "检查当前应用的数据流转与对象数据是否就绪"]}, status="published"))
            db.commit()
        fid = stable_id(key, "function")
        if not db.get(OntologyFunction, fid):
            db.add(OntologyFunction(id=fid, entity_id=findings.id, name=spec["name"] + "规则结果计数", return_type="number",
                description="实时统计数据库中当前规则结果，非固定样例值", logic_type="sql", logic_body="SELECT COUNT(*) FROM <asset>",
                input_schema=[], callable_name=f"demo_{key}_finding_count", tags=["客户演示"]))
            db.commit()
        function = db.get(OntologyFunction, fid)
        computed = FunctionExecutor(db).execute(function, {})
        if not computed.success:
            raise ValueError("演示计算函数执行失败")
        function.execution_count = (function.execution_count or 0) + 1
        function.last_executed = datetime.utcnow()
        for rule in db.query(BusinessRule).filter_by(entity_id=findings.id):
            RuleEvaluator(db).evaluate(rule, owner.id)
        did = stable_id(key, "document")
        if not db.get(BusinessDocument, did):
            content = f"# {spec['name']}\n目标：{spec['goal']}\n问题：{spec['questions']}\n对象：{'、'.join(e.name_cn for e in entities)}\n约束：" + "、".join(n for n, _ in spec['rules']) + "\n" + spec['boundary']
            db.add(BusinessDocument(id=did, name=spec["name"] + "业务需求说明.md", file_type="md", parsed_text=content,
                summary=spec["goal"], domain_tags=[spec["name"], "合成演示"], size_bytes=len(content.encode()), uploaded_by=owner.id))
        rid = stable_id(key, "scene-card")
        if not db.get(SceneRegistry, rid):
            db.add(SceneRegistry(id=rid, name=spec["name"] + " · 客户演示", description=spec["goal"] + "（合成数据）",
                icon="◈", route=f"/apps/projects/{project.id}", assets={"object_classes": project.config["entity_ids"],
                    "action_ids": project.config["action_ids"], "agent_ids": [aid]}, created_by=owner.id))
        scene_id = stable_id(key, "flow")
        scene = db.get(AipScene, scene_id)
        if not scene:
            nodes = [{"id": "quality", "type": "skillNode", "position": {"x": 80, "y": 100}, "data": {"label": "数据契约检查", "skill_id": skill_ids[2], "on_error": "stop"}},
                     {"id": "findings", "type": "skillNode", "position": {"x": 400, "y": 100}, "data": {"label": "查询业务规则结果", "skill_id": skill_ids[0], "on_error": "stop"}}]
            scene = AipScene(id=scene_id, name=spec["name"] + "业务检查", description="读取已发布本体应用；结果可在运行记录核验，不调用大模型。",
                group_name="客户演示", nodes_json=nodes, edges_json=[{"id": "q-f", "source": "quality", "target": "findings"}],
                ontology_bindings=project.config["entity_ids"], datasource_bindings=project.config["output_asset_ids"], created_by=owner.id)
            db.add(scene)
        db.commit()
        if not scene.published_version_id:
            publish_scene(scene.id, db)
        execution = create_execution_row(db, scene, "installation", {}, {})
        list(run_scene_stream(db, scene, execution, {}))
        if execution.status != "success":
            raise ValueError("演示编排运行失败：" + (execution.error_message or ""))
        pack.resources = {"skill_ids": skill_ids, "agent_id": aid, "scene_id": scene_id, "document_id": did, "function_id": fid}
        pack.status = "ready"
        pack.report = {"initial_findings": spec["expected_findings"], "objects": len(entities), "skills": len(skill_ids), "flow": execution.status}
        db.commit()
    return demo_status(db)


def demo_status(db):
    from app.services.llm_resolver import agent_model_status
    return {"packs": [{"key": p.key, "project_id": p.project_id, "status": p.status,
                       "resources": p.resources, "report": p.report} for p in db.query(CustomerDemoPack).all()],
            "model": agent_model_status(db)}


def verify_customer_demo(db, check_ai=False):
    from app.services.skill_chat import chat_events
    from app.models import Pipeline, PipelineRun, EntityAction, OntologyVersion, LineageEdge, ExecutionLog
    from app.models.quality_rule import HealthStatus
    from app.services.llm_resolver import agent_model_status
    report = {"ok": True, "packs": [], "model": agent_model_status(db), "checked_at": datetime.utcnow().isoformat() + "Z"}
    for pack in db.query(CustomerDemoPack).all():
        project = db.get(DeliveryProject, pack.project_id)
        user = db.get(User, project.owner_id) if project else None
        checks = []
        for sid in pack.resources.get("skill_ids", []):
            skill = db.get(Skill, sid)
            if not skill:
                checks.append({"success": False, "summary": "技能不存在"})
            else:
                checks.append(run_business_skill(db, skill, skill.test_cases[0]["params"], user, "verification"))
        passed = pack.status == "ready" and len(checks) == 3 and all(c["success"] for c in checks)
        item = {"key": pack.key, "data_passed": passed, "skills_passed": sum(c["success"] for c in checks)}
        if check_ai:
            agent = db.get(Agent, pack.resources.get("agent_id"))
            events = list(chat_events(db, agent, user, "请调用业务风险与规则结果技能，概括当前数据库中的结果，标明数据范围及需人工复核的内容。")) if agent and user else []
            called = [e for e in events if e.get("type") == "tool_result" and e.get("success")]
            answered = any(e.get("type") == "answer" for e in events)
            model = next((e.get("model") for e in events if e.get("type") == "model_status"), None)
            item["ai"] = {"passed": bool(called and answered), "model": model, "tool_calls": len(called),
                          "run_ids": [e["run_id"] for e in called], "checked_at": report["checked_at"]}
            if not item["ai"]["passed"]:
                item["ai"]["message"] = next((e.get("content") for e in events if e.get("type") == "error"), "未完成问答闭环")
            pack.report = {**pack.report, "ai": item["ai"]}
            passed = passed and item["ai"]["passed"]
        report["ok"] = report["ok"] and passed
        report["packs"].append(item)
    report["ok"] = report["ok"] and len(report["packs"]) == 4
    report["menus"] = {"数据连接": db.query(Connection).count(), "数据资产": db.query(Asset).count(),
        "数据管道": db.query(Pipeline).count(), "管道运行": db.query(PipelineRun).count(), "数据血缘": db.query(LineageEdge).count(),
        "质量检查": db.query(HealthStatus).count(), "本体对象": db.query(OntologyEntity).count(), "对象映射": db.query(ObjectBinding).count(),
        "对象关系": db.query(EntityRelation).count(), "业务规则": db.query(BusinessRule).count(), "计算函数": db.query(OntologyFunction).count(),
        "业务行动": db.query(EntityAction).count(), "本体版本": db.query(OntologyVersion).count(), "业务文档": db.query(BusinessDocument).count(),
        "技能": db.query(Skill).count(), "智能体": db.query(Agent).count(), "业务编排": db.query(AipScene).count(), "执行审计": db.query(ExecutionLog).count()}
    db.commit()
    return report
