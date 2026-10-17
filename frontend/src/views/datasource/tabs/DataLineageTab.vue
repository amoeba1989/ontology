<template>
  <div class="lb">
    <!-- 顶部工具栏 -->
    <div class="lb__toolbar">
      <div class="lb__title">
        <span class="lb__title-dot"></span>
        数据血缘
      </div>

      <div class="lb__search">
        <input
          v-model="searchQ"
          class="lb__search-input"
          placeholder="搜索数据表、业务对象、行动或规则……"
          @input="onSearchInput"
          @keydown.enter="runSearch"
        />
        <button class="lb__btn lb__btn--primary" @click="runSearch">搜索</button>
        <div v-if="searchOpen && searchResults.length" class="lb__search-pop">
          <div
            v-for="r in searchResults"
            :key="r.kind + ':' + r.id"
            class="lb__search-item"
            @click="focusNode(r, 'both')"
          >
            <span class="lb__kind-tag" :data-k="r.kind">{{ kindLabel(r.kind) }}</span>
            <span class="lb__search-name">{{ r.label || r.id.slice(0, 8) }}</span>
            <span class="lb__search-sub">{{ r.sub_label || '' }}</span>
          </div>
        </div>
      </div>

      <button class="lb__btn" @click="loadOverview">全局概览</button>
      <button class="lb__btn" :disabled="!focus || mode !== 'trace'" @click="doExport">导出报告</button>
    </div>

    <!-- 关系检查横幅 -->
    <div v-if="check && !check.clean" class="lb__banner">
      <span class="lb__banner-icon">⚠</span>
      <span v-for="(f, i) in check.findings" :key="f.category" class="lb__banner-item">
        {{ f.label }} <b>{{ f.count }}</b> 条<i v-if="i < check.findings.length - 1"> · </i>
      </span>
      <span class="lb__banner-scope">（{{ check.scope.note }}）</span>
    </div>

    <!-- 查询条件行 -->
    <div class="lb__querybar">
      <template v-if="focus">
        <span class="lb__current">当前：{{ focus.label }} <i class="lb__current-kind">{{ kindLabel(focus.kind) }}</i></span>
        <button class="lb__dir" :class="{ 'is-on': direction === 'upstream' }" @click="setDir('upstream')">查来源</button>
        <button class="lb__dir" :class="{ 'is-on': direction === 'downstream' }" @click="setDir('downstream')">查影响</button>
        <button class="lb__dir" :class="{ 'is-on': direction === 'both' }" @click="setDir('both')">来源与去向</button>
      </template>
      <span v-else class="lb__mode-hint">全局概览 · 展示全部血缘；点击节点或搜索聚焦后，方可按「展开层数 / 关系」追踪来源与影响</span>
      <span class="lb__grow"></span>
      <label class="lb__field" :class="{ 'is-disabled': !focus }">展开层数
        <select v-model.number="depth" class="lb__select" :disabled="!focus" :title="focus ? '' : '聚焦节点后可用'" @change="onQueryChange">
          <option :value="1">1 层</option><option :value="2">2 层</option>
          <option :value="3">3 层</option><option :value="4">4 层</option><option :value="5">5 层</option>
        </select>
      </label>
      <label class="lb__field" :class="{ 'is-disabled': !focus }">关系
        <select v-model="relation" class="lb__select" :disabled="!focus" :title="focus ? '' : '聚焦节点后可用'" @change="onQueryChange">
          <option value="">全部</option>
          <option value="binds_to">字段映射</option>
          <option value="reads">供数读取</option>
          <option value="writes">写入</option>
          <option value="derives_from">加工生成</option>
        </select>
      </label>
      <span v-if="counts" class="lb__counts">已显示 {{ counts.nodes }} 个节点 · {{ counts.edges }} 条关系<i v-if="truncated">（已截断）</i></span>
    </div>

    <!-- 主体：左导航 + 画布 + 右详情 -->
    <div class="lb__body">
      <aside class="lb__nav">
        <div class="lb__nav-title">节点导航</div>
        <div v-for="grp in navGroups" :key="grp.kind" class="lb__nav-group">
          <div class="lb__nav-group-h">{{ grp.label }}（{{ grp.items.length }}）</div>
          <div
            v-for="n in grp.items"
            :key="n.kind + ':' + n.id"
            class="lb__nav-item"
            :class="{ 'is-focus': focus && focus.id === n.id && focus.kind === n.kind }"
            @click="focusNode(n, 'both')"
          >{{ n.label || n.id.slice(0, 8) }}</div>
        </div>
        <div v-if="!navGroups.length" class="lb__nav-empty">选择一个节点，查看数据来源和使用去向</div>

        <div v-if="recent.length" class="lb__nav-title lb__nav-title--mt">最近查看</div>
        <div v-for="r in recent" :key="'r' + r.kind + r.id" class="lb__nav-item lb__nav-item--recent" @click="focusNode(r, 'both')">{{ r.label }}</div>
      </aside>

      <div class="lb__canvas">
        <VueFlow
          v-if="flowNodes.length"
          v-model:nodes="flowNodes"
          v-model:edges="flowEdges"
          :node-types="nodeTypes"
          :default-edge-options="defaultEdgeOptions"
          :fit-view-on-init="true"
          :fit-view-options="{ padding: 0.2, minZoom: 0.15 }"
          :nodes-draggable="true"
          :nodes-connectable="false"
          :pan-on-drag="true"
          :pro-options="{ hideAttribution: true }"
          @node-click="onNodeClick"
          @edge-click="onEdgeClick"
        >
          <Background variant="dots" :gap="22" :size="1" :pattern-color="patternColor" />
          <Controls position="bottom-left" :show-interactive="false" />
        </VueFlow>

        <div v-if="loading" class="lb__mask"><div class="lb__spin"></div>加载血缘数据…</div>
        <div v-else-if="!flowNodes.length" class="lb__empty">
          <div class="lb__empty-icon">↯</div>
          <div class="lb__empty-title">{{ mode === 'trace' ? '暂未发现关联关系' : '暂无血缘记录' }}</div>
          <div class="lb__empty-desc">
            血缘边由 <b>对象映射（ObjectBinding）</b> 与 <b>执行记录</b> 自动写入。<br />
            请先在「数据接入」注册资产，并在「本体构建」为对象建立映射；随后即可在此追踪来源与影响。
          </div>
        </div>

        <!-- 图例 -->
        <div class="lb__legend">
          <span><i class="lb__dot" data-k="asset"></i>数据资产</span>
          <span><i class="lb__dot" data-k="object_type"></i>业务对象</span>
          <span><i class="lb__dot" data-k="action"></i>业务行动</span>
          <span><i class="lb__line lb__line--dash"></i>推导关系</span>
        </div>
      </div>

      <aside class="lb__detail">
        <!-- 节点详情 -->
        <template v-if="selectedNode && !selectedEdge">
          <div class="lb__detail-h">{{ selectedNode.label || selectedNode.id.slice(0, 8) }}</div>
          <div class="lb__detail-sub">{{ kindLabel(selectedNode.kind) }}<template v-if="selectedNode.sub_label"> · {{ selectedNode.sub_label }}</template></div>
          <div class="lb__kv" v-for="[k, v] in nodeExtraEntries" :key="k"><span>{{ k }}</span><b>{{ v }}</b></div>
          <div class="lb__detail-actions">
            <button class="lb__btn lb__btn--primary" @click="focusNode(selectedNode!, 'upstream')">查来源</button>
            <button class="lb__btn lb__btn--primary" @click="focusNode(selectedNode!, 'downstream')">查影响</button>
          </div>
        </template>

        <!-- 关系详情 -->
        <template v-else-if="selectedEdge">
          <div class="lb__detail-h">{{ edgeDetail?.relation_label || selectedEdge.relation }}</div>
          <div class="lb__detail-sub">{{ edgePathText }}</div>
          <div v-if="edgeLoading" class="lb__detail-loading">加载关系依据…</div>
          <template v-else-if="edgeDetail">
            <div class="lb__section">关系说明</div>
            <p class="lb__para">{{ edgeDetail.explain }}</p>
            <div class="lb__badges">
              <span class="lb__badge">{{ evidenceText }}</span>
              <span class="lb__badge lb__badge--st" :data-st="edgeDetail.status">{{ edgeDetail.status === 'active' ? '有效' : '已停用' }}</span>
              <span v-if="edgeDetail.needs_review" class="lb__badge lb__badge--review">待复核</span>
            </div>
            <div class="lb__section">配置依据</div>
            <div v-if="edgeDetail.config_evidence" class="lb__kv" v-for="row in configRows" :key="row[0]"><span>{{ row[0] }}</span><b>{{ row[1] }}</b></div>
            <p v-else class="lb__para lb__para--muted">暂无配置绑定依据。</p>
            <div class="lb__section">执行情况</div>
            <p v-if="edgeDetail.execution_evidence" class="lb__para">
              用途 <code>{{ edgeDetail.execution_evidence.via_purpose }}</code>，累计 {{ edgeDetail.execution_evidence.weight }} 次。
            </p>
            <p v-else class="lb__para lb__para--muted">当前查询时间范围内暂无关联执行记录（无执行记录不代表配置失效）。</p>
            <template v-if="edgeDetail.needs_review">
              <div class="lb__section">复核原因</div>
              <p class="lb__para lb__para--warn">{{ edgeDetail.review_reason }}</p>
            </template>
          </template>
        </template>

        <div v-else class="lb__detail-hint">点击画布中的节点或连线查看详情。</div>
      </aside>
    </div>

    <!-- 底部路径面包屑 -->
    <div v-if="pathNodes.length" class="lb__crumb">
      <span class="lb__crumb-label">当前路径：</span>
      <template v-for="(n, i) in pathNodes" :key="n.id + i">
        <span class="lb__crumb-node" @click="focusNode(n, 'both')">{{ n.label || n.id.slice(0, 8) }}</span>
        <span v-if="n.relation_label" class="lb__crumb-rel">— {{ n.relation_label }} →</span>
        <span v-else-if="i < pathNodes.length - 1" class="lb__crumb-sep">→</span>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, markRaw, onMounted, watch } from 'vue'
