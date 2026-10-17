"""场景中心 — 场景注册表 CRUD API"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.scene_registry import SceneRegistry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scene-registry", tags=["scene-registry"])


class SceneCreate(BaseModel):
    name: str
    description: str = ""
    icon: str = "🔹"
    color: str = "#2E5BFF"
    route: str | None = None
    status: str = "enabled"
    sort_order: int = 0
    assets: dict | None = None


class SceneUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    icon: str | None = None
    color: str | None = None
    route: str | None = None
    status: str | None = None
    sort_order: int | None = None
    assets: dict | None = None


def _serialize(s: SceneRegistry) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "description": s.description,
        "icon": s.icon,
        "color": s.color,
        "route": s.route,
        "assets": s.assets,
        "status": s.status,
        "sort_order": s.sort_order,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


@router.get("")
def list_scenes(db: Session = Depends(get_db)):
    rows = db.query(SceneRegistry).order_by(SceneRegistry.sort_order, SceneRegistry.created_at).all()
    return [_serialize(s) for s in rows]


@router.post("")
def create_scene(body: SceneCreate, db: Session = Depends(get_db)):
    s = SceneRegistry(
        name=body.name,
        description=body.description,
        icon=body.icon,
        color=body.color,
        route=body.route,
        status=body.status,
        sort_order=body.sort_order,
        assets=body.assets,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return _serialize(s)


@router.put("/{scene_id}")
def update_scene(scene_id: str, body: SceneUpdate, db: Session = Depends(get_db)):
    s = db.get(SceneRegistry, scene_id)
    if not s:
        raise HTTPException(status_code=404, detail="场景不存在")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(s, field, value)
    db.commit()
    db.refresh(s)
    return _serialize(s)


@router.delete("/{scene_id}")
def delete_scene(scene_id: str, db: Session = Depends(get_db)):
    s = db.get(SceneRegistry, scene_id)
    if not s:
        raise HTTPException(status_code=404, detail="场景不存在")
    db.delete(s)
    db.commit()
    return {"ok": True}
