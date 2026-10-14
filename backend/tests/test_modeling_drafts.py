"""Persistence, review gates, AI contract, isolation and incremental migrations."""
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import Session
from app.database import Base, get_db
from app.core.deps import require_user
from app.models import User, OntologyEntity, BusinessRule
from app.models.modeling_draft import ModelingDraft
from app.api.v1.modeling_drafts import router
from app.schemas.modeling_draft import DraftContent, DraftRule
from app.services.modeling_draft import drone_template, evaluate_constraint, generate_proposal
from app.services.modeling_draft import test_rule as check_samples
from app.services.db_migrations import upgrade_incremental_schema


@pytest.fixture
def workspace(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    upgrade_incremental_schema(engine)
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)
    user = User(id="owner", username="owner", name="测试", password_hash="test", role="editor", is_active=True)
    db.add(user); db.commit()
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_user] = lambda: user
    with TestClient(app) as client:
        yield client, db, app
    db.close(); engine.dispose()


def create(client, content=None):
    response = client.post('/modeling-drafts', json={"name": "无人机观测", "scenario": "验证观测数据", "content": content or drone_template()})
    assert response.status_code == 201, response.text
    return response.json()


def save(client, draft):
    return client.put(f"/modeling-drafts/{draft['id']}", json={k: draft[k] for k in ('name', 'scenario', 'content', 'revision')})


def accept(client, draft):
    draft['content']['rules'][0]['confirmed'] = True
    response = save(client, draft)
    assert response.status_code == 200, response.text
    draft = response.json()
    response = client.post(f"/modeling-drafts/{draft['id']}/review", json={"revision": draft['revision'], "rule_ids": ['agl-nonnegative'], "decision": "accepted"})
    assert response.status_code == 200, response.text
    return response.json()


def test_persistent_draft_review_materialize_and_idempotence(workspace):
    client, db, _ = workspace
    draft = create(client)
    root = f"/modeling-drafts/{draft['id']}"
    db.expire_all()
    assert client.get(root).json()['content'] == draft['content']
    assert client.post(root + '/materialize', json={'revision': 1}).status_code == 422
    review = {'revision': 1, 'rule_ids': ['agl-nonnegative'], 'decision': 'accepted'}
    assert client.post(root + '/review', json=review).status_code == 422
    result = client.post(root + '/test-rules', json={'revision': 1}).json()
    assert result['results'][0]['passed'] is True
    draft = accept(client, draft)
    response = client.post(root + '/materialize', json={'revision': draft['revision']})
    assert response.status_code == 200, response.text
    imported = response.json()
    assert len(imported['materialized']['entity_ids']) == 3
    rule = db.get(BusinessRule, imported['materialized']['rule_ids'][0])
    assert rule.status == 'draft'
    assert rule.rule_meta_json['definition']['assumptions']
    assert client.post(root + '/materialize', json={'revision': draft['revision']}).json()['materialized'] == imported['materialized']
    assert db.query(OntologyEntity).count() == 3
    assert save(client, imported).status_code == 409
    assert any(e['kind'] == 'materialized' for e in client.get(root + '/events').json())


@pytest.mark.parametrize('change', ['threshold', 'unit', 'scenario'])
def test_edit_requires_review_again_and_stale_update_rejected(workspace, change):
    client, _, _ = workspace
    draft = accept(client, create(client))
    stale = deepcopy(draft)
    if change == 'threshold':
        draft['content']['rules'][0]['clauses'][0]['value'] = 10
    elif change == 'unit':
        draft['content']['entities'][0]['attributes'][-1]['unit'] = '英尺'
    else:
        draft['scenario'] = '新的适用场景'
    response = save(client, draft)
    assert response.status_code == 200, response.text
    rule = response.json()['content']['rules'][0]
    assert rule['status'] == 'pending' and rule['confirmed'] is False
    assert save(client, stale).status_code == 409


def test_cannot_forge_approval_and_no_permission_leak(workspace):
    client, _, app = workspace
    content = drone_template()
    content['rules'][0].update(status='accepted', confirmed=True)
    draft = create(client, content)
    assert draft['content']['rules'][0]['status'] == 'pending'
    app.dependency_overrides[require_user] = lambda: User(id='other', role='editor', is_active=True)
    assert client.get(f"/modeling-drafts/{draft['id']}").status_code == 404
    assert client.get('/modeling-drafts').json() == []
    app.dependency_overrides[require_user] = lambda: User(id='owner', role='viewer', is_active=True)
    assert client.get('/modeling-drafts').status_code == 403


def test_import_collision_rolls_back_and_reuse_avoids_duplicates(workspace):
    client, db, _ = workspace
    content = drone_template(); content['rules'] = []
    first = create(client, content)
    assert client.post(f"/modeling-drafts/{first['id']}/materialize", json={'revision': 1}).status_code == 200
    # First object would be new, second conflicts; transaction must roll back both revision and creation.
    content['entities'][0]['name'] = 'SecondAircraft'
    content['relations'][0]['source'] = 'SecondAircraft'
    second = create(client, content)
    root = f"/modeling-drafts/{second['id']}"
    assert client.post(root + '/materialize', json={'revision': 1}).status_code == 409
    assert db.query(OntologyEntity).count() == 3
    assert client.get(root).json()['revision'] == 1
    original = drone_template(); original['rules'] = []
    existing = {e.name: e.id for e in db.query(OntologyEntity).all()}
    for e in original['entities']:
        e['reuse_id'] = existing[e['name']]
    third = create(client, original)
    assert client.post(f"/modeling-drafts/{third['id']}/materialize", json={'revision': 1}).status_code == 200
    assert db.query(OntologyEntity).count() == 3