import { VueFlow, MarkerType } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import type { Node, Edge } from '@vue-flow/core'
import { message } from 'ant-design-vue'

import LineageSourceNode from '../../../components/lineage/LineageSourceNode.vue'
import LineageOntologyNode from '../../../components/lineage/LineageOntologyNode.vue'
import LineageAppNode from '../../../components/lineage/LineageAppNode.vue'
import LineageLayerNode from '../../../components/lineage/LineageLayerNode.vue'
import {
  lineageApi,
  type LineageNode, type LineageNodeKind, type LineageEdge, type LineageTrace,
  type TraceDirection, type LineageCheckResult, type LineageEdgeDetail,
} from '../../../api/lineage'
import { useThemeStore } from '../../../store/theme'

const nodeTypes = {
  lineageAsset: markRaw(LineageSourceNode),
  lineageOntology: markRaw(LineageOntologyNode),
  lineageAction: markRaw(LineageAppNode),
  lineageLayer: markRaw(LineageLayerNode),
} as any
const defaultEdgeOptions = { type: 'default', markerEnd: MarkerType.ArrowClosed }

const KIND_NODE_TYPE: Record<LineageNodeKind, string> = {
  asset: 'lineageAsset', object_type: 'lineageOntology', action: 'lineageAction', rule: 'lineageAction',
}
const FLOW_REVERSE = new Set(['derives_from'])

