import { get } from './client'

export interface SceneAttribute {
  id: string
  name: string
  type: string
  required: boolean
  example: string | null
  description: string
  source_field: string | null
  constraints: Record<string, unknown>
  constraint_text: string
}

export interface SceneRule {
  id: string
  name: string
  condition_expr: string
  action_desc: string
  status: string
  priority: string
  trigger_count: number
  last_triggered: string | null
  action_name: string | null
  conditions: Record<string, unknown>
}

export interface SceneActionItem {
  id: string
  name: string
  action_type: string
  status: string
  description: string
}

export interface SceneNode {
  id: string
  name: string
  name_cn: string
  tier: number
  status: string
  domain: string
  description: string
  instance_count: number
  source_table: string
  asset_id: string
  /** 绑定资产的质量规则聚合状态；null = 该资产没挂任何规则，页面不画约束标 */
  constraint_status: string | null
  constraint_rule_count: number
  constraint_by_status: Record<string, number>
  relation_count: number
  attributes: SceneAttribute[]
  rules: SceneRule[]
  actions: SceneActionItem[]
}

export interface SceneEdge {
  id: string
  from_id: string
  to_id: string
  from_name: string
  to_name: string
  label: string
  name_cn: string
  rel_type: string
  cardinality: string
  description: string
}

export interface OntologyScene {
  domains: { key: string; label: string; entity_count: number }[]
  nodes: SceneNode[]
  edges: SceneEdge[]
  summary: {
    node_count: number
    edge_count: number
    domain_count: number
    attribute_count: number
    rule_count: number
    instance_count: number
  }
  active_domain: string
  active_domain_label: string
}

export type EventLevel = 'info' | 'ok' | 'warning'
export type EventKind = 'instance' | 'rule_hit' | 'action_exec'

export interface SceneEvent {
  id: string
  kind: EventKind
  entity_id: string
  entity_name: string
  entity_name_cn: string
  domain: string
  object_id: string
  label: string
  summary: string
  timestamp: string | null
  level: EventLevel
  tags: { key: string; value: string; level: EventLevel }[]
  source_entity_id: string | null
  source_entity_name_cn: string | null
  relation_id: string | null
  relation_label: string | null
  rule_id: string | null
  user_name?: string | null
}

export interface OntologyEvents {
  events: SceneEvent[]
  window: { from: string; to: string } | null
  counts: { entity_id: string; entity_name_cn: string; count: number }[]
  total: number
}

export const ontologySceneApi = {
  scene(domain?: string) {
    return get<OntologyScene>('/dashboard/ontology-scene', { params: domain ? { domain } : {} })
  },
  events(domain?: string, limit = 30) {
    return get<OntologyEvents>('/dashboard/ontology-events', {
      params: { limit, ...(domain ? { domain } : {}) },
    })
  },
}