@pytest.mark.parametrize('value,valid', [(0, True), (-1, False), (None, False), ('30', False), (True, False)])
def test_numeric_constraints_do_not_coerce_missing_strings_or_booleans(value, valid):
    rule = DraftRule.model_validate(drone_template()['rules'][0])
    assert evaluate_constraint(rule, {'height_agl': value})['valid'] is valid
    rule.examples = rule.examples[:1]
    assert not check_samples(rule)['passed']


def test_ai_proposal_is_separate_until_explicit_apply(workspace, monkeypatch):
    client, db, _ = workspace
    from app.services import llm_resolver
    from app.api.v1 import modeling_drafts as api
    monkeypatch.setattr(llm_resolver, '_resolve_model_from_db', lambda *a: {'api_key': 'test', 'base_url': 'http://local.test/v1', 'model': 'test-model'})
    provider = Mock()
    provider.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content=json.dumps(drone_template())))])
    monkeypatch.setattr(api, 'generate_proposal', lambda db, draft: generate_proposal(db, draft, client=provider))
    draft = create(client, {'entities': [], 'relations': [], 'rules': [], 'questions': []})
    root = f"/modeling-drafts/{draft['id']}"
    response = client.post(root + '/generate', json={'revision': 1})
    assert response.status_code == 200, response.text
    proposed = response.json()
    assert not proposed['content']['entities']
    assert proposed['proposal']['content']['rules'][0]['origin'] == 'ai'
    assert provider.chat.completions.create.call_args.kwargs['response_format'] == {'type': 'json_object'}
    applied = client.post(root + '/apply-proposal', json={'revision': proposed['revision']})
    assert applied.status_code == 200 and len(applied.json()['content']['entities']) == 3
    assert client.post(root + '/apply-proposal', json={'revision': applied.json()['revision']}).status_code == 409
    provider.chat.completions.create.return_value.choices[0].message.content = '{bad json'
    before = client.get(root).json()
    assert client.post(root + '/generate', json={'revision': before['revision']}).status_code == 422
    assert client.get(root).json() == before


def test_invalid_references_rejected_before_storage(workspace):
    client, db, _ = workspace
    content = drone_template(); content['rules'][0]['clauses'][0]['field'] = 'not_an_attribute'
    assert client.post('/modeling-drafts', json={'name': 'bad', 'content': content}).status_code == 422
    assert db.query(ModelingDraft).count() == 0


def test_unbound_draft_rules_cannot_report_successful_execution(workspace):
    client, db, app = workspace
    from app.api.v1.rules import router as rules_router
    from app.core.deps import get_current_user
    from app.services.rule_engine import RuleEvaluator, RuleScreener
    app.include_router(rules_router)
    app.dependency_overrides[get_current_user] = app.dependency_overrides[require_user]
    draft = accept(client, create(client))
    imported = client.post(f"/modeling-drafts/{draft['id']}/materialize", json={'revision': draft['revision']}).json()
    rid = imported['materialized']['rule_ids'][0]
    assert client.post(f'/rules/{rid}/execute').status_code == 409
    assert client.put(f'/rules/{rid}', json={'status': 'active'}).status_code == 409
    rule = db.get(BusinessRule, rid)
    assert rule.trigger_count == 0
    with pytest.raises(ValueError, match='样例验证'):
        RuleEvaluator(db).evaluate(rule, 'test')
    assert RuleScreener(db).screen(rule)['error']


def test_admin_bootstrap_preserves_existing_password(workspace, monkeypatch):
    _, db, _ = workspace
    from app.api.v1.auth import seed_admin
    from app.core.security import verify_password
    monkeypatch.setenv('BOOTSTRAP_ADMIN_PASSWORD', 'Initial-Test-Password')
    seed_admin(db)
    user = db.query(User).filter_by(username='admin').one()
    assert verify_password('Initial-Test-Password', user.password_hash)
    original_hash = user.password_hash
    monkeypatch.setenv('BOOTSTRAP_ADMIN_PASSWORD', 'Different-Test-Password')
    seed_admin(db)
    assert user.password_hash == original_hash


def test_incremental_migration_preserves_legacy_data_and_is_repeatable(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE legacy_data (id INTEGER PRIMARY KEY, value TEXT)'))
        conn.execute(text("INSERT INTO legacy_data VALUES (1, 'keep')"))
    upgrade_incremental_schema(engine)
    upgrade_incremental_schema(engine)
    assert {'modeling_drafts', 'modeling_draft_events', 'alembic_version'} <= set(inspect(engine).get_table_names())
    with engine.connect() as conn:
        assert conn.execute(text('SELECT value FROM legacy_data')).scalar() == 'keep'
        assert conn.execute(text('SELECT version_num FROM alembic_version')).scalar() == '0001_modeling_drafts'
    engine.dispose()