// 主题联动：VueFlow 背景点、连线/标签取色随 light/dark 翻转（容器样式见 <style> 里的 token 变量）
const theme = useThemeStore()
const patternColor = computed(() => theme.isDark ? '#37383d' : '#d7dee9')
watch(() => theme.isDark, () => renderGraph())

const loading = ref(false)
const mode = ref<'trace' | 'overview'>('trace')
const focus = ref<LineageNode | null>(null)
const direction = ref<TraceDirection>('both')
const depth = ref(2)
const relation = ref('')
const trace = ref<LineageTrace | null>(null)
const check = ref<LineageCheckResult | null>(null)
const recent = ref<LineageNode[]>([])

const searchQ = ref('')
const searchResults = ref<LineageNode[]>([])
const searchOpen = ref(false)

const flowNodes = ref<Node[]>([])
const flowEdges = ref<Edge[]>([])
const nodeIndex = ref<Record<string, LineageNode>>({})

const selectedNode = ref<LineageNode | null>(null)
const selectedEdge = ref<LineageEdge | null>(null)
const edgeDetail = ref<LineageEdgeDetail | null>(null)
const edgeLoading = ref(false)

const counts = computed(() => trace.value?.counts ?? (flowNodes.value.length ? { nodes: flowNodes.value.length, edges: flowEdges.value.length } : null))
const truncated = computed(() => !!trace.value?.coverage.truncated)

const navGroups = computed(() => {
  const nodes = trace.value?.nodes ?? []
  const order: LineageNodeKind[] = ['asset', 'object_type', 'action', 'rule']
  return order
    .map(k => ({ kind: k, label: kindLabel(k), items: nodes.filter(n => n.kind === k) }))
    .filter(g => g.items.length)
})

const nodeExtraEntries = computed<[string, string][]>(() => {
  const ex = selectedNode.value?.extra
  if (!ex) return []
  return Object.entries(ex)
    .filter(([, v]) => v !== null && v !== undefined && v !== '')
    .map(([k, v]) => [extraLabel(k), String(v)])
})

