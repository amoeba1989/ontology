"""OWL 编辑器 API Schema。"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class OwlDocumentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    namespace_iri: str = Field(default="", max_length=255)
    domain: str | None = Field(default=None, max_length=50)
    content: dict


class OwlDocumentUpdate(BaseModel):
    """保存文档。revision 为乐观锁：与库内当前 revision 不一致时拒绝（409）。"""
    name: str | None = Field(default=None, min_length=1, max_length=100)
    namespace_iri: str | None = Field(default=None, max_length=255)
    domain: str | None = Field(default=None, max_length=50)
    content: dict
    revision: int = Field(ge=1)


class OwlDocumentOut(BaseModel):
    id: str
    name: str
    namespace_iri: str | None
    domain: str | None
    content: dict
    revision: int
    created_by: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OwlDocumentBrief(BaseModel):
    id: str
    name: str
    namespace_iri: str | None
    domain: str | None
    revision: int
    class_count: int = 0
    object_property_count: int = 0
    data_property_count: int = 0
    updated_at: datetime

    model_config = {"from_attributes": True}


class OwlParseClass(BaseModel):
    iri: str
    localName: str
    label: str | None = None
    description: str | None = None
    superClassIRIs: list[str] = []


class OwlParseProperty(BaseModel):
    iri: str
    localName: str
    label: str | None = None
    description: str | None = None
    domainIRIs: list[str] = []
    rangeIRIs: list[str] = []


class OwlParseResult(BaseModel):
    """纯解析结果：编辑器导入预览用，不落库。"""
    namespaceIRIs: list[str] = []
    classes: list[OwlParseClass] = []
    objectProperties: list[OwlParseProperty] = []
    dataProperties: list[OwlParseProperty] = []
    errors: list[str] = []


class OwlExportDraftRequest(BaseModel):
    """编辑器草稿导出 OWL：content 为编辑器文档 JSON。"""
    iri: str = Field(default="http://yuanshu.ontology/local#", max_length=255)
    content: dict
