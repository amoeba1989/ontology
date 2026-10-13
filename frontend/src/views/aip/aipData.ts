/**
 * AIP 场景平台 — 节点工具箱 / 模型选项 / 操作符等静态元数据
 */

/* ========== 节点工具箱 ========== */
export interface NodeTypeMeta {
  type: string
  label: string
  group: string
  color: string
  icon: string
  description: string
}

export const NODE_TYPES: NodeTypeMeta[] = [
  { type: 'ontologyQuery', label: '本体查询', group: '数据节点', color: '#2E5BFF', description: '查询本体对象实例', icon: 'database' },
  { type: 'datasource', label: '数据源查询', group: '数据节点', color: '#2E5BFF', description: '直接 SQL 查询', icon: 'database' },
  { type: 'ruleEngine', label: '规则引擎', group: '逻辑节点', color: '#FF8900', description: '执行业务规则', icon: 'filter' },
  { type: 'llmAgent', label: '模型节点', group: '逻辑节点', color: '#FF8900', description: '大模型推理', icon: 'brain' },
  { type: 'function', label: 'Function 计算', group: '函数节点', color: '#0EA5E9', description: '调用 OntologyFunction', icon: 'tool' },
  { type: 'agentNode', label: 'Agent 节点', group: 'Agent 节点', color: '#10B981', description: '本体驱动 ReAct 推理', icon: 'robot' },
  { type: 'skillNode', label: 'Skill 节点', group: 'Agent 子节点', color: '#10B981', description: 'Skill 注册', icon: 'thunder' },
  { type: 'toolNode', label: 'Tool 节点', group: 'Agent 子节点', color: '#0EA5E9', description: 'Tool 注册', icon: 'tool' },
  { type: 'condition', label: '条件分支', group: '控制节点', color: '#64748B', description: '条件判断分流', icon: 'branch' },
  { type: 'parallel', label: '并行网关', group: '控制节点', color: '#64748B', description: '下游并行执行', icon: 'branch' },
  { type: 'loop', label: '循环节点', group: '控制节点', color: '#64748B', description: '对列表逐项执行', icon: 'branch' },
  { type: 'writebackOntology', label: '写回本体', group: '动作节点', color: '#059669', description: '写回本体对象', icon: 'save' },
  { type: 'actionSystem', label: '动作执行', group: '动作节点', color: '#059669', description: '调用 EntityAction', icon: 'send' },
  { type: 'httpCall', label: 'HTTP 调用', group: '动作节点', color: '#059669', description: '调用外部 API', icon: 'send' },
  { type: 'subscene', label: '子场景', group: '编排节点', color: '#7C3AED', description: '嵌套执行其他场景', icon: 'robot' },
]

export const NODE_GROUPS = ['数据节点', '逻辑节点', '函数节点', 'Agent 节点', 'Agent 子节点', '控制节点', '动作节点', '编排节点']

/* ========== LLM / ML 模型选项 ========== */
export const LLM_MODELS = [
  { value: 'deepseek-v3', label: '元景大模型 DeepSeek-V3-0324', color: '#7C3AED' },
  { value: 'qwen2.5-72b', label: 'Qwen2.5-72B', color: '#0EA5E9' },
  { value: 'minimax', label: 'MiniMax', color: '#F59E0B' },
  { value: 'glm-4', label: 'GLM-4', color: '#10B981' },
]

export const OPERATORS = ['==', '!=', '>', '<', '>=', '<=', 'IN', 'NOT_IN', 'BETWEEN', 'switch']

export const ACTION_TYPES = [
  { value: 'sms', label: '短信通知' },
  { value: 'app_push', label: 'APP 推送' },
  { value: 'work_order', label: '生成工单' },
  { value: 'api_call', label: 'API 调用' },
  { value: 'email', label: '邮件通知' },
]

export const HTTP_METHODS = [
  { value: 'GET', label: 'GET' },
  { value: 'POST', label: 'POST' },
  { value: 'PUT', label: 'PUT' },
  { value: 'DELETE', label: 'DELETE' },
  { value: 'PATCH', label: 'PATCH' },
]