const configRows = computed<[string, string][]>(() => {
  const c = edgeDetail.value?.config_evidence
  if (!c) return []
  return [
    ['绑定角色', c.role],
    ['映射字段数', `${c.field_mapping_count} 个`],
    ['最近修改', c.updated_at.slice(0, 16).replace('T', ' ')],
    ['绑定状态', c.status === 'needs_review' ? '待复核' : c.status === 'deprecated' ? '已停用' : '有效'],
  ]
})

const evidenceText = computed(() => {
  const map: Record<string, string> = { config: '配置依据', execution: '执行记录', inference: '推导关系', pending: '待确认' }
  return (edgeDetail.value?.evidence_types ?? []).map(t => map[t] || t).join('、') || '依据详情暂不可用'
})

const edgePathText = computed(() => {
  const e = selectedEdge.value
  if (!e) return ''
  return `${labelOf(e.source)} → ${labelOf(e.target)}`
})

// 路径：选中节点时计算 焦点→节点 的最短数据流路径
const pathNodes = computed(() => {
  const target = selectedNode.value
  if (!target || !trace.value || !focus.value) return []
  if (target.kind === focus.value.kind && target.id === focus.value.id) return []
  const path = shortestPath(focus.value, target, trace.value.edges)
  return path
})

onMounted(() => { loadCheck(); loadOverview() })

function kindLabel(k: LineageNodeKind) {
  return ({ asset: '数据资产', object_type: '业务对象', action: '业务行动', rule: '业务规则' })[k] || k
}
function extraLabel(k: string) {
  return ({ name: '名称', alias: '别名', kind: '类型', tier: '层级', domain: '业务域', status: '状态', action_type: '动作类型', category: '分类', connection_name: '所属连接', entity_id: '所属对象' } as Record<string, string>)[k] || k
}
function labelOf(ref: { kind: LineageNodeKind; id: string }) {
  return nodeIndex.value[`${ref.kind}:${ref.id}`]?.label || ref.id.slice(0, 8)
}

let searchTimer: ReturnType<typeof setTimeout> | null = null
function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer)
  if (!searchQ.value.trim()) { searchOpen.value = false; searchResults.value = []; return }
  searchTimer = setTimeout(runSearch, 300)
}
async function runSearch() {
  const q = searchQ.value.trim()
  if (!q) return
  try {
    const res = await lineageApi.search(q)
    searchResults.value = res.results
    searchOpen.value = res.results.length > 0
  } catch (e) { message.error(`搜索失败：${err(e)}`) }
}

function setDir(d: TraceDirection) { direction.value = d; runTrace() }
function onQueryChange() { if (focus.value) runTrace() }

function focusNode(n: LineageNode | { kind: LineageNodeKind; id: string; label: string | null; sub_label?: string | null }, dir: TraceDirection) {
  focus.value = { kind: n.kind, id: n.id, label: n.label ?? null, sub_label: n.sub_label ?? null, extra: (n as LineageNode).extra ?? null }
  direction.value = dir
  mode.value = 'trace'
  searchOpen.value = false
  selectedNode.value = null; selectedEdge.value = null; edgeDetail.value = null
  recent.value = [focus.value, ...recent.value.filter(r => !(r.kind === focus.value!.kind && r.id === focus.value!.id))].slice(0, 6)
  runTrace()
}

async function runTrace() {
  if (!focus.value) return
  loading.value = true
  try {
    const t = await lineageApi.trace({ kind: focus.value.kind, node_id: focus.value.id, direction: direction.value, depth: depth.value, relation: relation.value || null })
    trace.value = t
    buildGraph(t)
  } catch (e) { message.error(`加载血缘失败：${err(e)}`) }
  finally { loading.value = false }
}

async function loadOverview() {
  loading.value = true
  try {
    const g = await lineageApi.overview()
    trace.value = null
    mode.value = 'overview'
    setGraphInput(g.nodes, g.edges, null)
  } catch (e) { message.error(`加载全局血缘失败：${err(e)}`) }
  finally { loading.value = false }
}

async function loadCheck() {
  try { check.value = await lineageApi.check() } catch { check.value = null }
}

function buildGraph(t: LineageTrace) {
  setGraphInput(t.nodes, t.edges, { kind: t.focus.kind, id: t.focus.id })
}

// 保存最近一次图输入，供主题切换时无需重新拉取即可重算配色/布局
const graphInput = ref<{ nodes: LineageNode[]; edges: LineageEdge[]; focusRef: { kind: LineageNodeKind; id: string } | null } | null>(null)

function setGraphInput(nodes: LineageNode[], edges: LineageEdge[], focusRef: { kind: LineageNodeKind; id: string } | null) {
  graphInput.value = { nodes, edges, focusRef }
  renderGraph()
}

