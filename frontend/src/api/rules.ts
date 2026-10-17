import { get, post, put, del } from './client'
import type { BusinessRule, RuleStatus, Priority } from '../types'

export interface RuleQuery {
  entityId?: string
  status?: RuleStatus
  priority?: Priority
  search?: string
  tags?: string[]
}

export interface RuleExecuteResult {
  success: boolean
  affectedCount: number
  message: string
}

export interface RuleConditionResult {
  field: string
  display: string
  operator: string
  expected: string | number | boolean | null
  actual: string | number | boolean | null
  matched: boolean
}

export interface RuleEvaluateResult {
  rule_id: string
  rule_name: string
  triggered: boolean
  matched_count: number
  total_count: number
  confidence: number
  conditions: RuleConditionResult[]
  risk_level?: string | null
}

export const ruleApi = {
  list(query?: RuleQuery) {
    const { entityId, ...rest } = query ?? {}
    return get<BusinessRule[]>('/rules', { params: { ...rest, entity_id: entityId } })
  },

  detail(id: string) {
    return get<BusinessRule>(`/rules/${id}`)
  },

  create(data: Partial<BusinessRule> & { entity_id?: string; condition_expr?: string; action_desc?: string }) {
    return post<BusinessRule>('/rules', data)
  },

  update(id: string, data: Partial<BusinessRule>) {
    return put<BusinessRule>(`/rules/${id}`, data)
  },

  remove(id: string) {
    return del<void>(`/rules/${id}`)
  },

  execute(id: string) {
    return post<RuleExecuteResult>(`/rules/${id}/execute`)
  },

  evaluate(id: string, userId: string) {
    return post<RuleEvaluateResult>(`/rules/${id}/evaluate`, { user_id: userId })
  },
}
