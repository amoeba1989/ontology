"""Install synthetic, independently scoped demonstrations without clearing user data."""
from datetime import datetime
from uuid import uuid5, NAMESPACE_URL
from sqlalchemy import select, func
from app.models import OntologyEntity, EntityAttribute, EntityRelation, BusinessRule, Connection, Asset, ObjectBinding
from app.models.scene_registry import SceneRegistry
from app.models import demo_records as records
from app.services.data_plane.lineage_service import LineageService


def sid(value):
    return str(uuid5(NAMESPACE_URL, 'ontology/scene-demo/v1/' + value))


DEFINITIONS = [
    ('flight_demo', 'DemoFlightScenario', '仿真运行', records.scenario),
    ('flight_demo', 'DemoAircraft', '飞行器', records.aircraft),
    ('flight_demo', 'DemoFlightObservation', '飞行观测', records.observation),
    ('commerce_demo', 'DemoCustomer', '演示客户', records.customer),
    ('commerce_demo', 'DemoProduct', '演示商品', records.product),
    ('commerce_demo', 'DemoOrder', '演示订单', records.order),
]


def install_scene_demo(db):
    engine = db.get_bind()
    for _, _, _, table in DEFINITIONS:
        table.create(engine, checkfirst=True)
    datasets = {
        records.scenario: [{'id': 'SIM-DEMO-001', 'name': '飞行观测合成样例'}],
        records.aircraft: [{'id': 'AIR-DEMO-001', 'name': '演示飞行器 A', 'model': '模拟四旋翼'}],
        records.observation: [
            {'id': f'OBS-DEMO-{i:03}', 'aircraft_id': 'AIR-DEMO-001', 'scenario_id': 'SIM-DEMO-001',
             'observed_at': datetime(2026, 1, 1, 0, 0, i), 'height_agl_m': 10.0 + i, 'speed_mps': 2.0 + i / 10}
            for i in range(1, 4)],
        records.customer: [{'id': 'CUST-DEMO-001', 'name': '合成客户 A'}],
        records.product: [{'id': 'PROD-DEMO-001', 'name': '演示商品 A', 'price': 25.5}],
        records.order: [{'id': 'ORDER-DEMO-001', 'customer_id': 'CUST-DEMO-001', 'product_id': 'PROD-DEMO-001', 'quantity': 2}],
    }
    for table, rows in datasets.items():
        for row in rows:
            if db.execute(select(table.c.id).where(table.c.id == row['id'])).first() is None:
                db.execute(table.insert().values(**row))
    connection_id = sid('connection')
    connection = db.get(Connection, connection_id)
    if not connection:
        if engine.dialect.name == 'mysql':
            url = engine.url
            connection = Connection(id=connection_id, name='新版演示 · MySQL 主库', category='database', type='mysql',
                host=url.host, port=url.port or 3306, database=url.database, credential_ref='platform://', credential_type='platform',
                writable=False, description='仅供合成演示数据查询，复用主库身份，不复制密码')
        elif engine.dialect.name == 'sqlite' and engine.url.database not in (None, ':memory:'):
            connection = Connection(id=connection_id, name='新版演示 · 本地主库', category='database', type='sqlite',
                database=engine.url.database, writable=False, description='合成演示数据查询')
        else:
            raise ValueError('Scene demo requires MySQL or a file-backed SQLite database')
        db.add(connection); db.flush()
    entities = {}
    for domain, name, label, table in DEFINITIONS:
        entity_id, asset_id = sid(name), sid(table.name)
        entity = db.get(OntologyEntity, entity_id)
        if not entity:
            entity = OntologyEntity(id=entity_id, name=name, name_cn=label, tier=2 if 'Observation' in name or name == 'DemoOrder' else 1,
                domain=domain, description='合成演示数据；不代表真实设备、人员或业务结果',
                config_json={'primary_key': 'id', 'synthetic': True, 'demo_version': 1})
            db.add(entity); db.flush()
            for col in table.c:
                kind = 'date' if col.name == 'observed_at' else 'number' if col.name in ('height_agl_m', 'speed_mps', 'price', 'quantity') else 'string'
                unit = {'height_agl_m': '米，明确为离地高度', 'speed_mps': '米/秒'}.get(col.name, '')
                db.add(EntityAttribute(id=sid(name + '/' + col.name), entity_id=entity.id, name=col.name,
                    type=kind, required=not col.nullable, description=unit or '合成演示字段',
                    source_table=table.name, source_field=col.name, data_status='已确认'))
            db.flush()
        entities[name] = entity
        asset = db.get(Asset, asset_id)
        if not asset:
            asset = Asset(id=asset_id, name=table.name, kind='table', domain=domain, connection_id=connection_id,
                locator={'table': table.name}, primary_key=['id'], tags=['synthetic', 'scene-demo-v1'], status='active',
                schema_snapshot=[{'name': c.name, 'type': str(c.type), 'nullable': c.nullable, 'is_pk': c.primary_key} for c in table.c],
                description='合成演示数据，不用于生产决策')
            db.add(asset)
        asset.profile = {'row_count': db.scalar(select(func.count()).select_from(table)), 'synthetic': True}
        binding_id = sid(name + '/binding')
        if not db.get(ObjectBinding, binding_id):
            db.add(ObjectBinding(id=binding_id, object_type_id=entity.id, asset_id=asset_id, role='primary', id_column='id',
                field_mappings=[{'attribute_id': a.id, 'source_column': a.name, 'transform': None} for a in entity.attributes], status='active'))
        db.flush()
        LineageService(db).upsert_binding(asset_id, entity.id, via_module='scene-demo')
    for source, target, column in [
        ('DemoFlightObservation', 'DemoAircraft', 'aircraft_id'), ('DemoFlightObservation', 'DemoFlightScenario', 'scenario_id'),
        ('DemoOrder', 'DemoCustomer', 'customer_id'), ('DemoOrder', 'DemoProduct', 'product_id')]:
        a, b = entities[source], entities[target]
        relation_id = sid(source + '/' + target)
        if not db.get(EntityRelation, relation_id):
            db.add(EntityRelation(id=relation_id, from_entity_id=a.id, to_entity_id=b.id, name='belongsTo' + target,
                name_cn='关联' + b.name_cn, rel_type='belongs_to', cardinality='N:1'))
            cfg = dict(a.config_json or {})
            cfg['relation_bindings'] = {**cfg.get('relation_bindings', {}), relation_id: {'source_column': column, 'target_column': 'id'}}
            a.config_json = cfg
    for domain, title in [('flight_demo', '飞行观测 · 新版演示'), ('commerce_demo', '电商订单 · 新版演示')]:
        scene_id = 'scene_demo_' + domain
        if not db.get(SceneRegistry, scene_id):
            db.add(SceneRegistry(id=scene_id, name=title, description='独立场景；全部记录均为合成演示数据',
                route='/browser', sort_order=-10 if domain == 'flight_demo' else -9,
                assets={'domains': [domain], 'object_classes': [name for d, name, _, _ in DEFINITIONS if d == domain]}))
        name = 'DemoFlightObservation' if domain == 'flight_demo' else 'DemoOrder'
        rule_id = sid(domain + '/rule')
        if not db.get(BusinessRule, rule_id):
            db.add(BusinessRule(id=rule_id, entity_id=entities[name].id, name='演示数据必填字段核验',
                condition_expr='id IS NOT NULL', action_desc='仅展示数据质量定义，不执行外部操作', status='draft', priority='low',
                rule_meta_json={'synthetic': True, 'execution': 'definition-only'}))
    db.commit()
    return {'scenes': 2, 'entities': 6, 'relations': 4, 'synthetic': True}