// 焦点查询布局：以焦点为中心按数据流方向做带符号 BFS 分层（上游为负列、下游为正列），每列垂直居中。
function layoutFocus(ids: string[], adjOut: Record<string, string[]>, adjIn: Record<string, string[]>, focusRef: { kind: LineageNodeKind; id: string }): Record<string, { x: number; y: number }> {
  const layer: Record<string, number> = {}
  const fk = `${focusRef.kind}:${focusRef.id}`
  layer[fk] = 0
  const qd: string[] = [fk]
  while (qd.length) {
    const cur = qd.shift()!
    for (const nx of adjOut[cur] || []) if (layer[nx] === undefined || layer[nx] < 0) { layer[nx] = Math.max(1, (layer[cur] || 0) + 1); qd.push(nx) }
  }
  const qu: string[] = [fk]
  while (qu.length) {
    const cur = qu.shift()!
    for (const nx of adjIn[cur] || []) if (layer[nx] === undefined || layer[nx] > 0) { layer[nx] = Math.min(-1, (layer[cur] || 0) - 1); qu.push(nx) }
  }
  for (const id of ids) if (layer[id] === undefined) layer[id] = 0
  const COL = 300, ROW = 92
  const buckets: Record<number, string[]> = {}
  for (const id of ids) { (buckets[layer[id]] ||= []).push(id) }
  const cols = Object.keys(buckets).map(Number).sort((a, b) => a - b)
  const minCol = cols[0] ?? 0
  const maxRows = Math.max(1, ...cols.map(c => buckets[c].length))
  const pos: Record<string, { x: number; y: number }> = {}
  for (const c of cols) {
    const bucket = buckets[c]
    const yStart = ((maxRows - bucket.length) * ROW) / 2   // 每列垂直居中，整体对称更易读
    bucket.forEach((id, rowIdx) => { pos[id] = { x: (c - minCol) * COL, y: yStart + rowIdx * ROW } })
  }
  return pos
}

// 全局概览布局：血缘图往往很“浅”（多为 资产↔对象 两两绑定），拓扑分层只会得到 2 个高列。
// 因此按本体层级分带（资产→对象→行动→规则），带内超过 MAX_ROWS 再横向换列，摊成“宽而矮”的网格，便于一眼看清整体分布。
function layoutOverview(nodes: LineageNode[]): Record<string, { x: number; y: number }> {
  const order: LineageNodeKind[] = ['asset', 'object_type', 'action', 'rule']
  const groups: Record<string, LineageNode[]> = {}
  for (const n of nodes) { (groups[n.kind] ||= []).push(n) }
  const kinds = [
    ...order.filter(k => groups[k]?.length),
    ...Object.keys(groups).filter(k => !order.includes(k as LineageNodeKind)),
  ]
  const COL = 250, ROW = 88, MAX_ROWS = 8
  const bandStart: Record<string, number> = {}
  let cursor = 0
  for (const k of kinds) {
    const subs = Math.max(1, Math.ceil((groups[k]?.length || 0) / MAX_ROWS))
    bandStart[k] = cursor
    cursor += subs
  }
  const pos: Record<string, { x: number; y: number }> = {}
  for (const k of kinds) {
    const g = (groups[k] || []).slice().sort((a, b) => (a.label || '').localeCompare(b.label || '', 'zh'))
    g.forEach((n, i) => {
      const sub = Math.floor(i / MAX_ROWS)
      const row = i % MAX_ROWS
      pos[`${n.kind}:${n.id}`] = { x: (bandStart[k] + sub) * COL, y: row * ROW }
    })
  }
  return pos
}

