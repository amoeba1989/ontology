"""退役遗留电商模型，统一为 OWL 8 实体电商场景（幂等）。

背景：早期以 User/Product/Order 三实体 + places/purchases/contains 三关系发布的
简化购物场景（domain=购物），与后续 OWL 导入的 8 实体电商本体（domain=shopping）
语义重叠，导致电商场景分裂为两个 domain、两个“顾客”概念。

本脚本：
1) 删除遗留实体 shopping_user 及其 3 条老关系（User--places-->Order、
   User--purchases-->Product、Order--contains-->Product）；
2) 将 scene_registry 中的“购物场景”重绑定到 shopping 域的 8 个实体。

Product(shopping_product)、Order(shopping_order) 被新模型复用，保留不动。
可重复执行：不存在则跳过。
"""
from __future__ import annotations

import sys

from app.database import SessionLocal
from app.models.entity import OntologyEntity
from app.models.relation import EntityRelation
from app.models.scene_registry import SceneRegistry

# 遗留关系：(from_entity_id, relation_name, to_entity_id)
LEGACY_RELATIONS = [
    ("shopping_user", "places", "shopping_order"),
    ("shopping_user", "purchases", "shopping_product"),
    ("shopping_order", "contains", "shopping_product"),
]
LEGACY_ENTITY_ID = "shopping_user"
SHOPPING_SCENE_ID = "scene_shopping"


def main() -> int:
    db = SessionLocal()
    try:
        # 1) 删除遗留关系
        for from_id, rel_name, to_id in LEGACY_RELATIONS:
            rows = (
                db.query(EntityRelation)
                .filter(
                    EntityRelation.from_entity_id == from_id,
                    EntityRelation.name == rel_name,
                    EntityRelation.to_entity_id == to_id,
                )
                .all()
            )
            for r in rows:
                db.delete(r)
                print(f"  - 删除遗留关系 {from_id} --{rel_name}--> {to_id}")
            if not rows:
                print(f"  . 遗留关系 {from_id} --{rel_name}--> {to_id} 不存在，跳过")

        # 2) 删除遗留实体 shopping_user（级联其属性）
        legacy = db.get(OntologyEntity, LEGACY_ENTITY_ID)
        if legacy:
            for rel in db.query(EntityRelation).filter(
                (EntityRelation.from_entity_id == LEGACY_ENTITY_ID)
                | (EntityRelation.to_entity_id == LEGACY_ENTITY_ID)
            ).all():
                db.delete(rel)
            db.delete(legacy)
            print(f"  - 删除遗留实体 {LEGACY_ENTITY_ID}（{legacy.name}/{legacy.name_cn}, domain={legacy.domain}）")
        else:
            print(f"  . 遗留实体 {LEGACY_ENTITY_ID} 不存在，跳过")

        db.flush()

        # 3) 重绑定“购物场景”到 shopping 域 8 实体
        shop = (
            db.query(OntologyEntity)
            .filter(OntologyEntity.domain == "shopping")
            .order_by(OntologyEntity.tier, OntologyEntity.name)
            .all()
        )
        scene = db.get(SceneRegistry, SHOPPING_SCENE_ID)
        if scene:
            # 构造新 dict 以触发 JSON 列变更检测（原地改同一对象不会标脏）
            scene.assets = {
                **(scene.assets or {}),
                "object_classes": [e.id for e in shop],
                "domains": ["shopping"],
            }
            print(f"  * 购物场景 object_classes -> {len(shop)} 个实体, domains=['shopping']")
        else:
            print(f"  . 未找到 scene_registry {SHOPPING_SCENE_ID}，跳过重绑定")

        db.commit()
        print("电商场景统一完成。")
        return 0
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"执行失败已回滚：{exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
