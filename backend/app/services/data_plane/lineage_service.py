"""LineageService — 本体侧血缘。

血缘范围：Asset → ObjectType → Action（不画上游 Connection→Asset，不画上游 ETL）。
事件订阅：
- binding.created/updated → upsert (asset → object_type, binds_to)
- binding.deleted → 标 weight=0
- execution.completed → 按 purpose 白名单写 ad-hoc 边
"""
from __future__ import annotations

import logging
from collections import deque
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.connection import Connection
from app.models.entity import OntologyEntity
from app.models.lineage_edge import LineageEdge
from app.models.object_binding import ObjectBinding
from app.models.rule import EntityAction, BusinessRule
from app.repositories.lineage_edge_repo import LineageEdgeRepository
from app.services.data_plane import lineage_semantics as sem

logger = logging.getLogger(__name__)


# 仅这些 purpose 前缀会让 execution.completed 写血缘 ad-hoc 边。
# 避免 probe.* 等"治理动作"也产生大量节点。
LINEAGE_PURPOSE_PREFIXES = ("mnp.", "scene.", "scenes.", "action.write", "ontology.", "copilot.")


class LineageService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = LineageEdgeRepository(db)

    # ── 写边 ───────────────────────────────────────────
    def upsert_binding(self, asset_id: str, object_type_id: str, *, via_module: str = "binding") -> None:
        self.repo.upsert(
            source_kind="asset", source_id=asset_id,
            target_kind="object_type", target_id=object_type_id,
            relation="binds_to", via_module=via_module,
        )
        self.db.commit()

    def deprecate_binding(self, asset_id: str, object_type_id: str) -> None:
        self.repo.deprecate_for_binding(object_type_id, asset_id)
        self.db.commit()

    def upsert_execution(self, asset_id: str, purpose: str) -> None:
        if not asset_id or not purpose:
            return
        if not any(purpose.startswith(p) for p in LINEAGE_PURPOSE_PREFIXES):
            return
        # 解析 purpose 形式为 "<domain>.<feature>" → object_type_id 留空，
        # 这里写 source=asset, target=object_type(by purpose 标签)，
        # 只在 binding 已存在时强化 weight；其余通过 ObjectBinding 写入主路径。
        # 简化：仅累加 ExecutionLog 已有 binds_to 边的 weight（找该 asset 的所有 binding）。
        from app.repositories.object_binding_repo import ObjectBindingRepository
        bindings = ObjectBindingRepository(self.db).list_for_asset(asset_id)
        for b in bindings:
            self.repo.upsert(
                source_kind="asset", source_id=asset_id,
                target_kind="object_type", target_id=b.object_type_id,
                relation="reads", via_module="execute", via_purpose=purpose,
            )
        self.db.commit()

    # ── 查询 ───────────────────────────────────────────
    def get_for_asset(self, asset_id: str, depth: int = 2) -> dict:
        return self._collect("asset", asset_id, depth)

    def get_for_object_type(self, ot_id: str, depth: int = 2) -> dict:
        return self._collect("object_type", ot_id, depth)

    def get_overview(self) -> dict:
        """全局血缘：所有非废弃边 + 涉及节点的元数据。"""
        edges = (
            self.db.query(LineageEdge)
            .filter(LineageEdge.weight > 0)
            .all()
        )
        node_keys: set[tuple[str, str]] = set()
        for e in edges:
            node_keys.add((e.source_kind, e.source_id))
            node_keys.add((e.target_kind, e.target_id))
        node_payload = self._enrich_nodes(node_keys)
        edge_payload = [self._edge_dict(e) for e in edges]
        return {"nodes": node_payload, "edges": edge_payload}

    def _collect(self, kind: str, node_id: str, depth: int) -> dict:
        edges, nodes = self.repo.find_neighbors(kind, node_id, depth=depth)
        node_payload = self._enrich_nodes(nodes)
        edge_payload = [self._edge_dict(e) for e in edges]
        return {"nodes": node_payload, "edges": edge_payload}

    @staticmethod
    def _edge_dict(e: LineageEdge) -> dict:
        return {
            "source": {"kind": e.source_kind, "id": e.source_id},
            "target": {"kind": e.target_kind, "id": e.target_id},
            "relation": e.relation,
            "via_module": e.via_module,
            "via_purpose": e.via_purpose,
            "weight": e.weight,
        }

    def _enrich_nodes(self, node_keys) -> list[dict]:
        asset_ids = [i for k, i in node_keys if k == "asset"]
        ot_ids = [i for k, i in node_keys if k == "object_type"]
        action_ids = [i for k, i in node_keys if k == "action"]

        assets: dict[str, Asset] = {}
        conns: dict[str, Connection] = {}
        if asset_ids:
            asset_rows = self.db.query(Asset).filter(Asset.id.in_(asset_ids)).all()
            assets = {a.id: a for a in asset_rows}
            conn_ids = {a.connection_id for a in asset_rows if a.connection_id}
            if conn_ids:
                conns = {
                    c.id: c for c in
                    self.db.query(Connection).filter(Connection.id.in_(conn_ids)).all()
                }

        ots: dict[str, OntologyEntity] = {}
        if ot_ids:
            ots = {
                o.id: o for o in
                self.db.query(OntologyEntity).filter(OntologyEntity.id.in_(ot_ids)).all()
            }

        actions: dict[str, EntityAction] = {}
        if action_ids:
            actions = {
                a.id: a for a in
                self.db.query(EntityAction).filter(EntityAction.id.in_(action_ids)).all()
            }

        out: list[dict] = []
        for kind, ident in sorted(node_keys):
            label: str | None = None
            sub_label: str | None = None
            extra: dict = {}
            if kind == "asset":
                a = assets.get(ident)
                if a:
                    label = a.alias or a.name
                    sub_label = a.kind
                    extra = {
                        "name": a.name,
                        "alias": a.alias,
                        "kind": a.kind,
                        "connection_id": a.connection_id,
                        "connection_name": (conns.get(a.connection_id).name if a.connection_id and conns.get(a.connection_id) else None),
                        "status": a.status,
                    }
            elif kind == "object_type":
                o = ots.get(ident)
                if o:
                    label = o.name_cn or o.name
                    sub_label = o.name
                    extra = {"name": o.name, "name_cn": o.name_cn, "tier": o.tier}
            elif kind == "action":
                act = actions.get(ident)
                if act:
                    label = act.name
                    sub_label = act.action_type
                    extra = {"name": act.name, "action_type": act.action_type, "category": act.category, "entity_id": act.entity_id}
            out.append({
                "kind": kind,
                "id": ident,
                "label": label,
                "sub_label": sub_label,
                "kind_label": sem.KIND_LABEL_ZH.get(kind, kind),
                "extra": extra or None,
            })
        return out

    # ── 归一化数据流边 ─────────────────────────────────
    def _active_edges(self) -> list[LineageEdge]:
        return self.db.query(LineageEdge).filter(LineageEdge.weight > 0).all()

    def _flow_edge(self, e: LineageEdge) -> dict:
        """把一条 LineageEdge 归一为「数据流边」：flow_from/flow_to 为真实数据流向端点。"""
        src = (e.source_kind, e.source_id)
        tgt = (e.target_kind, e.target_id)
        flow_from, flow_to = sem.flow_endpoints(e.relation, src, tgt)
        forward = flow_from == src
        return {
            "source": {"kind": src[0], "id": src[1]},
            "target": {"kind": tgt[0], "id": tgt[1]},
            "flow_from": {"kind": flow_from[0], "id": flow_from[1]},
            "flow_to": {"kind": flow_to[0], "id": flow_to[1]},
            "relation": e.relation,
            "relation_label": sem.zh_label(e.relation, forward=forward),
            "evidence_types": [sem.evidence_of(e.relation)],
            "via_module": e.via_module,
            "via_purpose": e.via_purpose,
            "weight": e.weight,
        }

    # ── 上下游追踪（方向感知 + 防环 + 截断）──────────────
    def trace(
        self, kind: str, node_id: str,
        direction: str = "both", depth: int = 2,
        relation: str | None = None, max_nodes: int = 80,
    ) -> dict:
        """以 (kind,node_id) 为焦点，按数据流方向 BFS。

        direction: upstream(查来源，沿流入焦点) / downstream(查影响，沿流出) / both。
        防环：全局 visited 集合；截断：节点数达 max_nodes 停止并置 truncated。
        """
        focus = (kind, node_id)
        edges = [self._flow_edge(e) for e in self._active_edges()]
        if relation:
            edges = [x for x in edges if x["relation"] == relation]

        # 邻接表（数据流方向）：out[from]=[(edge,to)]，inn[to]=[(edge,from)]，键为 (kind,id) 元组
        out: dict[tuple, list] = {}
        inn: dict[tuple, list] = {}
        for x in edges:
            out.setdefault((x["flow_from"]["kind"], x["flow_from"]["id"]), []).append(x)
            inn.setdefault((x["flow_to"]["kind"], x["flow_to"]["id"]), []).append(x)

        visited: set[tuple] = {focus}
        collected: list[dict] = []
        collected_ids: set[int] = set()
        truncated = False
        level = {focus: 0}
        dq = deque([focus])
        # both 需要双向，但分别不跨焦点串流：从焦点分别向上/向下扩展
        expand_up = direction in ("upstream", "both")
        expand_down = direction in ("downstream", "both")
        while dq:
            cur = dq.popleft()
            cur_depth = level[cur]
            if cur_depth >= depth:
                continue
            neighbors: list[tuple[dict, tuple]] = []
            if expand_down:
                for x in out.get(cur, []):
                    neighbors.append((x, (x["flow_to"]["kind"], x["flow_to"]["id"])))
            if expand_up:
                for x in inn.get(cur, []):
                    neighbors.append((x, (x["flow_from"]["kind"], x["flow_from"]["id"])))
            for x, nxt in neighbors:
                if id(x) not in collected_ids:
                    collected_ids.add(id(x))
                    collected.append(x)
                if nxt in visited:
                    continue
                if len(visited) >= max_nodes:
                    truncated = True
                    continue
                visited.add(nxt)
                level[nxt] = cur_depth + 1
                dq.append(nxt)

        # 去重边
        uniq = {(x["source"]["kind"], x["source"]["id"], x["target"]["kind"], x["target"]["id"], x["relation"], x["via_module"]): x for x in collected}
        edge_payload = list(uniq.values())
        node_payload = self._enrich_nodes(visited)
        focus_label = next((n["label"] for n in node_payload if n["kind"] == kind and n["id"] == node_id), node_id[:8])
        return {
            "focus": {"kind": kind, "id": node_id, "label": focus_label, "kind_label": sem.KIND_LABEL_ZH.get(kind, kind)},
            "query": {"direction": direction, "depth": depth, "relation": relation},
            "nodes": node_payload,
            "edges": edge_payload,
            "counts": {
                "nodes": len(node_payload),
                "edges": len(edge_payload),
                "direct": sum(1 for x in edge_payload if focus in ((x["flow_from"]["kind"], x["flow_from"]["id"]), (x["flow_to"]["kind"], x["flow_to"]["id"]))),
            },
            "coverage": {
                "truncated": truncated,
                "max_nodes": max_nodes,
                "checked_sources": ["lineage_edges", "object_bindings"],
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "note": "影响表示潜在依赖，不代表必然故障" if direction in ("downstream", "both") else "",
            },
        }

    # ── 节点搜索 ───────────────────────────────────────
    def search(self, q: str, limit: int = 20) -> list[dict]:
        kw = (q or "").strip().lower()
        results: list[dict] = []
        if not kw:
            return results
        for o in self.db.query(OntologyEntity).all():
            hay = " ".join(filter(None, [o.name, o.name_cn, o.domain])).lower()
            if kw in hay:
                results.append({"kind": "object_type", "id": o.id, "label": o.name_cn or o.name, "sub_label": o.name, "kind_label": sem.KIND_LABEL_ZH["object_type"], "extra": {"tier": o.tier, "domain": o.domain}})
        for a in self.db.query(Asset).all():
            hay = " ".join(filter(None, [a.name, a.alias, a.kind])).lower()
            if kw in hay:
                results.append({"kind": "asset", "id": a.id, "label": a.alias or a.name, "sub_label": a.name, "kind_label": sem.KIND_LABEL_ZH["asset"], "extra": {"kind": a.kind, "status": a.status}})
        for act in self.db.query(EntityAction).all():
            hay = " ".join(filter(None, [act.name, act.description])).lower()
            if kw in hay:
                results.append({"kind": "action", "id": act.id, "label": act.name, "sub_label": act.action_type, "kind_label": sem.KIND_LABEL_ZH["action"], "extra": {"action_type": act.action_type, "category": act.category, "entity_id": act.entity_id}})
        return results[:limit]

    # ── 关系详情（配置依据 + 执行依据 + 复核原因）────────
    def edge_detail(self, source_kind, source_id, target_kind, target_id, relation, via_module=None) -> dict:
        """分开呈现依据来源、有效状态、复核状态（§5.4、§6.1）。"""
        e = (
            self.db.query(LineageEdge).filter(
                LineageEdge.source_kind == source_kind, LineageEdge.source_id == source_id,
                LineageEdge.target_kind == target_kind, LineageEdge.target_id == target_id,
                LineageEdge.relation == relation,
            ).first()
        )
        flow_from, flow_to = sem.flow_endpoints(relation, (source_kind, source_id), (target_kind, target_id))
        detail = {
            "relation": relation,
            "relation_label": sem.zh_label(relation, forward=True),
            "evidence_types": [sem.evidence_of(relation)],
            "explain": sem.RELATION_SEMANTICS.get(relation, {}).get("explain", "").format(
                src=self._label_of(flow_from), tgt=self._label_of(flow_to),
            ),
            "participates_in_impact": sem.participates_in_impact(relation),
            "status": "active" if (e and e.weight > 0) else "deprecated",
            "weight": e.weight if e else 0,
            "config_evidence": None,
            "execution_evidence": None,
            "needs_review": False,
            "review_reason": None,
        }
        # 配置依据：asset↔object_type 的 ObjectBinding
        ot_id = target_id if target_kind == "object_type" else (source_id if source_kind == "object_type" else None)
        asset_id = source_id if source_kind == "asset" else (target_id if target_kind == "asset" else None)
        if ot_id and asset_id:
            b = (
                self.db.query(ObjectBinding).filter(
                    ObjectBinding.object_type_id == ot_id, ObjectBinding.asset_id == asset_id,
                ).first()
            )
            if b:
                fm = b.field_mappings or []
                detail["config_evidence"] = {
                    "binding_id": b.id, "role": b.role, "status": b.status,
                    "field_mapping_count": len(fm), "updated_at": b.updated_at.isoformat(),
                    "field_mappings": fm[:20],
                }
                if b.status == "needs_review":
                    detail["needs_review"] = True
                    detail["review_reason"] = b.review_reason or "来源表结构发生变化，请检查已映射字段"
        # 执行依据：via_purpose + weight 窗口
        if e and e.via_purpose:
            detail["execution_evidence"] = {"via_purpose": e.via_purpose, "via_module": e.via_module, "weight": e.weight}
            if sem.evidence_of(relation) == "execution":
                detail["evidence_types"] = ["execution", "config"] if detail["config_evidence"] else ["execution"]
        return detail

    def _label_of(self, key: tuple[str, str]) -> str:
        return next((n["label"] for n in self._enrich_nodes({key}) if n["label"]), key[1][:8])

    # ── 关系检查横幅（§6.3）───────────────────────────
    def check(self, scope: dict | None = None) -> dict:
        """引用一致性检查（区别于审计链验证）。只报告，绝不谎称全系统无异常。"""
        findings = []
        edges = self._active_edges()
        asset_ids = {a.id for a in self.db.query(Asset.id).all()}
        ot_ids = {o.id for o in self.db.query(OntologyEntity.id).all()}
        known = {"asset": asset_ids, "object_type": ot_ids}
        missing_ref = 0
        deprecated_ref = 0
        for e in edges:
            for k, i in ((e.source_kind, e.source_id), (e.target_kind, e.target_id)):
                if k in known and i not in known[k]:
                    missing_ref += 1
        deprecated_assets = {a.id for a in self.db.query(Asset).filter(Asset.status == "deprecated").all()}
        for e in edges:
            if e.source_kind == "asset" and e.source_id in deprecated_assets:
                deprecated_ref += 1
            if e.target_kind == "asset" and e.target_id in deprecated_assets:
                deprecated_ref += 1
        review_bindings = self.db.query(ObjectBinding).filter(ObjectBinding.status == "needs_review").count()
        if missing_ref:
            findings.append({"category": "missing_reference", "label": "引用对象不存在", "count": missing_ref})
        if deprecated_ref:
            findings.append({"category": "deprecated_asset", "label": "关联资产已停用", "count": deprecated_ref})
        if review_bindings:
            findings.append({"category": "needs_review", "label": "结构变更后待复核", "count": review_bindings})
        return {
            "scope": scope or {"level": "full", "note": "检查范围为当前血缘全量边，非字段级"},
            "findings": findings,
            "checked_at": datetime.utcnow().isoformat() + "Z",
            "clean": not findings,
        }

    # ── 中文 Markdown 报告导出（§8）──────────────────
    def export_report(self, kind, node_id, direction="both", depth=2) -> str:
        tr = self.trace(kind, node_id, direction=direction, depth=depth)
        idx = {f"{n['kind']}:{n['id']}": n for n in tr["nodes"]}
        dir_zh = {"upstream": "查来源", "downstream": "查影响", "both": "来源与去向"}[direction]
        lines = [
            f"# {tr['focus']['label']} 数据血缘报告",
            "",
            f"- 方向：{dir_zh}｜展开层数：{depth} 层｜生成时间：{tr['coverage']['generated_at']}",
            f"- 覆盖：{tr['counts']['nodes']} 个节点 · {tr['counts']['edges']} 条关系"
            + ("（已截断，仅展示部分结果）" if tr["coverage"]["truncated"] else ""),
            "",
            "## 关系路径",
        ]
        if not tr["edges"]:
            lines.append("\n暂未发现关联关系。")
        for x in tr["edges"]:
            fl = idx.get(f"{x['flow_from']['kind']}:{x['flow_from']['id']}", {}).get("label", "?")
            tl = idx.get(f"{x['flow_to']['kind']}:{x['flow_to']['id']}", {}).get("label", "?")
            ev = "、".join(sem.EVIDENCE_LABEL_ZH.get(t, t) for t in x["evidence_types"])
            lines.append(f"- {fl} → {x['relation_label']} → {tl}（{ev}）")
        return "\n".join(lines) + "\n"