function renderGraph() {
  const input = graphInput.value
  if (!input) { flowNodes.value = []; flowEdges.value = []; return }
  const { nodes, edges, focusRef } = input
  nodeIndex.value = Object.fromEntries(nodes.map(n => [`${n.kind}:${n.id}`, n]))

  const flows = edges.map(flEof)
  const ids = nodes.map(n => `${n.kind}:${n.id}`)
  let pos: Record<string, { x: number; y: number }>
  if (focusRef) {
    const adjOut: Record<string, string[]> = {}, adjIn: Record<string, string[]> = {}
    for (const f of flows) { (adjOut[f.from] ||= []).push(f.to); (adjIn[f.to] ||= []).push(f.from) }
    pos = layoutFocus(ids, adjOut, adjIn, focusRef)
  } else {
    pos = layoutOverview(nodes)
  }

  const fn: Node[] = nodes.map(n => {
    const id = `${n.kind}:${n.id}`
    const p = pos[id] || { x: 0, y: 0 }
    return {
      id,
      type: KIND_NODE_TYPE[n.kind],
      position: { x: p.x, y: p.y },
      data: { label: n.label || n.id.slice(0, 8), objectName: n.sub_label || '', tier: (n.extra?.tier as number) || undefined },
      class: focusRef && id === `${focusRef.kind}:${focusRef.id}` ? 'lb-node--focus' : '',
    }
  })

  const strokeColor = (rel: string) => rel === 'binds_to' ? '#8B5CF6'
    : rel === 'reads' ? (theme.isDark ? '#60a5fa' : '#3b82f6')
    : rel === 'writes' ? '#f59e0b'
    : '#94a3b8'
  const labelFill = theme.isDark ? '#c1c2c5' : '#475569'
  const labelBgFill = theme.isDark ? '#212226' : '#ffffff'
  const fe: Edge[] = edges.map((e, i) => {
    const f = flEof(e, i)
    const inferred = FLOW_REVERSE.has(e.relation)
    return {
      id: `e-${i}`,
      source: f.from,
      target: f.to,
      label: e.relation_label || undefined,
      style: { stroke: strokeColor(e.relation), strokeWidth: 1.6, strokeDasharray: inferred ? '6 4' : undefined },
      labelStyle: { fontSize: '11px', fill: labelFill },
      labelBgStyle: { fill: labelBgFill, stroke: theme.isDark ? '#37383d' : '#e9ecef', strokeWidth: 1 },
    }
  })
  flowNodes.value = fn
  flowEdges.value = fe
}

function flEof(e: LineageEdge, i?: number) {
  const from = e.flow_from ? `${e.flow_from.kind}:${e.flow_from.id}` : `${e.source.kind}:${e.source.id}`
  const to = e.flow_to ? `${e.flow_to.kind}:${e.flow_to.id}` : `${e.target.kind}:${e.target.id}`
  void i
  return { from, to }
}

function onNodeClick(evt: { node: Node }) {
  const n = nodeIndex.value[evt.node.id]
  if (!n) return
  selectedEdge.value = null; edgeDetail.value = null
  selectedNode.value = n
}

async function onEdgeClick(evt: { edge: Edge }) {
  const e = trace.value?.edges.find((_, i) => `e-${i}` === evt.edge.id)
    ?? (mode.value === 'overview' ? undefined : undefined)
  if (!e) { message.info('全局概览模式请切换到聚焦查询后查看关系依据'); return }
  selectedNode.value = null
  selectedEdge.value = e
  edgeDetail.value = null
  edgeLoading.value = true
  try { edgeDetail.value = await lineageApi.edgeDetail(e) }
  catch (err2) { message.error(`加载关系详情失败：${err(err2)}`) }
  finally { edgeLoading.value = false }
}

type PathNode = LineageNode & { relation_label?: string | null }

function shortestPath(
  from: { kind: LineageNodeKind; id: string },
  to: { kind: LineageNodeKind; id: string },
  edges: LineageEdge[],
): PathNode[] {
  const start = `${from.kind}:${from.id}`, goal = `${to.kind}:${to.id}`
  // 邻接表按数据流方向：from → to
  const adj: Record<string, { to: string; edge: LineageEdge }[]> = {}
  for (const e of edges) {
    const f = flEof(e)
    ;(adj[f.from] ||= []).push({ to: f.to, edge: e })
  }
  // BFS：prev[child] = { node: parent, edge: parent→child 的边 }
  const prev: Record<string, { node: string; edge: LineageEdge } | null> = { [start]: null }
  const q: string[] = [start]
  while (q.length) {
    const cur = q.shift()!
    if (cur === goal) break
    for (const nx of adj[cur] || []) if (!(nx.to in prev)) { prev[nx.to] = { node: cur, edge: nx.edge }; q.push(nx.to) }
  }
  if (!(goal in prev)) return []
  // 回溯得到 start..goal 的有序节点 id
  const ids: string[] = []
  let cur: string | null = goal
  while (cur) { ids.unshift(cur); if (cur === start) break; cur = prev[cur]!.node }
  // relation_label 挂在「流出该节点」的边上，即 prev[next].edge
  const out: PathNode[] = []
  ids.forEach((id, i) => {
    const node = nodeIndex.value[id]
    if (!node) return
    const nextId = ids[i + 1]
    const rel = nextId ? (prev[nextId]?.edge?.relation_label ?? undefined) : undefined
    out.push({ ...node, relation_label: rel })
  })
  return out
}

