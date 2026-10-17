"""OWL 编辑器服务：解析预览、库内导出、草稿导出。

三条路径全部经 rdflib，与 /entities/from-file 的 parse_owl_ontology 保持同一口径：
- parse_owl_to_editor：OWL/TTL → 编辑器文档 JSON（纯解析，不触库、不落库）
- export_db_to_owl：OntologyEntity/Attribute/Relation → OWL 2 XML（从数据库读取，非硬编码）
- export_content_to_owl：编辑器草稿 JSON → OWL 2 XML

tier / primary_key / required / enum 等 OWL 原生表达不了的语义，
导出时写入 rdfs:comment（与 owl/*.owl 文件约定一致），导入后由脚本补齐。
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from rdflib import Graph, Literal, Namespace, URIRef, RDF, RDFS, OWL, XSD

from app.models.entity import OntologyEntity, EntityAttribute
from app.models.relation import EntityRelation

DEFAULT_BASE_IRI = "http://yuanshu.ontology/local#"

# 平台属性类型 → xsd
_TYPE_TO_XSD = {
    "string": XSD.string,
    "number": XSD.decimal,
    "boolean": XSD.boolean,
    "date": XSD.dateTime,
    "json": XSD.string,
    "ref": XSD.string,
    "computed": XSD.string,
}


def _local_name(uri: str) -> str:
    if "#" in uri:
        return uri.rsplit("#", 1)[-1]
    return uri.rsplit("/", 1)[-1]


def _is_named(node) -> bool:
    return isinstance(node, URIRef)


# ── 解析：OWL/TTL → 编辑器结构 ──────────────────────────────────


def parse_owl_to_editor(content: bytes, fmt: str) -> dict:
    """纯解析 OWL/XML 或 Turtle 为编辑器文档结构，不接触数据库。"""
    g = Graph()
    g.parse(data=content, format=fmt)

    errors: list[str] = []

    # 命名空间（过滤 rdflib 内置的标准前缀，避免编辑器文档膨胀）
    _STANDARD = {"rdf", "rdfs", "owl", "xsd", "xml"}
    ns_list: list[str] = []
    for prefix, ns in g.namespaces():
        if prefix and prefix not in _STANDARD:
            ns_list.append(str(ns))

    classes: list[dict] = []
    class_iris: set[str] = set()
    for cls in g.subjects(RDF.type, OWL.Class):
        if not _is_named(cls):
            continue
        uri = str(cls)
        name = _local_name(uri)
        if not name:
            continue
        labels = list(g.objects(cls, RDFS.label))
        comments = list(g.objects(cls, RDFS.comment))
        supers = [
            str(p) for p in g.objects(cls, RDFS.subClassOf) if _is_named(p)
        ]
        classes.append({
            "iri": uri,
            "localName": name,
            "label": str(labels[0]) if labels else None,
            "description": str(comments[0]) if comments else None,
            "superClassIRIs": supers,
        })
        class_iris.add(uri)

    def _parse_properties(prop_type) -> list[dict]:
        props: list[dict] = []
        for prop in g.subjects(RDF.type, prop_type):
            if not _is_named(prop):
                continue
            uri = str(prop)
            name = _local_name(uri)
            if not name:
                continue
            labels = list(g.objects(prop, RDFS.label))
            comments = list(g.objects(prop, RDFS.comment))
            domains = [str(d) for d in g.objects(prop, RDFS.domain) if _is_named(d)]
            ranges = [str(r) for r in g.objects(prop, RDFS.range) if _is_named(r)]
            if prop_type is OWL.ObjectProperty:
                # 对象属性必须落在已知类之间，否则编辑器无法成图
                unknown = [d for d in domains + ranges if d not in class_iris]
                if unknown:
                    errors.append(f"对象属性 {name} 引用了未定义的类，已跳过: {unknown[0]}")
                    continue
            props.append({
                "iri": uri,
                "localName": name,
                "label": str(labels[0]) if labels else None,
                "description": str(comments[0]) if comments else None,
                "domainIRIs": domains,
                "rangeIRIs": ranges,
            })
        return props

    object_properties = _parse_properties(OWL.ObjectProperty)
    data_properties = _parse_properties(OWL.DatatypeProperty)

    return {
        "namespaceIRIs": ns_list,
        "classes": classes,
        "objectProperties": object_properties,
        "dataProperties": data_properties,
        "errors": errors,
    }


# ── 导出：公共建图工具 ──────────────────────────────────────────


def _new_graph(base_iri: str, prefix: str = "ys") -> Graph:
    g = Graph()
    base = Namespace(base_iri)
    g.bind(prefix, base)
    g.bind("owl", OWL)
    g.bind("rdfs", RDFS)
    g.bind("xsd", XSD)
    g.add((base_iri and URIRef(base_iri), RDF.type, OWL.Ontology))
    return g


def _add_class(g: Graph, base, uri: str, label: str, comment: str, super_uris: list[str]) -> URIRef:
    s = URIRef(uri)
    g.add((s, RDF.type, OWL.Class))
    if label:
        g.add((s, RDFS.label, Literal(label, lang="zh")))
    if comment:
        g.add((s, RDFS.comment, Literal(comment, lang="zh")))
    for su in super_uris:
        g.add((s, RDFS.subClassOf, URIRef(su)))
    return s


def _add_object_property(g: Graph, uri: str, label: str, comment: str,
                         domain_uris: list[str], range_uris: list[str]) -> None:
    s = URIRef(uri)
    g.add((s, RDF.type, OWL.ObjectProperty))
    if label:
        g.add((s, RDFS.label, Literal(label, lang="zh")))
    if comment:
        g.add((s, RDFS.comment, Literal(comment, lang="zh")))
    for d in domain_uris:
        g.add((s, RDFS.domain, URIRef(d)))
    for r in range_uris:
        g.add((s, RDFS.range, URIRef(r)))


def _add_data_property(g: Graph, uri: str, label: str, comment: str,
                       domain_uris: list[str], range_node) -> None:
    s = URIRef(uri)
    g.add((s, RDF.type, OWL.DatatypeProperty))
    if label:
        g.add((s, RDFS.label, Literal(label, lang="zh")))
    if comment:
        g.add((s, RDFS.comment, Literal(comment, lang="zh")))
    for d in domain_uris:
        g.add((s, RDFS.domain, URIRef(d)))
    if range_node is not None:
        g.add((s, RDFS.range, range_node))


def _serialize(g: Graph) -> bytes:
    xml = g.serialize(format="xml")
    return xml.encode("utf-8")


# ── 导出：编辑器草稿 JSON → OWL 2 XML ───────────────────────────


def export_content_to_owl(content: dict, iri: str = DEFAULT_BASE_IRI) -> bytes:
    """编辑器文档 JSON（OwlOntology 结构）→ OWL 2 XML。

    编辑器类/属性带 iri 时用其 iri；缺失时回退 base_iri + localName。
    """
    g = _new_graph(iri)
    base = Namespace(iri)

    def _iri_of(node: dict, fallback_name: str) -> str:
        return node.get("iri") or f"{base}{fallback_name}"

    # 先声明全部类（对象属性的 range 可能引用任何类）
    for c in content.get("classes", []):
        name = c.get("localName") or c.get("name") or ""
        if not name:
            continue
        label = c.get("label") or _first_annotation_label(c)
        comment = c.get("description") or ""
        supers = [
            e.get("classIRI") for e in (c.get("superClassExpressions") or [])
            if isinstance(e, dict) and e.get("type") == "namedClass" and e.get("classIRI")
        ]
        _add_class(g, base, _iri_of(c, name), label, comment, supers)

    for p in content.get("objectProperties", []):
        name = p.get("localName") or p.get("name") or ""
        if not name:
            continue
        domains = [d for d in (p.get("domains") or []) if isinstance(d, str)]
        ranges = [r for r in (p.get("ranges") or []) if isinstance(r, str)]
        _add_object_property(
            g, _iri_of(p, name),
            p.get("label") or _first_annotation_label(p),
            p.get("description") or "",
            domains, ranges,
        )

    for p in content.get("dataProperties", []):
        name = p.get("localName") or p.get("name") or ""
        if not name:
            continue
        domains = [d for d in (p.get("domains") or []) if isinstance(d, str)]
        raw_range = p.get("range")
        range_node = URIRef(raw_range) if isinstance(raw_range, str) and raw_range else XSD.string
        _add_data_property(
            g, _iri_of(p, name),
            p.get("label") or _first_annotation_label(p),
            p.get("description") or "",
            domains, range_node,
        )

    return _serialize(g)


def _first_annotation_label(node: dict) -> str:
    """编辑器节点 annotations 中的 rdfs:label 值（兼容前端文档结构）。"""
    for ann in node.get("annotations") or []:
        if isinstance(ann, dict) and ann.get("property") == "rdfs:label":
            return str(ann.get("value") or "")
    return ""


# ── 导出：数据库 → OWL 2 XML ────────────────────────────────────


def export_db_to_owl(db: Session, domain: str | None = None,
                     base_iri: str = DEFAULT_BASE_IRI) -> bytes:
    """从数据库读取本体（可按 domain 场景过滤）导出为 OWL 2 XML。

    语义还原约定：
    - name_cn → rdfs:label；description + tier/primary_key → rdfs:comment
    - 属性按名称跨实体归并（OWL DatatypeProperty 全局唯一），多 domain 共享声明
    - required / enum → 属性 rdfs:comment
    - 关系基数 → 关系 rdfs:comment
    """
    g = _new_graph(base_iri)
    base = Namespace(base_iri)

    q = db.query(OntologyEntity)
    entities = q.all() if not domain else q.filter(OntologyEntity.domain == domain).all()
    if not entities:
        return _serialize(g)

    ent_ids = [e.id for e in entities]
    attrs = db.query(EntityAttribute).filter(EntityAttribute.entity_id.in_(ent_ids)).all()
    rels = db.query(EntityRelation).filter(
        EntityRelation.from_entity_id.in_(ent_ids),
        EntityRelation.to_entity_id.in_(ent_ids),
    ).all()

    id_to_name = {e.id: e.name for e in entities}

    # 类
    for e in entities:
        comment_parts = [e.description] if e.description else []
        comment_parts.append(f"tier={e.tier}")
        pk = (e.config_json or {}).get("primary_key")
        if pk:
            comment_parts.append(f"primary_key={pk}")
        if e.domain:
            comment_parts.append(f"domain={e.domain}")
        _add_class(
            g, base, f"{base}{e.name}", e.name_cn or e.name,
            "; ".join(comment_parts), [],
        )

    # 数据属性：跨实体按名称归并
    by_name: dict[str, dict] = {}
    for a in attrs:
        item = by_name.setdefault(a.name, {"types": set(), "domains": set(), "comments": set()})
        item["domains"].add(f"{base}{id_to_name[a.entity_id]}")
        item["types"].add(_TYPE_TO_XSD.get(a.type, XSD.string))
        if a.required:
            item["comments"].add("required=true")
        cons = a.constraints_json or {}
        if cons.get("enumValues"):
            item["comments"].add(f"enum=[{'|'.join(str(v) for v in cons['enumValues'])}]")
        if a.description:
            item["comments"].add(a.description)
    for name, item in by_name.items():
        xsd_type = sorted(item["types"], key=str)[0]
        _add_data_property(
            g, f"{base}{name}", name,
            "; ".join(sorted(item["comments"])),
            sorted(item["domains"]), xsd_type,
        )

    # 对象属性
    seen_props: set[tuple] = set()
    for r in rels:
        key = (r.name, r.from_entity_id, r.to_entity_id)
        if key in seen_props:
            continue
        seen_props.add(key)
        comment = "; ".join(x for x in [r.cardinality, r.description or ""] if x)
        _add_object_property(
            g, f"{base}{r.name}", r.name_cn or r.name, comment,
            [f"{base}{id_to_name[r.from_entity_id]}"],
            [f"{base}{id_to_name[r.to_entity_id]}"],
        )

    return _serialize(g)
