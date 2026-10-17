"""规整场景注册表为恰好 2 个业务场景：无人机黑飞反制 + 电商（幂等）。

历史遗留：默认种子曾创建"边海空情目标研判"（引用不存在的 Target/Sensor/...），
且从未注册无人机场景；"购物场景"名称/描述停留在旧的三实体模型、route 指向无效页。
本脚本按当前 OWL 本体（domain=drone / shopping 的真实实体名）重建两张场景卡。

用法：cd backend && python -m scripts.normalize_scenes
"""
from __future__ import annotations

import sys

from app.database import SessionLocal
from app.models.entity import OntologyEntity
from app.models.scene_registry import SceneRegistry

DRONE = {
    "id": "scene_drone",
    "name": "无人机黑飞反制",
    "description": "基于无人机目标/观测/状态/飞行授权/反制设备/保护区/风险评估/预警事件本体，组织低慢小黑飞目标的侦-判-反闭环处置",
    "icon": "🛡️", "color": "#f59e0b", "route": "/workspace/space", "sort_order": 0,
    "domain": "drone",
}
SHOPPING = {
    "id": "scene_shopping",
    "name": "电商场景",
    "description": "以顾客/商品/订单/购物车项/优惠券/支付流水/订单风险评估/风控预警事件八大本体构建电商语义网络，覆盖用户行为、商品与订单全生命周期治理",
    "icon": "🛒", "color": "#2E5BFF", "route": None, "sort_order": 1,
    "domain": "shopping",
}
# 需要移除的旧场景（军事演示：名称/路由/固定 id 任一命中）
_LEGACY_NAMES = {"边海空情目标研判"}
_LEGACY_ROUTES = {"/scene/military"}
_LEGACY_IDS = {"cdc51fce-3e0a-4f45-a346-048186e69d64"}


def _names(db, domain):
    rows = (
        db.query(OntologyEntity)
        .filter(OntologyEntity.domain == domain)
        .order_by(OntologyEntity.tier, OntologyEntity.name)
        .all()
    )
    return [e.name for e in rows]


def _upsert(db, spec):
    obj = db.get(SceneRegistry, spec["id"])
    payload = {
        "name": spec["name"], "description": spec["description"],
        "icon": spec["icon"], "color": spec["color"],
        "route": spec["route"], "sort_order": spec["sort_order"],
        "status": "enabled",
    }
    assets = {"object_classes": _names(db, spec["domain"]), "domains": [spec["domain"]]}
    if obj:
        for k, v in payload.items():
            setattr(obj, k, v)
        obj.assets = assets  # 新 dict 触发 JSON 列变更检测
        print(f"  * 更新场景 {obj.id} <- {payload['name']} (对象类 {len(assets['object_classes'])})")
    else:
        obj = SceneRegistry(id=spec["id"], assets=assets, **payload)
        db.add(obj)
        print(f"  + 新建场景 {obj.id} = {payload['name']} (对象类 {len(assets['object_classes'])})")


def main() -> int:
    db = SessionLocal()
    try:
        removed = 0
        for s in db.query(SceneRegistry).all():
            if s.id in _LEGACY_IDS or s.name in _LEGACY_NAMES or (s.route or "") in _LEGACY_ROUTES:
                print(f"  - 删除遗留场景 {s.id} = {s.name}")
                db.delete(s)
                removed += 1
        db.flush()
        _upsert(db, DRONE)
        _upsert(db, SHOPPING)
        db.commit()

        final = db.query(SceneRegistry).order_by(SceneRegistry.sort_order).all()
        print(f"\n=== 现有场景 {len(final)} 个 ===")
        for s in final:
            oc = (s.assets or {}).get("object_classes", [])
            print(f"  [{s.sort_order}] {s.name}  route={s.route}  对象类={len(oc)}")
            print(f"        {oc}")
        print(f"（删除遗留 {removed} 个）场景规整完成。")
        return 0
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"执行失败已回滚：{exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
