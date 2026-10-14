import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.database import Base
from app.models import User, Skill, Agent, Asset, Connection, DeliveryProject, AgentTrace, ModelRegistry
from app.models.customer_demo import CustomerDemoPack, SkillRun
from app.models.system_config import SystemConfig
from app.services.customer_demo import install_customer_demo
from app.services.business_skills import run_business_skill
from app.services.skill_chat import chat_events


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    path = tmp_path_factory.mktemp("customer-demo")
    import os
    previous = os.environ.get("DEMO_DB_DIR")
    os.environ["DEMO_DB_DIR"] = str(path)
    engine = create_engine(f"sqlite:///{path}/platform.db", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)
    user = User(username="demo-admin", name="测试管理员", password_hash="test-only", role="admin")
    db.add(user); db.commit()
    install_customer_demo(db)
    yield db, user
    db.close(); engine.dispose()
    if previous is None:
        os.environ.pop("DEMO_DB_DIR", None)
    else:
        os.environ["DEMO_DB_DIR"] = previous


def test_install_idempotent_and_all_skills_have_real_results(demo):
    db, user = demo
    packs = db.query(CustomerDemoPack).all()
    assert len(packs) == 4 and all(p.status == "ready" for p in packs)
    original = {m.__tablename__: db.query(m).count() for m in (Skill, Agent, Asset, Connection, DeliveryProject, SkillRun)}
    install_customer_demo(db)
    assert original == {m.__tablename__: db.query(m).count() for m in (Skill, Agent, Asset, Connection, DeliveryProject, SkillRun)}
    for skill in db.query(Skill).all():
        result = run_business_skill(db, skill, skill.test_cases[0]["params"], user)
        assert result["success"], result
        assert result["run_id"] and result["release_number"] == 1


def test_skill_reads_changed_database_and_rejects_scope_override(demo):
    db, user = demo
    pack = db.get(CustomerDemoPack, "supply")
    skill = db.get(Skill, pack.resources["skill_ids"][0])
    project = db.get(DeliveryProject, pack.project_id)
    asset = db.get(Asset, project.config["output_asset_ids"][-1])
    conn = db.get(Connection, asset.connection_id)
    with sqlite3.connect(conn.database) as raw:
        raw.execute("UPDATE obj_findings SET reason='DATABASE_CHANGED' WHERE id=(SELECT id FROM obj_findings LIMIT 1)")
    result = run_business_skill(db, skill, {}, user)
    assert any("DATABASE_CHANGED" in row for row in result["data"]["rows"])
    assert not run_business_skill(db, skill, {"sql": "DELETE FROM obj_findings"}, user)["success"]
    stranger = User(id="stranger", username="stranger", name="陌生用户", role="viewer", password_hash="test")
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        run_business_skill(db, skill, {}, stranger)


def test_ai_native_tool_call_uses_database_and_persists_trace(demo):
    db, user = demo
    pack = db.get(CustomerDemoPack, "supply")
    agent = db.get(Agent, pack.resources["agent_id"])
    model = ModelRegistry(name="测试DeepSeek", provider="deepseek", model_name="deepseek-chat", api_base="https://api.deepseek.com", api_key="TEST-ONLY", status="active")
    db.add(model); db.commit()
    agent.model_id = model.id; db.commit()
    skill = db.get(Skill, pack.resources["skill_ids"][0])
    from openai.types.chat import ChatCompletionMessage
    call = ChatCompletionMessage(role="assistant", content=None, tool_calls=[{"id": "tool1", "type": "function", "function": {"name": "skill_" + skill.id.replace("-", ""), "arguments": "{}"}}])
    final = ChatCompletionMessage(role="assistant", content="根据合成数据库的查询证据，存在需要人工复核的业务结果。")
    client = Mock()
    client.chat.completions.create.side_effect = [SimpleNamespace(choices=[SimpleNamespace(message=call)]), SimpleNamespace(choices=[SimpleNamespace(message=final)])]
    events = list(chat_events(db, agent, user, "当前哪些订单有风险？", client=client))
    results = [e for e in events if e["type"] == "tool_result"]
    assert len(results) == 1 and results[0]["success"]
    assert any("DATABASE_CHANGED" in row for row in results[0]["data"]["rows"])
    assert events[-1]["type"] == "answer"
    assert db.get(SkillRun, results[0]["run_id"]).source == "agent:" + agent.id
    assert db.query(AgentTrace).filter_by(agent_id=agent.id).order_by(AgentTrace.created_at.desc()).first().status == "ok"
    assert client.chat.completions.create.call_args.kwargs["model"] == "deepseek-chat"
    messages = client.chat.completions.create.call_args.kwargs["messages"]
    assert any(m["role"] == "tool" and "DATABASE_CHANGED" in m["content"] for m in messages)


def test_ai_without_successful_tool_call_cannot_report_success(demo):
    db, user = demo
    agent = db.get(Agent, db.get(CustomerDemoPack, "supply").resources["agent_id"])
    from openai.types.chat import ChatCompletionMessage
    client = Mock()
    client.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(message=ChatCompletionMessage(role="assistant", content="已完成"))])
    events = list(chat_events(db, agent, user, "检查风险", client=client))
    assert events[-1]["type"] == "error"
    assert not any(e["type"] == "answer" for e in events)


def test_ai_provider_401_reports_safe_actionable_error(demo):
    db, user = demo
    agent = db.get(Agent, db.get(CustomerDemoPack, "supply").resources["agent_id"])
    client = Mock()
    provider_error = RuntimeError("provider response may contain credentials")
    provider_error.status_code = 401
    client.chat.completions.create.side_effect = provider_error
    events = list(chat_events(db, agent, user, "检查风险", client=client))
    assert events[0]["type"] == "model_status"
    assert events[-1]["type"] == "error"
    assert "401" in events[-1]["content"]
    assert "credentials" not in events[-1]["content"]


