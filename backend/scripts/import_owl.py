"""通用 OWL 场景本体导入脚本（幂等）。

用法：
    cd backend
    python scripts/import_owl.py --file ../owl/e-commerce-ontology.owl --domain shopping

幂等策略（parse_owl_ontology 已对实体按 name、属性按 (实体,名称)、关系按 (from,to,name) 全量去重）：
- 首次导入：解析新建全部实体/属性/关系 + 语义补齐
- 混合场景（部分实体已存在，如电商复用已发布的 Product/Order）：已存在的实体/属性被跳过，
  仅新建缺失项，可安全重跑，不会使属性翻倍
- 全部已存在：解析全部跳过，仅执行 enrich（幂等）

语义补齐：parse_owl_ontology 表达不了 tier / primary_key / required / enum / 真实基数，
由 SCENE_CONFIG[domain] 确定性补齐。新增场景时在 SCENE_CONFIG 增加配置即可。
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm.attributes import flag_modified  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models.entity import OntologyEntity, EntityAttribute  # noqa: E402
from app.models.relation import EntityRelation  # noqa: E402
from app.services.file_import import parse_owl_ontology  # noqa: E402

# ── 场景语义配置 ──────────────────────────────────────────────
# tiers: 实体名 → tier；primary_keys: 实体名 → 主键属性；
# required: (实体名, 属性名) 列表；enums: (实体名, 属性名) → {enumValues, enumLabels}；
# relations: 关系名 → 基数。

SCENE_CONFIG = {
    "shopping": {
        # T3 实体改名为 OrderRiskAssessment / FraudWarningEvent，避让无人机场景占用的
        # RiskAssessment / WarningEvent（OntologyEntity.name 全局唯一）。
        # Product / Order 复用库内已发布对象，属性名与其既有实名对齐（user_id/product_ids/
        # total_amount/status/created_at 等），不新增同名冲突属性。
        "tiers": {
            "Customer": 1, "Product": 1, "Order": 1,
            "CartItem": 2, "PaymentTransaction": 2, "Coupon": 2,
            "OrderRiskAssessment": 3, "FraudWarningEvent": 3,
        },
        "primary_keys": {
            "Customer": "customer_id", "Product": "product_id", "Order": "order_id",
            "CartItem": "cart_item_id", "PaymentTransaction": "txn_id", "Coupon": "coupon_id",
            "OrderRiskAssessment": "assessment_id", "FraudWarningEvent": "event_id",
        },
        "required": [
            ("Customer", "customer_id"), ("Customer", "customer_name"), ("Customer", "member_level"),
            ("Product", "product_id"), ("Product", "product_name"), ("Product", "price"),
            ("Order", "order_id"), ("Order", "user_id"), ("Order", "product_ids"),
            ("Order", "total_amount"), ("Order", "status"), ("Order", "created_at"),
            ("CartItem", "cart_item_id"), ("CartItem", "cart_customer_id"), ("CartItem", "cart_product_id"), ("CartItem", "quantity"),
            ("PaymentTransaction", "txn_id"), ("PaymentTransaction", "txn_order_id"),
            ("PaymentTransaction", "pay_method"), ("PaymentTransaction", "txn_amount"), ("PaymentTransaction", "pay_status"),
            ("Coupon", "coupon_id"), ("Coupon", "coupon_name"), ("Coupon", "discount_type"), ("Coupon", "discount_value"),
            ("OrderRiskAssessment", "assessment_id"), ("OrderRiskAssessment", "assessment_order_id"),
            ("FraudWarningEvent", "event_id"), ("FraudWarningEvent", "event_assessment_id"),
        ],
        "enums": {
            ("Customer", "member_level"): {
                "enumValues": ["normal", "silver", "gold", "vip"],
                "enumLabels": ["普通", "银卡", "金卡", "VIP"],
            },
            ("Product", "category"): {
                "enumValues": ["electronics", "clothing", "food", "home"],
                "enumLabels": ["数码", "服饰", "食品", "家居"],
            },
            ("Product", "status"): {
                "enumValues": ["on_sale", "off_sale", "discontinued"],
                "enumLabels": ["在售", "下架", "停产"],
            },
            ("Order", "status"): {
                "enumValues": ["pending", "paid", "shipped", "delivered", "cancelled"],
                "enumLabels": ["待支付", "已支付", "已发货", "已收货", "已取消"],
            },
            ("Order", "risk_flag"): {
                "enumValues": ["none", "suspicious", "confirmed_fraud"],
                "enumLabels": ["无", "可疑", "确认欺诈"],
            },
            ("Order", "channel"): {
                "enumValues": ["app", "web", "store"],
                "enumLabels": ["APP", "网页", "门店"],
            },
            ("Order", "pay_method"): {
                "enumValues": ["alipay", "wechat", "card", "cod"],
                "enumLabels": ["支付宝", "微信", "银行卡", "货到付款"],
            },
            ("PaymentTransaction", "pay_method"): {
                "enumValues": ["alipay", "wechat", "card", "cod"],
                "enumLabels": ["支付宝", "微信", "银行卡", "货到付款"],
            },
            ("PaymentTransaction", "pay_status"): {
                "enumValues": ["initiated", "success", "failed", "refunded"],
                "enumLabels": ["已发起", "成功", "失败", "已退款"],
            },
            ("Coupon", "discount_type"): {
                "enumValues": ["fixed", "percent"],
                "enumLabels": ["立减", "折扣"],
            },
            ("Coupon", "coupon_status"): {
                "enumValues": ["active", "used", "expired"],
                "enumLabels": ["可用", "已核销", "已过期"],
            },
            ("OrderRiskAssessment", "risk_level"): {
                "enumValues": ["low", "medium", "high", "critical"],
                "enumLabels": ["低", "中", "高", "严重"],
            },
            ("FraudWarningEvent", "warning_type"): {
                "enumValues": ["high_amount", "fraud_pattern", "device_abuse", "coupon_abuse"],
                "enumLabels": ["高额订单", "欺诈模式", "设备滥用", "优惠券滥用"],
            },
            ("FraudWarningEvent", "priority"): {
                "enumValues": ["p1", "p2", "p3"],
                "enumLabels": ["紧急", "重要", "一般"],
            },
            ("FraudWarningEvent", "event_status"): {
                "enumValues": ["open", "processing", "resolved", "false_positive"],
                "enumLabels": ["待处置", "处置中", "已解决", "误报关闭"],
            },
        },
        "relations": {
            "customer_places_order": "1:N",
            "order_contains_product": "N:1",
            "order_paid_by": "1:N",
            "cart_item_belongs_to": "N:1",
            "cart_item_references_product": "N:1",
            "order_applies_coupon": "N:1",
            "assessed_order": "N:1",
            "triggered_event": "1:N",
        },
    },
}


def enrich(db, domain: str, cfg: dict) -> dict:
    """导入后语义补齐（幂等）：tier / domain / primary_key / required / enum / 关系基数。"""
    stats = {"tier": 0, "pk": 0, "required": 0, "enum": 0, "cardinality": 0}

    for name, tier in cfg["tiers"].items():
        e = db.query(OntologyEntity).filter(OntologyEntity.name == name).first()
        if not e:
            continue
        e.tier = tier
        if e.domain != domain:
            e.domain = domain
        pk = cfg["primary_keys"].get(name)
        if pk:
            schema = e.config_json or {}
            if schema.get("primary_key") != pk:
                schema["primary_key"] = pk
                e.config_json = schema
                flag_modified(e, "config_json")
            stats["pk"] += 1
        stats["tier"] += 1

    for ent_name, attr_name in cfg["required"]:
        e = db.query(OntologyEntity).filter(OntologyEntity.name == ent_name).first()
        if not e:
            continue
        a = db.query(EntityAttribute).filter(
            EntityAttribute.entity_id == e.id, EntityAttribute.name == attr_name
        ).first()
        if a and not a.required:
            a.required = True
            stats["required"] += 1

    for (ent_name, attr_name), enum_cfg in cfg["enums"].items():
        e = db.query(OntologyEntity).filter(OntologyEntity.name == ent_name).first()
        if not e:
            continue
        a = db.query(EntityAttribute).filter(
            EntityAttribute.entity_id == e.id, EntityAttribute.name == attr_name
        ).first()
        if not a:
            continue
        cons = a.constraints_json or {}
        if cons.get("enumValues") != enum_cfg["enumValues"]:
            cons["enumValues"] = enum_cfg["enumValues"]
            cons["enumLabels"] = enum_cfg.get("enumLabels", [])
            a.constraints_json = cons
            flag_modified(a, "constraints_json")
            stats["enum"] += 1

    # 关系基数/类型补齐：必须限定在本场景实体范围内，否则会误改其他场景的同名关系
    # （如无人机场景的 assessed_order / triggered_event）。
    scene_ids = set()
    for name in cfg["tiers"]:
        e = db.query(OntologyEntity).filter(OntologyEntity.name == name).first()
        if e:
            scene_ids.add(e.id)
    for rel_name, card in cfg["relations"].items():
        for r in db.query(EntityRelation).filter(EntityRelation.name == rel_name).all():
            if r.from_entity_id not in scene_ids or r.to_entity_id not in scene_ids:
                continue
            changed = False
            if r.cardinality != card:
                r.cardinality = card
                changed = True
            if r.rel_type in ("has_many", "subclass"):
                r.rel_type = "directed"
                changed = True
            if changed:
                stats["cardinality"] += 1

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="通用 OWL 场景本体导入（幂等）")
    parser.add_argument("--file", required=True, help="OWL 文件路径")
    parser.add_argument("--domain", required=True, help=f"场景标签，当前配置：{', '.join(SCENE_CONFIG)}")
    args = parser.parse_args()

    if args.domain not in SCENE_CONFIG:
        sys.exit(f"[abort] 未配置场景「{args.domain}」的语义补齐配置，请在 SCENE_CONFIG 中添加")

    cfg = SCENE_CONFIG[args.domain]
    entity_names = list(cfg["tiers"].keys())
    owl_path = Path(args.file)
    if not owl_path.exists():
        sys.exit(f"[abort] OWL 文件不存在: {owl_path}")

    db = SessionLocal()
    try:
        existing = {
            e.name: e for e in
            db.query(OntologyEntity).filter(OntologyEntity.name.in_(entity_names)).all()
        }
        found = [n for n in entity_names if n in existing]
        missing = [n for n in entity_names if n not in existing]

        # parse_owl_ontology 已全量幂等去重，混合场景（复用已发布对象）可安全直接解析：
        # 已存在的实体/属性/关系被跳过，仅补齐缺失项。
        if found and missing:
            print(f"[merge] {len(found)} 个实体已存在（将复用并跳过），新建 {len(missing)} 个：{', '.join(missing)}")
        elif not missing:
            print(f"[skip] {len(found)} 个实体已全部存在，解析将全部跳过，仅执行语义补齐")

        content = owl_path.read_bytes()
        result = parse_owl_ontology(content, "xml", db)
        print(
            f"[import] 实体 +{result.entities_created}（跳过 {result.entities_skipped}）"
            f" · 属性 +{result.attributes_created}（跳过 {result.attributes_skipped}）"
            f" · 关系 +{result.relations_created}"
        )
        if result.errors:
            for err in result.errors:
                print(f"  [warn] {err}")

        stats = enrich(db, args.domain, cfg)
        db.commit()
        print(
            f"[enrich] tier/domain 补齐 {stats['tier']} 项 · pk {stats['pk']} 项"
            f" · required {stats['required']} 项 · 枚举 {stats['enum']} 项 · 关系基数 {stats['cardinality']} 条"
        )

        # 结果核验
        print("[verify]")
        for name in entity_names:
            e = db.query(OntologyEntity).filter(OntologyEntity.name == name).first()
            if not e:
                print(f"  {name:24s} ✗ 未入库")
                continue
            attrs = db.query(EntityAttribute).filter(EntityAttribute.entity_id == e.id).count()
            pk = (e.config_json or {}).get("primary_key", "-")
            print(f"  {name:24s} tier={e.tier} domain={e.domain} pk={pk} attrs={attrs}")
        scene_ids = set()
        for name in entity_names:
            e = db.query(OntologyEntity).filter(OntologyEntity.name == name).first()
            if e:
                scene_ids.add(e.id)
        for rel_name in cfg["relations"]:
            for r in db.query(EntityRelation).filter(EntityRelation.name == rel_name).all():
                if r.from_entity_id in scene_ids and r.to_entity_id in scene_ids:
                    print(f"  {r.from_entity_id} --{r.name}({r.cardinality},{r.rel_type})--> {r.to_entity_id}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