async function doExport() {
  if (!focus.value) return
  try {
    const url = lineageApi.exportUrl({ kind: focus.value.kind, node_id: focus.value.id, direction: direction.value, depth: depth.value })
    const resp = await fetch(`/api/v1${url}`, { headers: { Accept: 'text/plain' } })
    const text = await resp.text()
    const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `${focus.value.label || 'lineage'}-数据血缘报告.md`
    a.click()
    URL.revokeObjectURL(a.href)
  } catch (e) { message.error(`导出失败：${err(e)}`) }
}

function err(e: unknown): string { return e && typeof e === 'object' && 'message' in e ? (e as { message: string }).message : String(e) }
</script>

<style scoped>
.lb { display: flex; flex: 1; flex-direction: column; gap: 10px; color: var(--neutral-800); background: var(--neutral-0); border: 1px solid var(--neutral-200); border-radius: 12px; padding: 14px; min-height: 520px; }
.lb__toolbar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.lb__title { display: inline-flex; align-items: center; gap: 6px; font-size: 15px; font-weight: 700; color: var(--neutral-900); }
.lb__title-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--semantic-500); }
.lb__search { position: relative; display: flex; gap: 6px; flex: 1; max-width: 520px; }
.lb__search-input { flex: 1; background: var(--neutral-50); border: 1px solid var(--neutral-200); border-radius: 8px; padding: 7px 12px; color: var(--neutral-900); font-size: 13px; }
.lb__search-pop { position: absolute; top: 38px; left: 0; right: 0; background: var(--neutral-0); border: 1px solid var(--neutral-200); border-radius: 8px; z-index: 30; overflow: hidden; }
.lb__search-item { display: flex; align-items: center; gap: 8px; padding: 8px 12px; cursor: pointer; font-size: 13px; color: var(--neutral-800); }
.lb__search-item:hover { background: var(--neutral-100); }
.lb__search-name { font-weight: 600; }
.lb__search-sub { color: var(--neutral-600); font-size: 11px; }
.lb__kind-tag { font-size: 11px; padding: 1px 6px; border-radius: 4px; background: var(--neutral-100); color: var(--neutral-600); }

.lb__btn { background: var(--neutral-50); border: 1px solid var(--neutral-200); color: var(--neutral-800); border-radius: 8px; padding: 7px 14px; font-size: 13px; cursor: pointer; }
.lb__btn:hover:not(:disabled) { border-color: var(--semantic-500); }
.lb__btn:disabled { opacity: .4; cursor: not-allowed; }
.lb__btn--primary { background: var(--semantic-600); border-color: var(--semantic-600); color: #fff; }

.lb__banner { display: flex; align-items: center; gap: 10px; background: var(--status-warning-bg); border: 1px solid var(--status-warning); border-radius: 8px; padding: 7px 12px; font-size: 12px; color: var(--neutral-800); }
.lb__banner-icon { color: var(--status-warning); }
.lb__banner-item b { color: var(--status-warning); margin: 0 2px; }
.lb__banner-scope { color: var(--neutral-600); }

.lb__querybar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; font-size: 13px; }
.lb__current { font-weight: 600; color: var(--neutral-900); }
.lb__current-kind { font-style: normal; color: var(--neutral-600); font-weight: 400; font-size: 11px; margin-left: 4px; }
.lb__dir { background: var(--neutral-50); border: 1px solid var(--neutral-200); color: var(--neutral-600); border-radius: 7px; padding: 5px 12px; font-size: 12px; cursor: pointer; }
.lb__dir.is-on { border-color: var(--semantic-500); color: var(--semantic-600); background: var(--semantic-100); }
.lb__grow { flex: 1; }
.lb__mode-hint { font-size: 12px; color: var(--neutral-500); }
.lb__field { color: var(--neutral-600); font-size: 12px; display: inline-flex; align-items: center; gap: 6px; }
.lb__field.is-disabled { opacity: .5; }
.lb__select { background: var(--neutral-50); border: 1px solid var(--neutral-200); color: var(--neutral-800); border-radius: 6px; padding: 4px 8px; font-size: 12px; }
.lb__select:disabled { cursor: not-allowed; }
.lb__counts { color: var(--neutral-600); font-size: 12px; }

.lb__body { display: grid; grid-template-columns: 200px 1fr 320px; gap: 10px; flex: 1; min-height: 0; }
.lb__nav, .lb__detail { background: var(--neutral-50); border: 1px solid var(--neutral-200); border-radius: 10px; padding: 10px; overflow-y: auto; max-height: 560px; }
.lb__nav-title { font-size: 12px; font-weight: 600; color: var(--neutral-600); margin-bottom: 6px; }
.lb__nav-title--mt { margin-top: 14px; }
.lb__nav-group-h { font-size: 11px; color: var(--neutral-500); margin: 8px 0 4px; }
.lb__nav-item { font-size: 13px; padding: 5px 8px; border-radius: 6px; cursor: pointer; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--neutral-800); }
.lb__nav-item:hover { background: var(--neutral-100); }
.lb__nav-item.is-focus { background: var(--semantic-100); color: var(--semantic-600); }
.lb__nav-item--recent { color: var(--neutral-600); }
.lb__nav-empty { font-size: 12px; color: var(--neutral-500); line-height: 1.6; padding: 8px 0; }

