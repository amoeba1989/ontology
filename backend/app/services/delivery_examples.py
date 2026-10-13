"""Synthetic, non-military fixtures. Constraints are explicit SQL rules, not a SWRL reasoner."""
from datetime import datetime
from pathlib import Path
import os
import sqlite3
from uuid import uuid4

from sqlalchemy import func

from app.models import (Asset, Connection, OntologyEntity, EntityAttribute, ObjectBinding,
                        OntologyVersion, OntologyVersionEntity, OntologyVersionAttribute,
                        EntityRelation, EntityAction, BusinessRule)
from app.models.delivery_project import DeliveryProject, DeliveryEvent
from app.models.pipeline import Pipeline, PipelineRun


def table(label, columns, rows):
    return {"label": label, "columns": columns.split(), "rows": rows}


EXAMPLES = {
    "health": {
        "name": "慢病健康管理", "goal": "用合成患者、检验和用药数据检验风险识别链路，输出供医生复核的风险清单。",
        "questions": "哪些用药组合存在配置的禁忌？哪些检验超出样例区间？是否存在药物过敏？",
        "boundary": "全部为虚构测试数据与规则。指标异常只作为支持证据，不构成诊断或处方建议。",
        "tables": {
            "patients": table("患者档案", "id name age allergy_drug", [("P1", " 合成患者一 ", 65, "D1"), ("P2", "合成患者二", 42, "")]),
            "diseases": table("疾病", "id name icd trigger_note", [("C1", "测试慢病", "DEMO-001", "仅用于链路测试")]),
            "symptoms": table("症状", "id name disease_id", [("S1", "测试症状", "C1")]),
            "labs": table("检验指标", "id name patient_id disease_id value low high measured_at", [("L1", "测试指标", "P1", "C1", 12.0, 3.0, 9.0, "2026-01-01T09:00:00Z"), ("L2", "测试指标", "P2", "C1", 6.0, 3.0, 9.0, "2026-01-01T09:00:00Z")]),
            "drugs": table("药物", "id name disease_id dose_note metabolism", [("D1", "测试药物A", "C1", "不用于实际处方", "模拟类型"), ("D2", "测试药物B", "C1", "不用于实际处方", "模拟类型")]),
            "contraindications": table("用药禁忌", "id name drug_id other_drug_id", [("CI1", "测试药物冲突", "D1", "D2")]),
            "prescriptions": table("用药记录", "id name patient_id drug_id", [("RX1", "模拟用药一", "P1", "D1"), ("RX2", "模拟用药二", "P1", "D2")]),
            "diagnoses": table("诊断记录", "id name patient_id disease_id", [("DX1", "既有测试诊断", "P1", "C1")]),
        },
        "relations": [("diseases", "symptoms", "hasSymptom", "id", "disease_id"), ("diseases", "labs", "reflectedBy", "id", "disease_id"),
                      ("patients", "diagnoses", "hasDiagnosis", "id", "patient_id"), ("diagnoses", "diseases", "diagnosisOf", "disease_id", "id"),
                      ("drugs", "diseases", "treats", "disease_id", "id"), ("drugs", "contraindications", "hasContraindication", "id", "drug_id"),
                      ("patients", "prescriptions", "takes", "id", "patient_id"), ("prescriptions", "drugs", "usesDrug", "drug_id", "id")],
        "rules": [
            ("用药冲突", "SELECT 'interaction-' || a.id || '-' || b.id AS id, '用药冲突' AS name, a.patient_id AS source_id, '配置的禁忌组合，需要医生复核' AS reason, 'review' AS level, 'pending' AS state FROM raw_prescriptions a JOIN raw_contraindications c ON a.drug_id=c.drug_id JOIN raw_prescriptions b ON b.patient_id=a.patient_id AND b.drug_id=c.other_drug_id"),
            ("指标异常证据", "SELECT 'lab-' || id, '指标异常', patient_id, '超出样例参考范围，非确诊结论', 'evidence', 'pending' FROM raw_labs WHERE value < low OR value > high"),
            ("过敏用药拦截提示", "SELECT 'allergy-' || p.id || '-' || r.id, '过敏禁忌', p.id, '与患者过敏记录匹配，禁止样例处方，待医生核查', 'blocked', 'pending' FROM raw_patients p JOIN raw_prescriptions r ON p.id=r.patient_id AND p.allergy_drug=r.drug_id"),
        ], "expected_findings": 3,
    },
    "library": {
        "name": "学术文献与知识主题", "goal": "通过合成文献检验主题检索、单向引用和作者研究方向关联。",
        "questions": "大模型本体建模有哪些相关文献？哪些文献引用了谁？同一作者的研究主题如何聚合？",
        "boundary": "相同主题计数是本样例的聚类基线，不代表语义相似度模型。上位主题检索包含下位主题文献；不把所有上位文献自动归入每个子主题。",
        "tables": {
            "papers": table("文献", "id name author_id topic_id journal_id year doi keywords", [("P1", " 本体与大模型 ", "A1", "T2", "J1", 2025, "demo:paper1", "本体 大模型"), ("P2", "本体辅助检索", "A1", "T2", "J1", 2026, "demo:paper2", "本体 检索"), ("P3", "材料分析", "A2", "T3", "J1", 2024, "demo:paper3", "材料")]),
            "authors": table("作者", "id name topic_id", [("A1", "测试作者一", "T2"), ("A2", "测试作者二", "T3")]),
            "topics": table("研究主题", "id name parent_id", [("T1", "人工智能", ""), ("T2", "大模型本体建模", "T1"), ("T3", "材料学", "")]),
            "datasets": table("数据集", "id name paper_id", [("DS1", "合成研究数据", "P1")]),
            "journals": table("期刊", "id name quartile index_name", [("J1", "测试期刊", "DEMO", "模拟收录库")]),
            "citations": table("参考文献关系", "id name paper_id cited_id", [("R1", "P2引用P1", "P2", "P1")]),
        },
        "relations": [("papers", "authors", "authoredBy", "author_id", "id"), ("papers", "topics", "coversTopic", "topic_id", "id"),
                      ("papers", "citations", "hasReference", "id", "paper_id"), ("citations", "papers", "cites", "cited_id", "id"),
                      ("papers", "datasets", "uses", "id", "paper_id"), ("authors", "topics", "specializeIn", "topic_id", "id"),
                      ("topics", "topics", "subTopicOf", "parent_id", "id")],
        "rules": [
            ("上位主题包含下位文献", "SELECT 'topic-' || p.id AS id, '主题检索命中' AS name, p.id AS source_id, '下位主题文献纳入上位主题检索' AS reason, 'info' AS level, 'pending' AS state FROM raw_papers p JOIN raw_topics t ON p.topic_id=t.id WHERE t.id='T1' OR t.parent_id='T1'"),
            ("引用仅按原方向展开", "SELECT 'cite-' || id, '单向引用', paper_id, paper_id || ' cites ' || cited_id, 'info', 'pending' FROM raw_citations"),
            ("同作者同主题聚合", "SELECT 'cluster-' || author_id || '-' || topic_id, '研究方向聚类', author_id, '同主题文献数=' || COUNT(*), 'info', 'pending' FROM raw_papers GROUP BY author_id, topic_id HAVING COUNT(*) >= 2"),
        ], "expected_findings": 4,
    },
    "bim": {
        "name": "建筑 BIM 运维", "goal": "用简化建筑数据验证空间关联、维保到期、材料寿命和包围盒碰撞检查。",
        "questions": "哪些设备和材料到期？哪些构件包围盒重叠？设备故障影响哪些相连空间？",
        "boundary": "使用简化坐标和轴对齐包围盒，不等同于 IFC 精确碰撞。影响范围限定为本房间及一跳连通空间，是测试假设。",
        "tables": {
            "buildings": table("建筑", "id name", [("B1", " 测试办公楼 ")]),
            "floors": table("楼层", "id name building_id", [("F1", "一层", "B1")]),
            "rooms": table("房间空间", "id name floor_id", [("R1", "机房", "F1"), ("R2", "走廊", "F1"), ("R3", "独立办公室", "F1")]),
            "components": table("建筑构件", "id name material_id x1 y1 z1 x2 y2 z2 fire_rating", [("C1", "梁一", "M1", 0, 0, 0, 2, 2, 2, "样例A级"), ("C2", "管道一", "M1", 1, 1, 1, 3, 3, 3, "样例A级"), ("C3", "构件三", "M2", 4, 4, 4, 5, 5, 5, "样例B级")]),
            "equipment": table("机电设备", "id name room_id maintenance_days days_since_service status rated_power", [("E1", "测试空调", "R1", 90, 100, "fault", 3.5), ("E2", "测试风机", "R3", 90, 20, "normal", 1.5)]),
            "workorders": table("运维工单", "id name equipment_id state", [("W1", "测试巡检", "E2", "open")]),
            "materials": table("建材", "id name life_years used_years fire_rating", [("M1", "测试材料一", 10, 11, "A级"), ("M2", "测试材料二", 20, 5, "B级")]),
            "room_links": table("空间连通", "id name from_room to_room", [("RL1", "机房连接走廊", "R1", "R2")]),
        },
        "relations": [("buildings", "floors", "containsFloor", "id", "building_id"), ("floors", "rooms", "containsRoom", "id", "floor_id"),
                      ("rooms", "equipment", "hosts", "id", "room_id"), ("components", "materials", "madeOf", "material_id", "id"),
                      ("workorders", "equipment", "maintain", "equipment_id", "id")],
        "rules": [
            ("维保到期", "SELECT 'maintenance-' || id AS id, '维保到期' AS name, id AS source_id, '达到样例维保周期，建议生成工单' AS reason, 'warning' AS level, 'pending' AS state FROM raw_equipment WHERE days_since_service >= maintenance_days"),
            ("材料寿命到期", "SELECT 'material-' || id, '材料到期', id, '使用年限达到材料寿命', 'warning', 'pending' FROM raw_materials WHERE used_years >= life_years"),
            ("包围盒重叠", "SELECT 'collision-' || a.id || '-' || b.id, '构件碰撞', a.id, a.id || ' overlaps ' || b.id, 'warning', 'pending' FROM raw_components a JOIN raw_components b ON a.id < b.id AND a.x1 < b.x2 AND b.x1 < a.x2 AND a.y1 < b.y2 AND b.y1 < a.y2 AND a.z1 < b.z2 AND b.z1 < a.z2"),
            ("故障空间影响", "SELECT 'impact-' || e.id || '-' || r.id, '空间影响', r.id, '故障设备=' || e.id, 'warning', 'pending' FROM raw_equipment e JOIN raw_rooms r ON r.id=e.room_id OR r.id IN (SELECT l.to_room FROM raw_room_links l WHERE l.from_room=e.room_id) OR r.id IN (SELECT l.from_room FROM raw_room_links l WHERE l.to_room=e.room_id) WHERE e.status='fault'"),
        ], "expected_findings": 5,
    },
    "supply": {
        "name": "电商供应链", "goal": "统一商品、库存和物流数据，验证库存缺口、供应依赖与订单发货条件。",
        "questions": "哪些 SKU 低于安全库存？订单是否有足够库存和可用物流？供应商产能能否补足缺口？",
        "boundary": "库存缺口与发货规则为本次验收补充的样例规则，未接入真实订单或供应商系统。",
        "tables": {
            "products": table("商品", "id name", [("P1", " 测试商品 ")]),
            "skus": table("SKU", "id name product_id supplier_id specification safety_stock", [("S1", "规格一", "P1", "SUP1", "红色", 10), ("S2", "规格二", "P1", "SUP1", "蓝色", 5)]),
            "warehouses": table("仓库", "id name address capacity", [("WH1", "测试仓", "合成地址", 1000)]),
            "inventory": table("库存记录", "id name sku_id warehouse_id quantity reserved", [("I1", "规格一库存", "S1", "WH1", 8, 3), ("I2", "规格二库存", "S2", "WH1", 20, 0)]),
            "suppliers": table("供应商", "id name lead_days capacity", [("SUP1", "测试供应商", 7, 4)]),
            "routes": table("物流线路", "id name warehouse_id destination active", [("LR1", "测试线路", "WH1", "CITY1", 1)]),
            "orders": table("订单", "id name sku_id warehouse_id quantity destination state", [("O1", "测试订单一", "S1", "WH1", 6, "CITY1", "open"), ("O2", "测试订单二", "S2", "WH1", 2, "CITY2", "open")]),
        },
        "relations": [("products", "skus", "hasSku", "id", "product_id"), ("skus", "inventory", "hasInventory", "id", "sku_id"),
                      ("inventory", "warehouses", "storedAt", "warehouse_id", "id"), ("skus", "suppliers", "suppliedBy", "supplier_id", "id"),
                      ("orders", "skus", "contains", "sku_id", "id"), ("warehouses", "routes", "connectedBy", "id", "warehouse_id")],
        "rules": [
            ("安全库存缺口", "SELECT 'stock-' || i.id AS id, '安全库存不足' AS name, i.sku_id AS source_id, '缺口=' || (s.safety_stock-(i.quantity-i.reserved)) AS reason, 'warning' AS level, 'pending' AS state FROM raw_inventory i JOIN raw_skus s ON s.id=i.sku_id WHERE i.quantity-i.reserved < s.safety_stock"),
            ("订单库存不足", "SELECT 'order-' || o.id, '订单库存不足', o.id, '可用库存小于订单需求', 'blocked', 'pending' FROM raw_orders o JOIN raw_inventory i ON o.sku_id=i.sku_id AND o.warehouse_id=i.warehouse_id WHERE o.quantity > i.quantity-i.reserved"),
            ("物流不可达", "SELECT 'route-' || o.id, '无可用物流', o.id, '目标城市无启用线路', 'blocked', 'pending' FROM raw_orders o WHERE NOT EXISTS (SELECT 1 FROM raw_routes r WHERE r.warehouse_id=o.warehouse_id AND r.destination=o.destination AND r.active=1)"),
            ("供应产能不足", "SELECT 'capacity-' || s.id, '补货产能不足', s.id, '供应商产能不足以补足安全库存', 'warning', 'pending' FROM raw_skus s JOIN raw_inventory i ON s.id=i.sku_id JOIN raw_suppliers v ON s.supplier_id=v.id WHERE s.safety_stock-(i.quantity-i.reserved) > v.capacity"),
        ], "expected_findings": 4,
    },
}


