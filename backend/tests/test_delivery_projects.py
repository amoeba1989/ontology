"""Real SQLite end-to-end coverage for project delivery; no external services."""
from datetime import datetime
import sqlite3
import subprocess
import sys
import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base, get_db
from app.core.deps import require_user
from app.api.v1.delivery import router
from app.models import User, Connection, Asset, OntologyEntity, EntityAttribute, ObjectBinding
from app.models import OntologyVersion, OntologyVersionEntity, OntologyVersionAttribute, EntityAction
from app.models.pipeline import Pipeline, PipelineRun


@pytest.fixture
def workspace(tmp_path):
    source = tmp_path / "business.db"
    with sqlite3.connect(source) as raw:
        raw.execute("CREATE TABLE equipment (id TEXT PRIMARY KEY, status TEXT)")
        raw.execute("INSERT INTO equipment VALUES ('E1', 'warning')")
    engine = create_engine(f"sqlite:///{tmp_path / 'platform.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)
    owner = User(id="owner", username="owner", password_hash="test", name="Owner", role="editor")
    conn = Connection(name="equipment", type="sqlite", database=str(source), writable=True, rate_limit_qps=1000)
    db.add_all([owner, conn]); db.flush()
    asset = Asset(name="设备数据", kind="table", connection_id=conn.id, locator={"table": "equipment"},
                  schema_snapshot=[{"name": "id"}, {"name": "status"}], primary_key=["id"])
    entity = OntologyEntity(name="Equipment", name_cn="设备", tier=1, status="published")
    db.add_all([asset, entity]); db.flush()
    attrs = [EntityAttribute(entity_id=entity.id, name=n, type="string", required=True) for n in ("id", "status")]
    db.add_all(attrs); db.flush()
    binding = ObjectBinding(object_type_id=entity.id, asset_id=asset.id, role="primary", id_column="id",
                            field_mappings=[{"attribute_id": a.id, "source_column": a.name} for a in attrs])
    version = OntologyVersion(version_number=1, name="设备模型", status="published", is_active=True)
    db.add_all([binding, version]); db.flush()
    ve = OntologyVersionEntity(version_id=version.id, source_entity_id=entity.id, name=entity.name, name_cn=entity.name_cn, tier=1)
    db.add(ve); db.flush()
    db.add_all([OntologyVersionAttribute(version_entity_id=ve.id, source_attribute_id=a.id,
                                        name=a.name, type=a.type, required=True) for a in attrs])
    action = EntityAction(name="设备状态更新", entity_id=entity.id, category="domain", action_type="sql_exec",
                          type_config={"connection_id": conn.id, "sql": "UPDATE equipment SET status=:status WHERE id=:id"},
                          parameters_json=[{"name": "id", "type": "string", "required": True},
                                           {"name": "status", "type": "string", "required": True}])
    db.add(action); db.commit()
    api = FastAPI()
    api.include_router(router)
    api.dependency_overrides[get_db] = lambda: db
    api.dependency_overrides[require_user] = lambda: owner
    config = {"goal": "发现异常设备并更新处理状态", "audience": "运维", "questions": "哪些设备异常？",
              "acceptance": "更新后状态可查", "expected_actions": "更新设备状态",
              "asset_ids": [asset.id], "processing_mode": "direct", "processing_note": "已有规范设备表，无需加工",
              "entity_ids": [entity.id], "version_id": version.id, "action_ids": [action.id],
              "acceptance_evidence": "使用 E1 核对状态，后续在应用中验证状态更新"}
    with TestClient(api) as client:
        yield client, db, config, source, api, binding, asset, conn
    db.close(); engine.dispose()


def create(client, config):
    response = client.post('/delivery-projects', json={"name": "设备运维", "config": config})
    assert response.status_code == 201, response.text
    return response.json()


def publish(client, project):
    root = f"/delivery-projects/{project['id']}"
    tested = client.post(root + '/test')
    assert tested.status_code == 200, tested.text
    response = client.post(root + '/publish')
    assert response.status_code == 200, response.text
    return root


def test_real_query_publish_action_refresh_and_draft_isolation(workspace):
    client, db, config, source, _, _, _, _ = workspace
    project = create(client, config)
    root = publish(client, project)
    entity_id = config['entity_ids'][0]
    assert client.get(root + '/runtime/' + entity_id).json()['rows'] == [['E1', 'warning']]
    action_url = root + '/runtime/actions/' + config['action_ids'][0]
    params = {"id": "E1", "status": "resolved' ; DROP TABLE equipment; --"}
    response = client.post(action_url, json={"params": params, "dry_run": True})
    assert response.status_code == 200 and response.json()['success'], response.text
    assert client.get(root + '/runtime/' + entity_id).json()['rows'][0][1] == 'warning'
    response = client.post(action_url, json={"params": params})
    assert response.status_code == 200 and response.json()['success'], response.text
    # Parameter values remain data; the real source table is intact and refreshed.
    assert client.get(root + '/runtime/' + entity_id).json()['rows'][0][1] == params['status']
    with sqlite3.connect(source) as raw:
        assert raw.execute('SELECT count(*) FROM equipment').fetchone()[0] == 1
    draft = {**project['config'], 'entity_ids': [], 'goal': '新的业务需求'}
    saved = client.put(root, json={"name": "新草稿", "config": draft, "revision": 1})
    assert saved.status_code == 200
    assert client.get(root + '/runtime').json()['name'] == '设备运维'
    assert client.get(root + '/runtime/' + entity_id).status_code == 200
    assert client.post(root + '/publish').status_code == 400
    assert client.put(root, json={"name": "过时草稿", "config": config, "revision": 1}).status_code == 409
    events = client.get(root + '/events').json()
    assert any(e['kind'] == 'action' and e['status'] == 'success' for e in events)


def test_publish_requires_live_test_and_rejects_changed_mapping(workspace):
    client, db, config, _, _, binding, _, _ = workspace
    project = create(client, config)
    root = f"/delivery-projects/{project['id']}"
    assert client.post(root + '/publish').status_code == 400
    assert client.post(root + '/test').status_code == 200
    binding.field_mappings = list(reversed(binding.field_mappings)); db.commit()
    assert client.post(root + '/publish').status_code == 400
    assert client.post(root + '/test').status_code == 200
    assert client.post(root + '/publish').status_code == 200


def test_auth_ownership_and_unknown_runtime_objects(workspace):
    client, db, config, _, api, _, _, _ = workspace
    p = create(client, config)
    root = publish(client, p)
    assert client.get(root + '/runtime/not-a-project-object').status_code == 404
    api.dependency_overrides[require_user] = lambda: User(id='other', role='editor')
    assert client.get('/delivery-projects').json() == []
    assert client.get(root).status_code == 404
    assert client.post(root + '/publish').status_code == 404
    api.dependency_overrides.pop(require_user)
    assert client.get('/delivery-projects').status_code == 401


def test_asset_contract_changes_fail_closed(workspace):
    client, db, config, _, _, _, asset, _ = workspace
    root = publish(client, create(client, config))
    asset.locator = {"table": "another_table"}; db.commit()
    response = client.get(root + '/runtime/' + config['entity_ids'][0])
    assert response.status_code == 400
    assert '改变' in response.json()['detail']


def test_query_failure_recorded_and_recoverable(workspace):
    client, db, config, source, _, _, _, _ = workspace
    p = create(client, config)
    root = f"/delivery-projects/{p['id']}"
    with sqlite3.connect(source) as raw:
        raw.execute('ALTER TABLE equipment RENAME TO unavailable')
    assert client.post(root + '/test').status_code == 400
    assert client.get(root + '/events').json()[0]['status'] == 'error'
    with sqlite3.connect(source) as raw:
        raw.execute('ALTER TABLE unavailable RENAME TO equipment')
    assert client.post(root + '/test').status_code == 200


def test_pipeline_rejects_mock_wrong_sources_and_duplicate_append(workspace):
    client, db, config, _, _, _, asset, conn = workspace
    pipeline = Pipeline(name='加工', steps=['抽取', '加载'], engine='mock', status='success',
                        config_json={"source": {"connection_id": conn.id, "query": "SELECT * FROM equipment"},
                                     "target": {"connection_id": conn.id, "table": "equipment", "write_mode": "upsert"}})
    db.add(pipeline); db.flush()
    db.add(PipelineRun(pipeline_id=pipeline.id, status='success', finished_at=datetime.utcnow())); db.commit()
    config.update(processing_mode='pipeline', pipeline_ids=[pipeline.id], output_asset_ids=[asset.id])
    p = create(client, config)
    assert not p['steps'][2]['ready']
    pipeline.engine = 'real'; db.commit()
    assert client.get('/delivery-projects/' + p['id']).json()['steps'][2]['ready']
    pipeline.config_json = {**pipeline.config_json, 'source': {'connection_id': conn.id, 'query': 'SELECT * FROM hidden'}}
    db.commit()
    assert not client.get('/delivery-projects/' + p['id']).json()['steps'][2]['ready']


def test_seed_does_not_erase_business_changes(tmp_path):
    script = Path(__file__).resolve().parents[1] / 'scripts/seed_mil_demo.py'
    env = {**os.environ, 'DEMO_DB_DIR': str(tmp_path)}
    subprocess.run([sys.executable, str(script)], env=env, check=True, capture_output=True)
    with sqlite3.connect(tmp_path / 'mil_demo.db') as raw:
        raw.execute("UPDATE target SET name='业务修改' WHERE target_id='T-01'")
        raw.execute("INSERT INTO command_decision VALUES ('D1','T-01',NULL,'low',NULL,NULL,'保留工单','用户','now')")
    subprocess.run([sys.executable, str(script)], env=env, check=True, capture_output=True)
    with sqlite3.connect(tmp_path / 'mil_demo.db') as raw:
        assert raw.execute("SELECT name FROM target WHERE target_id='T-01'").fetchone()[0] == '业务修改'
        assert raw.execute('SELECT count(*) FROM command_decision').fetchone()[0] == 1


@pytest.mark.parametrize('key,expected', [('health', 3), ('library', 4), ('bim', 5), ('supply', 4)])
def test_four_business_examples_complete_real_chain(workspace, monkeypatch, tmp_path, key, expected):
    client, db, _, _, api, _, _, _ = workspace
    monkeypatch.setenv('DEMO_DB_DIR', str(tmp_path))
    owner = db.get(User, 'owner'); owner.role = 'admin'; db.commit()
    response = client.post('/delivery-projects/examples/' + key)
    assert response.status_code == 201, response.text
    project = response.json(); root = '/delivery-projects/' + project['id']
    assert not project['steps'][2]['ready']
    response = client.post(root + '/run-pipelines')
    assert response.status_code == 200, response.text
    assert all(s['ready'] for s in response.json()['steps'][:4]), response.text
    # Run twice to prove no duplicate output objects.
    assert client.post(root + '/run-pipelines').status_code == 200
    response = client.post(root + '/publish-ontology')
    assert response.status_code == 200, response.text
    project = response.json()
    config = {**project['config'], 'acceptance_evidence': '已按合成数据核对风险条数、重复运行及业务操作'}
    saved = client.put(root, json={'name': project['name'], 'config': config, 'revision': project['revision']})
    assert saved.status_code == 200, saved.text
    tested = client.post(root + '/test')
    assert tested.status_code == 200, tested.text
    assert client.post(root + '/publish').status_code == 200
    runtime = client.get(root + '/runtime').json()
    from app.services.delivery_examples import EXAMPLES
    assert len(runtime['relations']) == len(EXAMPLES[key]['relations'])
    findings = next(o for o in runtime['objects'] if o['label'] == '业务规则结果')
    rows = client.get(root + '/runtime/' + findings['id']).json()['rows']
    assert len(rows) == expected
    assert len({row[0] for row in rows}) == expected
    source_asset = db.get(Asset, project['config']['asset_ids'][0])
    connection = db.get(Connection, source_asset.connection_id)
    response = client.post(root + '/runtime/actions/' + runtime['actions'][0]['id'],
                           json={'params': {'finding_id': rows[0][0], 'note': '人工核验'}})
    assert response.status_code == 200 and response.json()['success'], response.text
    with sqlite3.connect(connection.database) as raw:
        assert raw.execute('SELECT note FROM review_log').fetchone()[0] == '人工核验'
        # Removing all source facts must remove obsolete inference output too.
        tables = [row[0] for row in raw.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'raw_%'")]
        for name in tables:
            raw.execute(f'DELETE FROM "{name}"')
    assert client.post(root + '/run-pipelines').status_code == 200
    assert client.get(root + '/runtime/' + findings['id']).json()['rows'] == []
    # Project publication does not switch the existing global active ontology.
    assert db.query(OntologyVersion).filter_by(is_active=True).one().name == '设备模型'