def test_ontology_api_queries_relations_and_rejects_identifier_injection(demo):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.database import get_db
    from app.core.deps import require_user
    from app.api.v1.ontology_api import router
    from app.models import OntologyEntity
    db, user = demo
    project = db.get(DeliveryProject, db.get(CustomerDemoPack, "supply").project_id)
    product = db.get(OntologyEntity, project.config["entity_ids"][0])
    api = FastAPI(); api.include_router(router)
    api.dependency_overrides[get_db] = lambda: db
    client = TestClient(api)
    root = "/ontology-api/objects/" + product.name
    assert client.get(root).status_code == 401
    api.dependency_overrides[require_user] = lambda: user
    response = client.get(root)
    assert response.status_code == 200, response.text
    assert response.json()["instances"][0]["id"] == "P1"
    assert response.json()["instances"][0]["$id"] == "P1"
    assert response.json()["asset_id"] and response.json()["asset_name"]
    related = client.get(root + "/P1/relations").json()
    assert len(related["relations"][0]["instances"]) == 2
    assert related["relations"][0]["name"] == "hasSku"
    assert related["relations"][0]["target_api_name"]
    assert client.get(root, params={"filter": json.dumps({"id) OR 1=1 --": "P1"})}).status_code == 422
    assert client.get(root, params={"filter": json.dumps({"id": "P1' OR 1=1 --"})}).json()["count"] == 0
    assert client.get(root, params={"offset": 1}).json()["count"] == 0
    assert client.post(root, json={"id": "P2"}).status_code == 405


def test_standalone_skill_node_failure_and_cycle_are_not_success(demo):
    from app.services.agent.graph_engine import GraphEngine
    db, _ = demo
    failed = GraphEngine(db, [{"id": "skill", "type": "skillNode", "data": {"skill_id": "missing"}}], [], emit_node_io=True)
    events = list(failed.run_for_scene({}))
    assert any(e["type"] == "scene_failed" for e in events)
    assert not any(e["type"] == "scene_finished" for e in events)
    cycle = GraphEngine(db, [{"id": "a", "type": "skillNode", "data": {}}], [{"source": "a", "target": "a"}], emit_node_io=True)
    assert list(cycle.run_for_scene({}))[-1]["type"] == "scene_failed"


def test_model_system_settings_and_registry_use_one_configuration(demo):
    from app.models.system_config import SystemConfig
    from app.api.v1.system_config import get_ai_models, save_ai_models, test_ai_model
    from app.services.llm_resolver import resolve_agent_model, agent_model_status
    db, user = demo
    settings = SystemConfig(group="ai", key="ai.models", value=json.dumps([{"id": "m1", "model_id": "deepseek-chat", "base_url": "https://api.deepseek.com/v1", "api_key": "TEST-SECRET", "scenes": ["agent"], "is_default": True}]))
    db.add(settings); db.commit()
    assert resolve_agent_model(db)["model"] == "deepseek-chat"
    status = agent_model_status(db)
    assert status["configured"] and status["host"] == "api.deepseek.com"
    assert "TEST-SECRET" not in json.dumps(status)
    masked = get_ai_models(db, user)["models"][0]
    assert masked["api_key"] != "TEST-SECRET"
    save_ai_models({"models": [masked]}, db, user)
    assert "TEST-SECRET" in settings.value
    with patch("openai.OpenAI") as factory:
        factory.return_value.chat.completions.create.return_value.choices = [SimpleNamespace(message=SimpleNamespace(content="OK"))]
        assert test_ai_model({"id": "m1"}, db, user).success
        assert factory.call_args.kwargs["api_key"] == "TEST-SECRET"
    db.delete(settings); db.commit()


def test_pipeline_change_flows_through_published_skill(demo):
    from app.api.v1.delivery import project_run_pipelines
    db, user = demo
    pack = db.get(CustomerDemoPack, "supply")
    project = db.get(DeliveryProject, pack.project_id)
    asset = db.get(Asset, project.config["asset_ids"][0])
    conn = db.get(Connection, asset.connection_id)
    with sqlite3.connect(conn.database) as raw:
        raw.execute("UPDATE raw_inventory SET quantity=50 WHERE id='I1'")
    project_run_pipelines(project.id, db, user)
    skill = db.get(Skill, pack.resources["skill_ids"][0])
    result = run_business_skill(db, skill, {}, user)
    assert result["success"]
    assert len(result["data"]["rows"]) == 1
    assert result["data"]["rows"][0][1] == "无可用物流"


def test_registered_assets_documents_templates_and_graph_counts(demo):
    from app.services import dwd_catalog
    from app.api.v1.customer_demo import template
    from app.api.v1.ai_builder_v2 import list_documents
    from app.services.ai_builder_v2 import read_document
    from app.services.file_import import preview_json_ontology
    from app.api.v1.studio import get_tbox, get_capability
    db, user = demo
    domains = dwd_catalog.get_domains(db)
    assert len(domains) == 4
    tables = dwd_catalog.get_tables_by_domains(domains, db=db)
    assert len({t['table_name'] for t in tables}) == len(tables) == db.query(Asset).count()
    assert all(dwd_catalog.get_table_schema(t['table_name'], db) for t in tables)
    docs = list_documents(db=db)['documents']
    assert len(docs) == 4 and all(read_document(d['key'], db) for d in docs)
    for key in ('health', 'library', 'bim', 'supply'):
        preview = preview_json_ontology(template(key, db, user), '')
        assert preview['objects'] and preview['relations']
    assert get_capability(db)['meta']['skillCount'] == 12
    tbox = get_tbox(db)
    assert tbox