def create_example(db, user, key):
    """Each click creates an isolated source database and editable project; never touches production sources."""
    spec = EXAMPLES[key]
    token = uuid4().hex[:12]
    directory = Path(os.environ.get("DEMO_DB_DIR", "./data")) / "delivery-examples"
    directory.mkdir(parents=True, exist_ok=True)
    path = (directory / f"{key}-{token}.db").resolve()
    conn = Connection(name=f"验收/{spec['name']}/{token}", type="sqlite", database=str(path), writable=True,
                      rate_limit_qps=1000, created_by=user.id, description="独立合成验收数据")
    db.add(conn); db.flush()
    source_ids, output_ids, entity_ids, pipeline_ids, entity_by_table = [], [], [], [], {}
    schemas = {}
    with sqlite3.connect(path) as raw:
        for name, t in spec["tables"].items():
            types = ["REAL" if isinstance(v, float) else "INTEGER" if isinstance(v, int) else "TEXT" for v in t["rows"][0]]
            schemas[name] = [(column, typ) for column, typ in zip(t["columns"], types)]
            ddl = ', '.join(f'"{column}" {typ}' + (' PRIMARY KEY' if column == 'id' else '') for column, typ in schemas[name])
            raw.execute(f'CREATE TABLE "raw_{name}" ({ddl})')
            raw.execute(f'CREATE TABLE "obj_{name}" ({ddl})')
            raw.executemany(f'INSERT INTO "raw_{name}" VALUES ({",".join("?" for _ in types)})', t["rows"])
        raw.execute('CREATE TABLE obj_findings (id TEXT PRIMARY KEY, name TEXT, source_id TEXT, reason TEXT, level TEXT, state TEXT)')
        raw.execute('CREATE TABLE review_log (id INTEGER PRIMARY KEY AUTOINCREMENT, finding_id TEXT, note TEXT)')
    for name, t in spec["tables"].items():
        schema = [{"name": col, "type": typ.lower(), "is_pk": col == 'id'} for col, typ in schemas[name]]
        source = Asset(name=f"{spec['name']} · 源/{t['label']} · {token}", kind="table", connection_id=conn.id,
                       locator={"table": f"raw_{name}"}, schema_snapshot=schema, primary_key=['id'], tags=['delivery-example', key])
        db.add(source); db.flush(); source_ids.append(source.id)
    # Every modeled class is backed by the result of a real pipeline.
    definitions = [(name, t['label'], schemas[name], f'SELECT ' + ', '.join('TRIM(name) AS name' if c == 'name' else c for c in t['columns']) + f' FROM raw_{name}')
                   for name, t in spec['tables'].items()]
    definitions.append(('findings', '业务规则结果', [(c, 'TEXT') for c in ['id', 'name', 'source_id', 'reason', 'level', 'state']],
                        ' UNION ALL '.join(sql for _, sql in spec['rules'])))
    for name, label, columns, query in definitions:
        schema = [{"name": col, "type": typ.lower(), "is_pk": col == 'id'} for col, typ in columns]
        asset = Asset(name=f"{spec['name']} · 结果/{label} · {token}", kind='table', connection_id=conn.id,
                      locator={'table': f'obj_{name}'}, schema_snapshot=schema, primary_key=['id'], tags=['delivery-example', key])
        entity = OntologyEntity(name=f"Example_{key}_{name}_{token}", name_cn=label, tier=1 if name != 'findings' else 3,
                                description=f"{spec['name']}合成验收对象", config_json={'primary_key': 'id'}, status='active')
        db.add_all([asset, entity]); db.flush()
        attrs = [EntityAttribute(entity_id=entity.id, name=col, type='number' if typ in ('REAL', 'INTEGER') else 'string',
                                 required=col == 'id', description=col, source_table=f'obj_{name}',
                                 source_field=col, data_status='已确认来源') for col, typ in columns]
        db.add_all(attrs); db.flush()
        db.add(ObjectBinding(object_type_id=entity.id, asset_id=asset.id, role='primary', id_column='id', created_by=user.id,
                             field_mappings=[{'attribute_id': a.id, 'source_column': a.name} for a in attrs]))
        pipeline = Pipeline(name=f"{spec['name']} / {label} / {token}", steps=['读取合成源数据', '标准化与规则计算', '按主键更新结果'],
                            engine='real', config_json={'source': {'connection_id': conn.id, 'query': query},
                                'target': {'connection_id': conn.id, 'table': f'obj_{name}', 'write_mode': 'truncate_insert'}})
        db.add(pipeline); db.flush()
        output_ids.append(asset.id); entity_ids.append(entity.id); pipeline_ids.append(pipeline.id); entity_by_table[name] = entity
    for source, target, predicate, source_key, target_key in spec['relations']:
        db.add(EntityRelation(name=predicate, from_entity_id=entity_by_table[source].id, to_entity_id=entity_by_table[target].id,
                              rel_type='association', cardinality='N:N',
                              description=f"有向关系：{source}.{source_key} = {target}.{target_key}"))
    for name, sql in spec['rules']:
        db.add(BusinessRule(entity_id=entity_by_table['findings'].id, name=name, condition_expr=sql, action_desc='输出可追溯规则结果',
                            description=spec['boundary'], rule_meta_json={'engine': 'sql', 'example': key}))
    action = EntityAction(name=f"{spec['name']}：记录人工复核", entity_id=entity_by_table['findings'].id, category='domain',
                          action_type='sql_exec', type_config={'connection_id': conn.id,
                            'sql': 'INSERT INTO review_log (finding_id, note) SELECT :finding_id, :note WHERE EXISTS (SELECT 1 FROM obj_findings WHERE id=:finding_id) RETURNING id, finding_id, note'},
                          parameters_json=[{'name': 'finding_id', 'type': 'string', 'required': True, 'description': '规则结果编号'}, {'name': 'note', 'type': 'string', 'required': True, 'description': '复核说明'}])
    db.add(action); db.flush()
    project = DeliveryProject(owner_id=user.id, name=f"{spec['name']} · 验收样例", config={
        'goal': spec['goal'], 'audience': '业务验收人员', 'questions': spec['questions'],
        'expected_actions': '对规则结果记录人工复核，写入独立样例数据库',
        'acceptance': f"初始规则结果 {spec['expected_findings']} 条；重跑不重复；源数据变化可更新；人工复核可追溯。\n{spec['boundary']}",
        'asset_ids': source_ids, 'pipeline_ids': pipeline_ids, 'output_asset_ids': output_ids,
        'entity_ids': entity_ids, 'action_ids': [action.id], 'processing_mode': 'pipeline',
        'processing_note': '真实 SQL 清洗名称、关联源表并计算业务约束，输出表使用全量替换。仅作用于独立样例库。',
        'version_id': None, 'acceptance_evidence': '', 'example_key': key,
    })
    db.add(project); db.flush()
    db.add(DeliveryEvent(project_id=project.id, revision=1, kind='example', status='success', message='已创建独立合成数据、模型、约束和真实管道；等待运行与发布'))
    db.commit()
    return project
