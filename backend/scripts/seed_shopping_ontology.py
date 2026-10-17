"""
购物场景本体数据种子脚本
创建三个本体实体：用户(User)、商品(Product)、订单(Order)
并建立它们之间的关系和业务规则
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, engine, Base
from app.models import (
    OntologyEntity, EntityAttribute, EntityRelation,
    BusinessRule, EntityAction, OntologyFunction,
    SceneRegistry, BusinessDocument, User,
)
from app.utils.identifiers import gen_uuid

# 固定 ID，方便后续引用
USER_ID = "shopping_user"
PRODUCT_ID = "shopping_product"
ORDER_ID = "shopping_order"


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # ── 1. 创建三个本体实体 ──────────────────────────────────

        # 用户实体
        if not db.get(OntologyEntity, USER_ID):
            user_entity = OntologyEntity(
                id=USER_ID,
                name="User",
                name_cn="用户",
                tier=1,
                status="published",
                domain="购物",
                description="平台注册用户，包含基本信息、联系方式和账户状态",
                config_json={"primary_key": "user_id", "namespace": "shopping"},
            )
            user_attrs = [
                EntityAttribute(name="user_id", type="string", description="用户唯一标识", required=True, example="U10001", data_status="人工确认"),
                EntityAttribute(name="username", type="string", description="用户登录名", required=True, example="zhangsan", data_status="人工确认"),
                EntityAttribute(name="nickname", type="string", description="用户昵称", example="张三", data_status="人工确认"),
                EntityAttribute(name="email", type="string", description="邮箱地址", example="zhangsan@example.com", data_status="人工确认"),
                EntityAttribute(name="phone", type="string", description="手机号码", example="13800138000", data_status="人工确认"),
                EntityAttribute(name="register_date", type="datetime", description="注册日期", example="2025-01-15", data_status="人工确认"),
                EntityAttribute(name="vip_level", type="integer", description="会员等级(0-5)", example="2", data_status="人工确认"),
                EntityAttribute(name="status", type="string", description="账户状态: active/frozen/cancelled", example="active", data_status="人工确认"),
                EntityAttribute(name="total_spent", type="number", description="累计消费金额", example="15680.50", data_status="人工确认"),
                EntityAttribute(name="address", type="string", description="默认收货地址", example="北京市海淀区中关村大街1号", data_status="人工确认"),
            ]
            user_entity.attributes = user_attrs
            db.add(user_entity)
            print("  [OK] 用户实体 (User) 已创建，含 10 个属性")

        # 商品实体
        if not db.get(OntologyEntity, PRODUCT_ID):
            product_entity = OntologyEntity(
                id=PRODUCT_ID,
                name="Product",
                name_cn="商品",
                tier=1,
                status="published",
                domain="购物",
                description="平台在售商品，包含商品信息、价格、库存等",
                config_json={"primary_key": "product_id", "namespace": "shopping"},
            )
            product_attrs = [
                EntityAttribute(name="product_id", type="string", description="商品唯一标识", required=True, example="P20001", data_status="人工确认"),
                EntityAttribute(name="product_name", type="string", description="商品名称", required=True, example="iPhone 16 Pro", data_status="人工确认"),
                EntityAttribute(name="category", type="string", description="商品分类", example="手机数码", data_status="人工确认"),
                EntityAttribute(name="brand", type="string", description="品牌", example="Apple", data_status="人工确认"),
                EntityAttribute(name="price", type="number", description="售价(元)", required=True, example="7999.00", data_status="人工确认"),
                EntityAttribute(name="cost_price", type="number", description="成本价(元)", example="5800.00", data_status="人工确认"),
                EntityAttribute(name="stock", type="integer", description="库存数量", example="500", data_status="人工确认"),
                EntityAttribute(name="status", type="string", description="商品状态: on_sale/off_sale/discontinued", example="on_sale", data_status="人工确认"),
                EntityAttribute(name="rating", type="number", description="评分(0-5)", example="4.8", data_status="人工确认"),
                EntityAttribute(name="description", type="string", description="商品描述", example="A17 Pro芯片，钛金属设计", data_status="人工确认"),
                EntityAttribute(name="created_at", type="datetime", description="上架时间", example="2025-09-20", data_status="人工确认"),
            ]
            product_entity.attributes = product_attrs
            db.add(product_entity)
            print("  [OK] 商品实体 (Product) 已创建，含 11 个属性")

        # 订单实体
        if not db.get(OntologyEntity, ORDER_ID):
            order_entity = OntologyEntity(
                id=ORDER_ID,
                name="Order",
                name_cn="订单",
                tier=2,
                status="published",
                domain="购物",
                description="用户购买商品的交易订单，包含金额、状态、物流信息",
                config_json={"primary_key": "order_id", "namespace": "shopping"},
            )
            order_attrs = [
                EntityAttribute(name="order_id", type="string", description="订单唯一标识", required=True, example="ORD30001", data_status="人工确认"),
                EntityAttribute(name="user_id", type="string", description="下单用户ID", required=True, example="U10001", data_status="人工确认"),
                EntityAttribute(name="product_ids", type="string", description="商品ID列表(逗号分隔)", required=True, example="P20001,P20003", data_status="人工确认"),
                EntityAttribute(name="total_amount", type="number", description="订单总金额", required=True, example="12998.00", data_status="人工确认"),
                EntityAttribute(name="discount_amount", type="number", description="优惠金额", example="500.00", data_status="人工确认"),
                EntityAttribute(name="pay_amount", type="number", description="实付金额", example="12498.00", data_status="人工确认"),
                EntityAttribute(name="pay_method", type="string", description="支付方式: alipay/wechat/card", example="alipay", data_status="人工确认"),
                EntityAttribute(name="status", type="string", description="订单状态: pending/paid/shipped/delivered/cancelled/refunded", required=True, example="paid", data_status="人工确认"),
                EntityAttribute(name="shipping_address", type="string", description="收货地址", example="上海市浦东新区陆家嘴环路100号", data_status="人工确认"),
                EntityAttribute(name="created_at", type="datetime", description="下单时间", required=True, example="2025-10-01 14:30:00", data_status="人工确认"),
                EntityAttribute(name="paid_at", type="datetime", description="支付时间", example="2025-10-01 14:32:00", data_status="人工确认"),
                EntityAttribute(name="shipped_at", type="datetime", description="发货时间", example="2025-10-02 09:00:00", data_status="人工确认"),
                EntityAttribute(name="delivered_at", type="datetime", description="收货时间", example="2025-10-04 15:00:00", data_status="人工确认"),
                EntityAttribute(name="remark", type="string", description="订单备注", example="请尽快发货", data_status="人工确认"),
            ]
            order_entity.attributes = order_attrs
            db.add(order_entity)
            print("  [OK] 订单实体 (Order) 已创建，含 14 个属性")

        db.flush()

        # ── 2. 创建实体间关系 ──────────────────────────────────

        relations = [
            {
                "id": "rel_user_order",
                "from": USER_ID,
                "to": ORDER_ID,
                "name": "places",
                "name_cn": "下单",
                "rel_type": "has_many",
                "cardinality": "1:N",
                "description": "一个用户可以下多个订单",
            },
            {
                "id": "rel_order_product",
                "from": ORDER_ID,
                "to": PRODUCT_ID,
                "name": "contains",
                "name_cn": "包含商品",
                "rel_type": "many_to_many",
                "cardinality": "N:N",
                "description": "一个订单包含多个商品，一个商品可出现在多个订单中",
            },
            {
                "id": "rel_user_product",
                "from": USER_ID,
                "to": PRODUCT_ID,
                "name": "purchases",
                "name_cn": "购买",
                "rel_type": "many_to_many",
                "cardinality": "N:N",
                "description": "用户购买商品（通过订单间接关联）",
            },
        ]

        for rel_def in relations:
            if not db.get(EntityRelation, rel_def["id"]):
                rel = EntityRelation(
                    id=rel_def["id"],
                    from_entity_id=rel_def["from"],
                    to_entity_id=rel_def["to"],
                    name=rel_def["name"],
                    name_cn=rel_def["name_cn"],
                    rel_type=rel_def["rel_type"],
                    cardinality=rel_def["cardinality"],
                    description=rel_def["description"],
                )
                db.add(rel)
                print(f"  [OK] 关系 {rel_def['name_cn']} ({rel_def['name']}) 已创建")

        db.flush()

        # ── 3. 创建业务规则 ──────────────────────────────────

        rules = [
            {
                "id": "rule_high_value",
                "entity_id": ORDER_ID,
                "name": "高额订单预警",
                "condition_expr": "total_amount > 10000",
                "action_desc": "标记为大额订单，触发人工审核",
                "status": "active",
                "priority": "high",
                "conditions_json": [{"field": "total_amount", "op": ">", "value": 10000}],
            },
            {
                "id": "rule_vip_discount",
                "entity_id": USER_ID,
                "name": "VIP用户优惠规则",
                "condition_expr": "vip_level >= 3 AND total_spent > 5000",
                "action_desc": "自动享受9.5折优惠",
                "status": "active",
                "priority": "medium",
                "conditions_json": [{"field": "vip_level", "op": ">=", "value": 3}, {"field": "total_spent", "op": ">", "value": 5000}],
            },
            {
                "id": "rule_low_stock",
                "entity_id": PRODUCT_ID,
                "name": "低库存预警",
                "condition_expr": "stock < 10 AND status == 'on_sale'",
                "action_desc": "触发补货提醒",
                "status": "active",
                "priority": "high",
                "conditions_json": [{"field": "stock", "op": "<", "value": 10}, {"field": "status", "op": "==", "value": "on_sale"}],
            },
            {
                "id": "rule_cancel_timeout",
                "entity_id": ORDER_ID,
                "name": "超时未支付自动取消",
                "condition_expr": "status == 'pending' AND created_at < now() - 30min",
                "action_desc": "自动取消订单并释放库存",
                "status": "active",
                "priority": "medium",
                "conditions_json": [{"field": "status", "op": "==", "value": "pending"}],
            },
            {
                "id": "rule_refund_check",
                "entity_id": ORDER_ID,
                "name": "退款频率异常检测",
                "condition_expr": "status == 'refunded'",
                "action_desc": "标记异常退款，进入人工审核队列",
                "status": "active",
                "priority": "low",
                "conditions_json": [{"field": "status", "op": "==", "value": "refunded"}],
            },
        ]

        for rule_def in rules:
            existing = db.query(BusinessRule).filter(BusinessRule.id == rule_def["id"]).first()
            if not existing:
                rule = BusinessRule(
                    id=rule_def["id"],
                    entity_id=rule_def["entity_id"],
                    name=rule_def["name"],
                    condition_expr=rule_def["condition_expr"],
                    action_desc=rule_def["action_desc"],
                    status=rule_def["status"],
                    priority=rule_def["priority"],
                    conditions_json=rule_def.get("conditions_json"),
                )
                db.add(rule)
                print(f"  [OK] 规则「{rule_def['name']}」已创建")

        db.flush()

        # ── 4. 创建业务行动 ──────────────────────────────────

        actions = [
            {
                "id": "action_notify_user",
                "entity_id": ORDER_ID,
                "name": "发送订单通知",
                "action_type": "notification",
                "category": "domain",
                "status": "active",
                "description": "向用户发送订单状态变更通知（短信/站内信）",
                "parameters_json": [{"name": "channel", "type": "string", "default": "sms"}, {"name": "template", "type": "string"}],
            },
            {
                "id": "action_freeze_account",
                "entity_id": USER_ID,
                "name": "冻结异常账户",
                "action_type": "update",
                "category": "domain",
                "status": "active",
                "description": "当检测到异常行为时冻结用户账户",
                "parameters_json": [{"name": "reason", "type": "string"}],
                "effects_json": {"field": "status", "value": "frozen"},
            },
            {
                "id": "action_off_sale",
                "entity_id": PRODUCT_ID,
                "name": "商品自动下架",
                "action_type": "update",
                "category": "domain",
                "status": "active",
                "description": "库存为0时自动下架商品",
                "parameters_json": [],
                "preconditions_json": {"field": "stock", "op": "<=", "value": 0},
                "effects_json": {"field": "status", "value": "off_sale"},
            },
        ]

        for act_def in actions:
            existing = db.query(EntityAction).filter(EntityAction.id == act_def["id"]).first()
            if not existing:
                action = EntityAction(
                    id=act_def["id"],
                    entity_id=act_def["entity_id"],
                    name=act_def["name"],
                    action_type=act_def["action_type"],
                    category=act_def.get("category", "domain"),
                    status=act_def["status"],
                    description=act_def.get("description", ""),
                    parameters_json=act_def.get("parameters_json", []),
                    preconditions_json=act_def.get("preconditions_json"),
                    effects_json=act_def.get("effects_json"),
                )
                db.add(action)
                print(f"  [OK] 行动「{act_def['name']}」已创建")

        db.flush()

        # ── 5. 创建计算函数 ──────────────────────────────────

        functions = [
            {
                "id": "func_avg_order_amount",
                "entity_id": USER_ID,
                "name": "用户平均订单金额",
                "return_type": "number",
                "logic_type": "sql",
                "logic_body": "SELECT AVG(pay_amount) FROM <asset> WHERE user_id = :user_id",
                "description": "计算指定用户的平均订单实付金额",
            },
            {
                "id": "func_product_revenue",
                "entity_id": PRODUCT_ID,
                "name": "商品累计营收",
                "return_type": "number",
                "logic_type": "sql",
                "logic_body": "SELECT SUM(pay_amount) FROM <asset> WHERE product_ids LIKE :product_id",
                "description": "统计某商品在所有订单中带来的累计营收",
            },
        ]

        for fn_def in functions:
            existing = db.get(OntologyFunction, fn_def["id"])
            if not existing:
                func = OntologyFunction(
                    id=fn_def["id"],
                    entity_id=fn_def["entity_id"],
                    name=fn_def["name"],
                    return_type=fn_def["return_type"],
                    logic_type=fn_def["logic_type"],
                    logic_body=fn_def["logic_body"],
                    description=fn_def.get("description", ""),
                    tags=["购物场景"],
                )
                db.add(func)
                print(f"  [OK] 函数「{fn_def['name']}」已创建")

        db.flush()

        # ── 6. 创建场景注册卡片 ──────────────────────────────────

        if not db.query(SceneRegistry).filter(SceneRegistry.id == "scene_shopping").first():
            scene = SceneRegistry(
                id="scene_shopping",
                name="购物场景",
                description="以用户、商品、订单三大核心本体构建购物语义网络，覆盖用户行为分析、商品管理、订单全生命周期治理",
                icon="🛒",
                route="/ontology/shopping",
                assets={
                    "object_classes": [USER_ID, PRODUCT_ID, ORDER_ID],
                    "domains": ["购物"],
                },
                created_by=db.query(User).filter_by(role="admin").order_by(User.created_at).first().id if db.query(User).count() > 0 else None,
            )
            db.add(scene)
            print("  [OK] 场景注册卡片「购物场景」已创建")

        # ── 7. 创建业务文档 ──────────────────────────────────

        if not db.query(BusinessDocument).filter(BusinessDocument.id == "doc_shopping_spec").first():
            doc = BusinessDocument(
                id="doc_shopping_spec",
                name="购物场景本体设计说明.md",
                file_type="md",
                parsed_text=(
                    "# 购物场景本体设计说明\n\n"
                    "## 1. 场景概述\n"
                    "本场景围绕电商购物业务，定义三大核心本体：用户、商品、订单。\n\n"
                    "## 2. 本体定义\n\n"
                    "### 2.1 用户 (User)\n"
                    "- 层级：T1（核心实体）\n"
                    "- 主键：user_id\n"
                    "- 关键属性：username, email, phone, vip_level, total_spent\n\n"
                    "### 2.2 商品 (Product)\n"
                    "- 层级：T1（核心实体）\n"
                    "- 主键：product_id\n"
                    "- 关键属性：product_name, category, price, stock, status\n\n"
                    "### 2.3 订单 (Order)\n"
                    "- 层级：T2（业务实体）\n"
                    "- 主键：order_id\n"
                    "- 关键属性：total_amount, pay_amount, status, created_at\n\n"
                    "## 3. 关系定义\n"
                    "- 用户 → 订单：places (1:N)\n"
                    "- 订单 → 商品：contains (N:N)\n"
                    "- 用户 → 商品：purchases (N:N)\n\n"
                    "## 4. 业务规则\n"
                    "- 高额订单预警（>10000元）\n"
                    "- VIP用户优惠规则\n"
                    "- 低库存预警（<10件）\n"
                    "- 超时未支付自动取消\n"
                    "- 退款频率异常检测\n\n"
                    "## 5. 业务行动\n"
                    "- 发送订单通知\n"
                    "- 冻结异常账户\n"
                    "- 商品自动下架\n"
                ),
                summary="购物场景三大本体（用户/商品/订单）的设计说明文档",
                domain_tags=["购物", "本体设计"],
                size_bytes=1200,
                uploaded_by=db.query(User).filter_by(role="admin").order_by(User.created_at).first().id if db.query(User).count() > 0 else None,
            )
            db.add(doc)
            print("  [OK] 业务文档「购物场景本体设计说明」已创建")

        db.commit()

        # ── 汇总 ──────────────────────────────────
        print("\n" + "=" * 50)
        print("  购物场景本体数据入库完成！")
        print("=" * 50)
        from sqlalchemy import func
        print(f"  本体实体: {db.query(OntologyEntity).filter(OntologyEntity.domain == '购物').count()} 个")
        print(f"  属性总数: {db.query(EntityAttribute).filter(EntityAttribute.entity_id.in_([USER_ID, PRODUCT_ID, ORDER_ID])).count()} 个")
        print(f"  关系总数: {db.query(EntityRelation).filter(EntityRelation.id.in_(['rel_user_order', 'rel_order_product', 'rel_user_product'])).count()} 个")
        print(f"  业务规则: {db.query(BusinessRule).filter(BusinessRule.id.like('rule_%')).count()} 个")
        print(f"  业务行动: {db.query(EntityAction).filter(EntityAction.id.like('action_%')).count()} 个")
        print(f"  计算函数: {db.query(OntologyFunction).filter(OntologyFunction.id.like('func_%')).count()} 个")

    except Exception as e:
        db.rollback()
        print(f"\n[ERROR] 数据入库失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 50)
    print("  购物场景本体数据种子脚本")
    print("=" * 50)
    seed()
