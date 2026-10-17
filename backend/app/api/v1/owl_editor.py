"""OWL 编辑器 API：解析预览、草稿文档 CRUD（落库）、OWL 导出。

所有能力均为数据库/API 驱动，无任何内置演示数据：
- POST /parse                上传 OWL/TTL 纯解析为编辑器结构（不落库）
- GET  /export               按场景（domain）从库内本体导出 OWL 2 XML
- POST /export-draft         编辑器草稿 JSON 导出 OWL 2 XML
- GET/POST/PUT/DELETE /documents  编辑器文档草稿持久化（owl_documents 表，revision 乐观锁）
"""
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.owl_document import OwlDocument
from app.schemas.owl_editor import (
    OwlDocumentBrief, OwlDocumentCreate, OwlDocumentOut, OwlDocumentUpdate,
    OwlExportDraftRequest, OwlParseResult,
)
from app.services.audit import write_audit
from app.services.owl_service import (
    DEFAULT_BASE_IRI, export_content_to_owl, export_db_to_owl, parse_owl_to_editor,
)

router = APIRouter(prefix="/owl-editor", tags=["ontology:owl-editor"])

_XML_MEDIA = "application/rdf+xml"


@router.post("/parse", response_model=OwlParseResult)
async def parse_owl(
    file: UploadFile = File(...),
    file_type: str = Form(""),
    db: Session = Depends(get_db),
):
    """上传 OWL/TTL 纯解析为编辑器文档结构。不落库、不写审计。"""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")

    fmt = file_type or ("turtle" if (file.filename or "").endswith((".ttl",)) else "xml")
    if fmt not in ("xml", "turtle"):
        raise HTTPException(status_code=400, detail="file_type 必须为 xml 或 turtle")

    try:
        data = parse_owl_to_editor(content, fmt)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OWL 解析失败: {str(e)}")

    return OwlParseResult(**data)


@router.get("/export")
def export_owl(
    domain: str | None = Query(None, description="场景标签（drone/shopping/...），不传导出全部"),
    base_iri: str = Query(DEFAULT_BASE_IRI),
    db: Session = Depends(get_db),
):
    """按场景从库内本体导出 OWL 2 XML 文件。"""
    try:
        data = export_db_to_owl(db, domain=domain, base_iri=base_iri)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OWL 导出失败: {str(e)}")

    filename = f"{domain or 'all'}-ontology.owl"
    return Response(
        content=data,
        media_type=_XML_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/export-draft")
def export_draft_owl(body: OwlExportDraftRequest):
    """编辑器当前草稿导出为 OWL 2 XML 文件。"""
    try:
        data = export_content_to_owl(body.content, iri=body.iri)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"草稿导出失败: {str(e)}")

    return Response(
        content=data,
        media_type=_XML_MEDIA,
        headers={"Content-Disposition": 'attachment; filename="draft-ontology.owl"'},
    )


# ── 编辑器文档草稿（owl_documents 表） ──────────────────────────


def _brief(d: OwlDocument) -> OwlDocumentBrief:
    content = d.content or {}
    return OwlDocumentBrief(
        id=d.id, name=d.name, namespace_iri=d.namespace_iri, domain=d.domain,
        revision=d.revision,
        class_count=len(content.get("classes") or []),
        object_property_count=len(content.get("objectProperties") or []),
        data_property_count=len(content.get("dataProperties") or []),
        updated_at=d.updated_at,
    )


@router.get("/documents", response_model=list[OwlDocumentBrief])
def list_documents(
    domain: str | None = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(OwlDocument)
    rows = q.all() if not domain else q.filter(OwlDocument.domain == domain).all()
    rows.sort(key=lambda d: d.updated_at, reverse=True)
    return [_brief(d) for d in rows]


@router.get("/documents/{doc_id}", response_model=OwlDocumentOut)
def get_document(doc_id: str, db: Session = Depends(get_db)):
    d = db.get(OwlDocument, doc_id)
    if not d:
        raise HTTPException(status_code=404, detail="文档不存在")
    return d


@router.post("/documents", response_model=OwlDocumentOut, status_code=201)
def create_document(
    body: OwlDocumentCreate,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    exists = db.query(OwlDocument).filter(OwlDocument.name == body.name).first()
    if exists:
        raise HTTPException(status_code=409, detail=f"文档名「{body.name}」已存在")

    d = OwlDocument(
        name=body.name,
        namespace_iri=body.namespace_iri or None,
        domain=body.domain,
        content=body.content,
        revision=1,
        created_by=user.id if user else None,
    )
    db.add(d)
    db.flush()
    write_audit(
        db, user_id=user.id if user else None, user_name=user.name if user else None,
        action="create", target_type="owl_document",
        target_id=d.id, target_name=d.name,
        snapshot_after={"namespace_iri": d.namespace_iri, "domain": d.domain},
    )
    db.commit()
    db.refresh(d)
    return d


@router.put("/documents/{doc_id}", response_model=OwlDocumentOut)
def update_document(
    doc_id: str,
    body: OwlDocumentUpdate,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    """保存草稿。revision 乐观锁：与库内当前 revision 不一致返回 409。"""
    d = db.get(OwlDocument, doc_id)
    if not d:
        raise HTTPException(status_code=404, detail="文档不存在")
    if d.revision != body.revision:
        raise HTTPException(
            status_code=409,
            detail=f"文档已被他人修改（服务端 revision={d.revision}，本地 revision={body.revision}），请刷新后重试",
        )

    d.content = body.content
    if body.namespace_iri is not None:
        d.namespace_iri = body.namespace_iri or None
    if body.domain is not None:
        d.domain = body.domain
    d.revision = body.revision + 1

    write_audit(
        db, user_id=user.id if user else None, user_name=user.name if user else None,
        action="update", target_type="owl_document",
        target_id=d.id, target_name=d.name,
        snapshot_after={"revision": d.revision},
    )
    db.commit()
    db.refresh(d)
    return d


@router.delete("/documents/{doc_id}", status_code=204)
def delete_document(
    doc_id: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    d = db.get(OwlDocument, doc_id)
    if not d:
        raise HTTPException(status_code=404, detail="文档不存在")

    write_audit(
        db, user_id=user.id if user else None, user_name=user.name if user else None,
        action="delete", target_type="owl_document",
        target_id=d.id, target_name=d.name,
        snapshot_before={"revision": d.revision},
    )
    db.delete(d)
    db.commit()
