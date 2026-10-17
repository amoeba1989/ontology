"""/lineage v2 — 本体侧血缘（Asset → ObjectType → Action）。

改造方案落地的接口能力：节点搜索、上下游追踪（方向/层数/关系/截断）、
关系详情（配置+执行依据）、关系检查横幅、中文报告导出。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.data_plane import LineageGraph
from app.services.data_plane.lineage_service import LineageService

router = APIRouter(prefix="/lineage", tags=["data-plane:lineage"])


@router.get("/overview", response_model=LineageGraph)
def get_overview(db: Session = Depends(get_db)):
    """全局血缘大图：所有非废弃边 + 节点元数据。"""
    return LineageService(db).get_overview()


@router.get("", response_model=LineageGraph)
def get_lineage(
    asset_id: str | None = Query(None),
    object_type_id: str | None = Query(None),
    depth: int = Query(2, ge=1, le=5),
    db: Session = Depends(get_db),
):
    if asset_id and object_type_id:
        raise HTTPException(400, "asset_id 与 object_type_id 二选一")
    if asset_id:
        return LineageService(db).get_for_asset(asset_id, depth=depth)
    if object_type_id:
        return LineageService(db).get_for_object_type(object_type_id, depth=depth)
    raise HTTPException(400, "asset_id 或 object_type_id 必填")


@router.get("/search")
def search_nodes(
    q: str = Query("", min_length=1),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """节点搜索：支持中文名、别名、原始名，结果含类型。"""
    return {"results": LineageService(db).search(q, limit=limit)}


@router.get("/trace")
def trace(
    kind: str = Query(..., description="asset | object_type | action | rule"),
    node_id: str = Query(...),
    direction: str = Query("both", pattern="^(upstream|downstream|both)$", description="upstream=查来源 downstream=查影响"),
    depth: int = Query(2, ge=1, le=5),
    relation: str | None = Query(None),
    max_nodes: int = Query(80, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """方向感知的上下游追踪：防环 + 截断 + 中文文案 + 数据流端点。"""
    return LineageService(db).trace(kind, node_id, direction=direction, depth=depth, relation=relation, max_nodes=max_nodes)


@router.get("/edge-detail")
def edge_detail(
    source_kind: str = Query(...),
    source_id: str = Query(...),
    target_kind: str = Query(...),
    target_id: str = Query(...),
    relation: str = Query(...),
    via_module: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """关系详情：分开返回配置依据、执行依据、复核状态与原因。"""
    return LineageService(db).edge_detail(
        source_kind, source_id, target_kind, target_id, relation, via_module
    )


@router.get("/check")
def check(db: Session = Depends(get_db)):
    """关系检查横幅：引用不存在/资产停用/待复核（引用一致性，非审计链）。"""
    return LineageService(db).check()


@router.get("/export", response_class=PlainTextResponse)
def export_report(
    kind: str = Query(...),
    node_id: str = Query(...),
    direction: str = Query("both", pattern="^(upstream|downstream|both)$"),
    depth: int = Query(2, ge=1, le=5),
    db: Session = Depends(get_db),
):
    """导出中文 Markdown 血缘报告（含查询条件、覆盖与截断说明）。"""
    return LineageService(db).export_report(kind, node_id, direction=direction, depth=depth)
