from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from app.database import Base
from app.models import OntologyEntity, EntityRelation, Asset, ObjectBinding
from app.models.scene_registry import SceneRegistry
from app.models.demo_records import observation
from app.services.scene_demo import install_scene_demo
from app.services.scene_scope import install_scene_scope


def test_synthetic_demo_is_idempotent_and_separated(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'demo.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(OntologyEntity(id='existing', name='Existing', name_cn='保留对象', tier=1, domain='existing'))
        db.commit()
        assert install_scene_demo(db)['synthetic'] is True
        install_scene_demo(db)
        assert db.query(OntologyEntity).count() == 7
        assert db.query(SceneRegistry).count() == 2
        assert db.query(EntityRelation).count() == 4
        assert db.query(ObjectBinding).count() == 6
        assert db.scalar(select(func.count()).select_from(observation)) == 3
        asset = db.query(Asset).filter_by(name='demo_flight_observations').one()
        from app.services.data_plane.execute_service import ExecuteService, ExecuteRequest
        result = ExecuteService(db).execute(ExecuteRequest(asset_id=asset.id, sql='SELECT COUNT(*) AS n FROM <asset>', params={}, purpose='demo.query', bypass_cache=True))
        assert result.rows[0][0] == 3
    with Session(engine) as db:
        install_scene_scope(db, 'scene_demo_flight_demo')
        names = {e.name for e in db.query(OntologyEntity).all()}
        assert names == {'DemoFlightScenario', 'DemoAircraft', 'DemoFlightObservation'}
        assert db.query(Asset).count() == 3
    with Session(engine) as db:
        assert db.get(OntologyEntity, 'existing').name == 'Existing'
    engine.dispose()
