export const DOMAIN_LABEL: Record<string, string> = { military: '军事场景' }
export const STATUS_COLOR: Record<string, string> = { published: '#3b5bdb', draft: '#8fa0b8' }
export const EVENT_LEVEL_COLOR: Record<string, string> = { warning: '#e8590c', ok: '#12b886', info: '#4c6ef5' }
export const EVENT_LEVEL_LABEL: Record<string, string> = { warning: '告警', ok: '正常', info: '信息' }
export const PRIORITY_COLOR: Record<string, string> = { high: '#e8590c', medium: '#4c6ef5', low: '#adb5bd' }
export type ConstraintStatus = 'healthy' | 'warning' | 'failure' | 'unknown'
export const CONSTRAINT_COLOR: Record<ConstraintStatus, string> = { healthy: '#20c997', warning: '#f08c00', failure: '#e03131', unknown: '#8fa0b8' }
export const CONSTRAINT_LABEL: Record<ConstraintStatus, string> = { healthy: '验证通过', warning: '警告', failure: '验证失败', unknown: '已定义·未验证' }
export const STUB_ACTION_TYPES = new Set(['sql_exec', 'modify_attribute', 'notification', 'call_function'])
export const MAX_RULE_BADGES = 3

export function domainLabel(key: string) { return DOMAIN_LABEL[key] || key || '未分组' }
export function formatTime(ts: string | null): string {
  if (!ts) return '—'
  const date = new Date(ts)
  return Number.isNaN(date.getTime()) ? ts : date.toLocaleString('zh-CN', { hour12: false })
}
