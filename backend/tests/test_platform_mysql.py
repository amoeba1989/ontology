"""Migration safety and optional real MySQL round-trip (MYSQL_TEST_URL)."""
import os
import json
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime

import pytest
from sqlalchemy import JSON, MetaData, create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from app.config import Settings
from app.db_engine import create_platform_engine, database_url
from app.database import Base
from app.models import OntologyEntity, EntityAttribute, EntityRelation
from app.models.system_config import SystemConfig
from app.models.monitor import ServiceMetric
from app.models.scene import AipSceneExecution
from app.services.platform_migration import backup_sqlite, migrate_platform, _digest


def test_model_registry_is_complete_in_a_fresh_migration_process():
    # Other tests import SystemConfig directly, which used to mask its absence
    # from the registry loaded by the standalone migration command.
    result = subprocess.run([sys.executable, "-c", """
import importlib, pkgutil
from app.database import Base
import app.models
registered = set(Base.metadata.tables)
for module in pkgutil.iter_modules(app.models.__path__):
    importlib.import_module('app.models.' + module.name)
missing = set(Base.metadata.tables) - registered
assert not missing, 'Missing model registrations: ' + ', '.join(sorted(missing))
assert 'system_config' in registered
"""], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_mysql_password_is_not_parsed_as_url_syntax():
    config = Settings(_env_file=None, DATABASE_BACKEND="mysql", MYSQL_HOST="localhost",
                      MYSQL_USER="test", MYSQL_PASSWORD="a@:/#%?", MYSQL_DATABASE="test")
    url = database_url(config)
    assert url.password == "a@:/#%?"
    assert url.drivername == "mysql+pymysql"
    assert "a@:/#%?" not in str(url)
    assert url.query["charset"] == "utf8mb4"


def test_missing_mysql_settings_fail_without_sqlite_fallback():
    with pytest.raises(ValueError, match="MYSQL_HOST"):
        create_platform_engine(Settings(_env_file=None, DATABASE_BACKEND="mysql"))


def test_digest_uses_json_numeric_semantics(tmp_path):
    left = create_engine(f"sqlite:///{tmp_path / 'left.db'}")
    right = create_engine(f"sqlite:///{tmp_path / 'right.db'}")
    try:
        for engine, payload in ((left, {"score": 1.0}), (right, {"score": 1})):
            with engine.begin() as conn:
                conn.exec_driver_sql("CREATE TABLE sample (id INTEGER PRIMARY KEY, payload JSON)")
                conn.exec_driver_sql("INSERT INTO sample VALUES (1, ?)", (json.dumps(payload),))
        left_table, right_table = MetaData(), MetaData()
        left_table.reflect(left); right_table.reflect(right)
        left_table.tables['sample'].c.payload.type = JSON()
        right_table.tables['sample'].c.payload.type = JSON()
        with left.connect() as lconn, right.connect() as rconn:
            assert _digest(lconn, left_table.tables['sample'], ['id', 'payload']) == _digest(
                rconn, right_table.tables['sample'], ['id', 'payload'])
    finally:
        left.dispose(); right.dispose()


def test_backup_is_consistent_and_never_overwritten(tmp_path):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as c:
        c.execute("CREATE TABLE t (v TEXT)")
        c.execute("INSERT INTO t VALUES ('原始数据')")
    backup = backup_sqlite(source, tmp_path / "backup.db")
    with sqlite3.connect(backup) as c:
        assert c.execute("SELECT v FROM t").fetchone()[0] == "原始数据"
    with pytest.raises(FileExistsError):
        backup_sqlite(source, backup)
    with pytest.raises(ValueError):
        backup_sqlite(tmp_path / "missing.db", tmp_path / "other.db")


@pytest.fixture(params=["sqlite", "mysql"])
def migration_pair(request, tmp_path):
    source = create_engine(f"sqlite:///{tmp_path / 'source.db'}")
    Base.metadata.create_all(source)
    admin = None
    schema = None
    if request.param == "mysql":
        if not os.environ.get("MYSQL_TEST_URL"):
            source.dispose()
            pytest.skip("Set MYSQL_TEST_URL to run real MySQL tests")
        url = make_url(os.environ["MYSQL_TEST_URL"])
        admin = create_engine(url.set(database=None))
        schema = "ontology_test_" + uuid.uuid4().hex[:12]
        with admin.begin() as c:
            c.execute(text(f"CREATE DATABASE `{schema}` CHARACTER SET utf8mb4"))
        target = create_engine(url.set(database=schema))
    else:
        target = create_engine(f"sqlite:///{tmp_path / 'target.db'}")
    try:
        yield source, target
    finally:
        source.dispose(); target.dispose()
        if admin:
            with admin.begin() as c:
                c.execute(text(f"DROP DATABASE `{schema}`"))
            admin.dispose()


def seed(source):
    with source.begin() as c:
        c.execute(OntologyEntity.__table__.insert(), [
            {"id": "a", "name": "Aircraft", "name_cn": "飞行器🛩", "tier": 1,
             "domain": "drone", "config_json": {"units": ["米"], "enabled": True}},
            {"id": "B", "name": "Observation", "name_cn": "观测", "tier": 2,
             "domain": "drone", "config_json": None},
        ])
        c.execute(EntityAttribute.__table__.insert(), {"id": "attr", "entity_id": "a",
                  "name": "identifier", "type": "string", "required": True})
        c.execute(EntityRelation.__table__.insert(), {"id": "rel", "from_entity_id": "a",
                  "to_entity_id": "B", "name": "hasObservation", "rel_type": "has_many", "cardinality": "1:N"})
        c.execute(SystemConfig.__table__.insert(), {"id": "cfg", "group": "basic", "key": "test",
                  "value": "中文配置" * 20000, "updated_at": datetime(2026, 10, 17, 1, 2, 3, 123456)})
        c.execute(ServiceMetric.__table__.insert(), {"service_name": "migration-test", "response_ms": 123.456789012345})
        c.execute(AipSceneExecution.__table__.insert(), {
            "id": "execution", "scene_id": "scene", "scene_name": "迁移测试", "scene_version": 1,
            "status": "success", "triggered_by": "manual",
            "trigger_payload": {"integer": 1, "whole_float": 1.0, "fraction": 1.25, "nested": [True, None, {"值": 0.0}]},
            "input_params": {}, "node_results": {"node": {"confidence": 0.8}},
            "final_output": {"score": 100.0}, "started_at": datetime(2026, 10, 17, 1, 2, 3, 123456),
            "finished_at": datetime(2026, 10, 17, 1, 2, 4, 654321), "duration_ms": 1531,
        })


def test_dry_run_and_verified_copy(migration_pair):
    source, target = migration_pair
    seed(source)
    assert migrate_platform(source, target, Base.metadata)["applied"] is False
    assert inspect(target).get_table_names() == []
    result = migrate_platform(source, target, Base.metadata, apply=True)
    assert result["rows"]["ontology_entities"] == 2
    with target.connect() as c:
        assert c.scalar(select(OntologyEntity.name_cn).where(OntologyEntity.id == "a")) == "飞行器🛩"
        assert c.scalar(select(SystemConfig.updated_at)).microsecond == 123456
        assert c.scalar(select(SystemConfig.value)) == "中文配置" * 20000
        assert c.scalar(select(ServiceMetric.response_ms)) == 123.456789012345
    with pytest.raises(ValueError, match="Target must be empty"):
        migrate_platform(source, target, Base.metadata, apply=True)


def test_unknown_source_table_is_not_silently_lost(migration_pair):
    source, target = migration_pair
    with source.begin() as c:
        c.execute(text("CREATE TABLE unknown_business_data (id INTEGER PRIMARY KEY)"))
    with pytest.raises(ValueError, match="Unmapped source tables"):
        migrate_platform(source, target, Base.metadata, apply=True)
    assert inspect(target).get_table_names() == []
