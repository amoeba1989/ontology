import { get } from './client'

export type LineageNodeKind = 'asset' | 'object_type' | 'action' | 'rule'

export interface LineageNodeRef {
  kind: LineageNodeKind
  id: string
}

export interface LineageNode {
  kind: LineageNodeKind
  id: string
  label: string | null
  sub_label: string | null
  kind_label?: string | null
  extra: Record<string, unknown> | null
}

export interface LineageEdge {
  source: LineageNodeRef
  target: LineageNodeRef
  relation: string
  relation_label?: string | null
  flow_from?: LineageNodeRef
  flow_to?: LineageNodeRef
  evidence_types?: string[]
  via_module: string | null
  via_purpose: string | null
  weight: number
}

export interface LineageGraph {
  nodes: LineageNode[]
  edges: LineageEdge[]
}

export type TraceDirection = 'upstream' | 'downstream' | 'both'

export interface LineageTrace extends LineageGraph {
  focus: { kind: LineageNodeKind; id: string; label: string; kind_label: string }
  query: { direction: TraceDirection; depth: number; relation: string | null }
  counts: { nodes: number; edges: number; direct: number }
  coverage: {
    truncated: boolean
    max_nodes: number
    checked_sources: string[]
    generated_at: string
    note: string
  }
}

export interface LineageSearchResult {
  results: LineageNode[]
}

export interface LineageEdgeDetail {
  relation: string
  relation_label: string
  evidence_types: string[]
  explain: string
  participates_in_impact: boolean
  status: string
  weight: number
  config_evidence: null | {
    binding_id: string
    role: string
    status: string
    field_mapping_count: number
    updated_at: string
    field_mappings: unknown[]
  }
  execution_evidence: null | { via_purpose: string; via_module: string | null; weight: number }
  needs_review: boolean
  review_reason: string | null
}

export interface LineageCheckFinding {
  category: string
  label: string
  count: number
}

export interface LineageCheckResult {
  scope: { level: string; note: string }
  findings: LineageCheckFinding[]
  checked_at: string
  clean: boolean
}

export const lineageApi = {
  overview() {
    return get<LineageGraph>('/lineage/overview')
  },
  forAsset(assetId: string, depth = 2) {
    return get<LineageGraph>(`/lineage?asset_id=${encodeURIComponent(assetId)}&depth=${depth}`)
  },
  forObjectType(objectTypeId: string, depth = 2) {
    return get<LineageGraph>(`/lineage?object_type_id=${encodeURIComponent(objectTypeId)}&depth=${depth}`)
  },
  search(q: string, limit = 20) {
    return get<LineageSearchResult>('/lineage/search', { params: { q, limit } })
  },
  trace(opts: { kind: LineageNodeKind; node_id: string; direction: TraceDirection; depth: number; relation?: string | null }) {
    return get<LineageTrace>('/lineage/trace', {
      params: {
        kind: opts.kind,
        node_id: opts.node_id,
        direction: opts.direction,
        depth: opts.depth,
        relation: opts.relation || undefined,
      },
    })
  },
  edgeDetail(e: LineageEdge) {
    return get<LineageEdgeDetail>('/lineage/edge-detail', {
      params: {
        source_kind: e.source.kind,
        source_id: e.source.id,
        target_kind: e.target.kind,
        target_id: e.target.id,
        relation: e.relation,
        via_module: e.via_module || undefined,
      },
    })
  },
  check() {
    return get<LineageCheckResult>('/lineage/check')
  },
  exportUrl(opts: { kind: LineageNodeKind; node_id: string; direction: TraceDirection; depth: number }) {
    const p = new URLSearchParams({ kind: opts.kind, node_id: opts.node_id, direction: opts.direction, depth: String(opts.depth) })
    return `/lineage/export?${p.toString()}`
  },
}