.lb__canvas { position: relative; background: var(--neutral-50); border: 1px solid var(--neutral-200); border-radius: 10px; overflow: hidden; min-height: 460px; }
.lb__mask, .lb__empty { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; color: var(--neutral-600); font-size: 13px; }
.lb__empty { background: var(--neutral-50); }
.lb__empty-icon { font-size: 34px; color: var(--semantic-500); }
.lb__empty-title { font-size: 14px; font-weight: 600; color: var(--neutral-900); }
.lb__empty-desc { font-size: 12px; line-height: 1.7; text-align: center; max-width: 460px; color: var(--neutral-600); }
.lb__empty-desc b { color: var(--neutral-900); }
.lb__spin { width: 22px; height: 22px; border: 2.5px solid var(--neutral-200); border-top-color: var(--semantic-500); border-radius: 50%; animation: lb-spin .7s linear infinite; }
@keyframes lb-spin { to { transform: rotate(360deg); } }
.lb__legend { position: absolute; right: 10px; bottom: 10px; display: flex; flex-direction: column; gap: 4px; background: var(--neutral-0); border: 1px solid var(--neutral-200); border-radius: 8px; padding: 8px 10px; font-size: 11px; color: var(--neutral-600); }
.lb__legend span { display: inline-flex; align-items: center; gap: 6px; }
.lb__dot { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
.lb__dot[data-k="asset"] { background: #4a9eff; }
.lb__dot[data-k="object_type"] { background: #8B5CF6; }
.lb__dot[data-k="action"] { background: #f59e0b; }
.lb__line--dash { width: 16px; height: 0; border-top: 2px dashed var(--neutral-400); }

.lb__detail-h { font-size: 15px; font-weight: 700; color: var(--neutral-900); }
.lb__detail-sub { font-size: 12px; color: var(--neutral-600); margin: 2px 0 12px; }
.lb__kv { display: flex; justify-content: space-between; gap: 12px; font-size: 12px; padding: 5px 0; border-bottom: 1px solid var(--neutral-200); }
.lb__kv span { color: var(--neutral-600); }
.lb__kv b { color: var(--neutral-900); font-weight: 600; text-align: right; max-width: 180px; word-break: break-all; }
.lb__detail-actions { display: flex; gap: 8px; margin-top: 14px; }
.lb__detail-loading, .lb__detail-hint { font-size: 12px; color: var(--neutral-500); padding: 20px 0; text-align: center; }
.lb__section { font-size: 12px; font-weight: 600; color: var(--semantic-600); margin: 14px 0 6px; }
.lb__para { font-size: 12px; line-height: 1.6; color: var(--neutral-700); margin: 0; }
.lb__para--muted { color: var(--neutral-500); }
.lb__para--warn { color: var(--status-warning); }
.lb__para code { background: var(--neutral-100); padding: 1px 5px; border-radius: 4px; }
.lb__badges { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
.lb__badge { font-size: 11px; padding: 2px 8px; border-radius: 5px; background: var(--neutral-100); color: var(--neutral-600); }
.lb__badge--st[data-st="active"] { color: var(--status-success); }
.lb__badge--st[data-st="deprecated"] { color: var(--neutral-500); }
.lb__badge--review { color: var(--status-warning); }

.lb__crumb { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; background: var(--neutral-50); border: 1px solid var(--neutral-200); border-radius: 8px; padding: 8px 12px; font-size: 12px; }
.lb__crumb-label { color: var(--neutral-600); }
.lb__crumb-node { color: var(--semantic-600); cursor: pointer; }
.lb__crumb-node:hover { text-decoration: underline; }
.lb__crumb-rel { color: var(--tier2-primary); }
.lb__crumb-sep { color: var(--neutral-500); }

:deep(.lb-node--focus .ln-node), :deep(.lb-node--focus) { filter: drop-shadow(0 0 6px var(--semantic-500)); }
:deep(.vue-flow__controls) { background: var(--neutral-0); border: 1px solid var(--neutral-200); border-radius: 8px; }
:deep(.vue-flow__controls-button) { background: var(--neutral-0); border-color: var(--neutral-200); color: var(--neutral-600); fill: var(--neutral-600); }
</style>
