"""Scene switching must scope lists, details, relationships and graph counts."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import OntologyEntity, EntityRelation, BusinessRule
from app.models.scene_registry import SceneRegistry
from app.models.version import OntologyVersion


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'scope.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine)
    with sessions() as db:
        db.add_all([
            OntologyEntity(id="d", name="Aircraft", name_cn="飞行器", tier=1, domain="drone"),
            OntologyEntity(id="s", name="Order", name_cn="订单", tier=1, domain="shopping"),
            SceneRegistry(id="drone", name="飞行", assets={"domains": ["drone"]}),
            SceneRegistry(id="shop", name="电商", assets={"object_classes": ["Order"]}),
            SceneRegistry(id="empty", name="空场景", assets={}),
            SceneRegistry(id="off", name="停用", status="disabled", assets={"domains": ["drone"]}),
        ])
        db.flush()
        db.add(EntityRelation(id="cross", from_entity_id="d", to_entity_id="s", name="cross", rel_type="has_one", cardinality="1:1"))
        db.add(BusinessRule(id="dr", entity_id="d", name="观测校验", condition_expr="true", action_desc="记录"))
        db.add(BusinessRule(id="sr", entity_id="s", name="订单校验", condition_expr="true", action_desc="记录"))
        db.add(OntologyVersion(id='dv', version_number=1, name='飞行草稿', scene_id='drone'))
        db.add(OntologyVersion(id='sv', version_number=2, name='电商草稿', scene_id='shop'))
        db.commit()
    monkeypatch.setattr('app.database.SessionLocal', sessions)
    from app.api.v1.entities import router as entities
    from app.api.v1.rules import router as rules
    from app.api.v1.studio import router as studio
    from app.api.v1.ontology_publish import router as versions
    app = FastAPI()
    for router in (entities, rules, studio, versions):
        app.include_router(router, prefix='/api/v1')
    with TestClient(app) as c:
        yield c
    engine.dispose()


def test_scene_switch_does_not_leak_between_sessions(client):
    for scene, expected in [('drone', ['d']), ('shop', ['s']), ('drone', ['d']), ('empty', [])]:
        response = client.get('/api/v1/entities', params={'scene_id': scene})
        assert response.status_code == 200, response.text
        assert [r['id'] for r in response.json()] == expected
    assert len(client.get('/api/v1/entities').json()) == 2


def test_scene_filters_relations_rules_graph_and_details(client):
    assert [r['id'] for r in client.get('/api/v1/rules?scene_id=drone').json()] == ['dr']
    graph = client.get('/api/v1/entities/graph?scene_id=drone').json()
    assert [n['id'] for n in graph['nodes']] == ['d']
    assert graph['edges'] == []
    assert client.get('/api/v1/entities/s?scene_id=drone').status_code == 404
    tbox = client.get('/api/v1/studio/tbox?scene_id=shop')
    assert tbox.status_code == 200
    assert 'Aircraft' not in tbox.text


@pytest.mark.parametrize('scene', ['missing', 'off'])
def test_invalid_scene_never_falls_back_to_all(client, scene):
    assert client.get('/api/v1/entities', params={'scene_id': scene}).status_code == 404


def test_new_version_keeps_scene_even_before_entities_are_added(client):
    assert [v['id'] for v in client.get('/api/v1/ontology-publish/versions?scene_id=drone').json()] == ['dv']
    assert client.get('/api/v1/ontology-publish/versions/sv?scene_id=drone').status_code == 404


def test_scene_publication_rejects_mixed_objects_and_preserves_other_scene(client):
    assert client.post('/api/v1/ontology-publish/versions/dv/entities', json={'entity_ids': ['s']}).status_code == 422
    assert client.post('/api/v1/ontology-publish/versions/dv/entities', json={'entity_ids': ['d']}).status_code == 200
    from app import database
    from app.api.v1.ontology_publish import approve_version
    with database.SessionLocal() as db:
        db.get(OntologyVersion, 'sv').is_active = True
        db.get(OntologyVersion, 'sv').status = 'published'
        db.get(OntologyEntity, 's').status = 'published'
        db.get(OntologyVersion, 'dv').status = 'pending_approval'
        db.commit()
        approve_version('dv', db, None)
        assert db.get(OntologyVersion, 'sv').is_active is True
        assert db.get(OntologyEntity, 's').status == 'published'
