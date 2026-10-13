<template>
  <div class="pl-tab">
    <!-- 顶部统计与操作 -->
    <div class="pl-header">
      <div class="pl-stats">
        <div class="pl-stat"><div class="pl-stat__lbl">管线总数</div><div class="pl-stat__num" style="color:#1f2937">{{ summary.total }}</div></div>
        <div class="pl-stat"><div class="pl-stat__lbl">运行中</div><div class="pl-stat__num" style="color:#10b981">{{ summary.running }}</div></div>
        <div class="pl-stat"><div class="pl-stat__lbl">成功</div><div class="pl-stat__num" style="color:#059669">{{ summary.success }}</div></div>
        <div class="pl-stat"><div class="pl-stat__lbl">已停止</div><div class="pl-stat__num" style="color:#6b7280">{{ summary.stopped }}</div></div>
        <div class="pl-stat"><div class="pl-stat__lbl">错误</div><div class="pl-stat__num" style="color:#ef4444">{{ summary.error }}</div></div>
        <div class="pl-stat"><div class="pl-stat__lbl">上次执行总记录</div><div class="pl-stat__num" style="color:#3b82f6">{{ fmtNum(summary.total_records_last_run) }}</div></div>
      </div>
      <div class="pl-toolbar">
        <a-input-search v-model:value="keyword" placeholder="搜索管线名称 / 描述 / 来源 / 目标" style="width: 280px" allow-clear />
        <a-select v-model:value="statusFilter" style="width: 140px" :options="statusOptions" />
        <a-button @click="refreshList">刷新</a-button>
        <a-button type="primary" @click="openCreate">+ 新建管线</a-button>
      </div>
    </div>

    <!-- 列表 -->
    <div v-if="filtered.length === 0 && !keyword && !statusFilter" class="pl-empty">
      <div class="pl-empty__title">暂无管线</div>
      <div class="pl-empty__sub">管线用于把数据源接入并按步骤推进，到达目标本体对象</div>
      <a-button type="primary" @click="openCreate">+ 新建第一条管线</a-button>
    </div>
    <div v-else-if="filtered.length === 0" class="pl-empty pl-empty--small">没有符合筛选条件的管线</div>
    <div v-else class="pl-list">
      <div v-for="p in filtered" :key="p.id" class="pl-card" :style="{ borderLeftColor: statusColor(activeStatus(p)) }">
        <div class="pl-card__body">
          <div class="pl-card__head">
            <span class="pl-card__name">{{ p.name }}</span>
            <span class="pl-tag" :style="engineTagStyle(p.engine)">{{ p.engine === 'real' ? '真实 ETL' : '演示' }}</span>
            <span class="pl-tag" :style="tagStyle(activeStatus(p))">{{ statusLabel(activeStatus(p)) }}</span>
            <span v-if="activeRuns[p.id]" class="pl-tag" :style="tagStyle('pending')">
              步骤 {{ activeRuns[p.id].step_index + 1 }}/{{ stepCount(p) }} · {{ activeRuns[p.id].step_label }}
            </span>
            <span v-else-if="p.last_run_at && p.last_records != null" class="pl-card__meta">
              上次同步 {{ fmtNum(p.last_records) }} 条 · {{ fmtDur(p.last_duration_ms) }} · {{ fmtDate(p.last_run_at) }}
            </span>
          </div>

          <div class="pl-steps">
            <span class="pl-step" :style="badgeStyle('#3b82f6', '#3b82f6', false)">{{ p.source || '数据源' }}</span>
            <template v-for="(s, i) in p.steps" :key="i">
              <span class="pl-arrow">›</span>
              <span class="pl-step" :style="stepBadgeStyle(p, i)">{{ s }}</span>
            </template>
            <span class="pl-arrow">›</span>
            <span class="pl-step" :style="badgeStyle('#7c3aed', '#7c3aed', false)">{{ p.target || '目标' }}</span>
          </div>

          <div v-if="activeRuns[p.id]" class="pl-progress">
            <div class="pl-progress__bar" :style="{ width: (activeRuns[p.id].progress || 0) + '%' }" />
          </div>

          <div v-else-if="p.engine === 'real' && p.last_run_at" class="pl-lastrun pl-lastrun--real">
            上次执行：读取 → 写入 {{ fmtNum(p.last_records || 0) }} 行，耗时 {{ fmtDur(p.last_duration_ms) }}
          </div>
          <div v-else-if="p.last_records != null" class="pl-lastrun">
            上次执行：同步 {{ fmtNum(p.last_records) }} 条 → {{ fmtNum(p.last_objects || 0) }} 个本体对象，耗时 {{ fmtDur(p.last_duration_ms) }}
          </div>
        </div>

        <div class="pl-card__actions">
          <a-button v-if="activeStatus(p) === 'running'" danger size="small" @click="stopPipeline(p)">停止</a-button>
          <a-button v-else size="small" type="primary" ghost style="color:#10b981;border-color:#a7f3d0" @click="runPipeline(p)">运行</a-button>
          <a-button v-if="p.engine === 'real'" size="small" @click="openPreview(p)">预览</a-button>
          <a-button size="small" @click="openDetail(p)">详情</a-button>
          <a-button size="small" :disabled="activeStatus(p) === 'running'" @click="openEdit(p)">编辑</a-button>
          <a-popconfirm title="删除此管线？关联的运行历史也会被删除。" @confirm="deletePipeline(p)">
            <a-button size="small">删除</a-button>
          </a-popconfirm>
        </div>
      </div>
    </div>

    <!-- 新建/编辑抽屉 -->
    <a-drawer v-model:open="showEditor" :title="editing ? '编辑管线 — ' + editing.name : '新建管线'" width="620" destroy-on-close>
      <a-form layout="vertical">
        <a-form-item label="管线名称 *">
          <a-input v-model:value="form.name" placeholder="如：客户主数据接入" />
        </a-form-item>
        <a-form-item label="描述">
          <a-textarea v-model:value="form.description" :rows="2" />
        </a-form-item>

        <a-form-item label="引擎类型 *">
          <a-radio-group v-model:value="form.engine" button-style="solid" @change="onEngineChange">
            <a-radio-button value="mock">演示（仅进度动画）</a-radio-button>
            <a-radio-button value="real">真实 ETL（抽取→转换→写入）</a-radio-button>
          </a-radio-group>
          <div class="pl-help" v-if="form.engine === 'real'">真实引擎从源连接读数据、按列映射转换、写入目标表（目标表须已存在、目标连接须开启可写）。</div>
          <div class="pl-help" v-else>演示引擎只推进步骤进度条，不搬运任何真实数据。</div>
        </a-form-item>

        <!-- 真实 ETL 配置 -->
        <template v-if="form.engine === 'real'">
          <div class="pl-section-title">① 数据源（抽取）</div>
          <a-form-item label="源连接 *">
            <a-select v-model:value="form.srcConn" :options="dbConnOptions" placeholder="选择数据库连接" show-search option-filter-prop="label" />
          </a-form-item>
          <a-form-item label="抽取 SQL *">
            <a-textarea v-model:value="form.srcQuery" :rows="3" placeholder="SELECT * FROM orders_staging" />
            <div class="pl-help">仅支持 SELECT；可用 WHERE 做行过滤。占位符用 :name 风格。</div>
          </a-form-item>

          <div class="pl-section-title">② 目标（写入）</div>
          <a-row :gutter="12">
            <a-col :span="12">
              <a-form-item label="目标连接 *">
                <a-select v-model:value="form.tgtConn" :options="dbConnOptions" placeholder="选择数据库连接" show-search option-filter-prop="label" @change="onTgtConnChange" />
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item label="目标表 *">
                <a-select v-model:value="form.tgtTable" :options="targetTableOptions" placeholder="选择表" show-search @change="onTgtTableChange" :loading="loadingTables" />
              </a-form-item>
            </a-col>
          </a-row>
          <a-row :gutter="12">
            <a-col :span="12">
              <a-form-item label="写入模式 *">
                <a-select v-model:value="form.writeMode" :options="writeModeOptions" />
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item v-if="form.writeMode === 'upsert'" label="主键列（逗号分隔）*">
                <a-input v-model:value="form.upsertKeysText" placeholder="order_id" />
              </a-form-item>
            </a-col>
          </a-row>
          <div class="pl-help" style="margin-top:-8px;margin-bottom:12px">目标连接需 <b>writable=可写</b>（下拉中标「只读」的无法作为写入目标）。</div>

          <div class="pl-section-title">
            ③ 列映射（转换）
            <a-button size="small" style="margin-left:8px" :disabled="!form.tgtConn || !form.tgtTable" :loading="loadingCols" @click="autoMapFromTarget">拉取目标列自动生成</a-button>
          </div>
          <div class="pl-help" style="margin-bottom:8px">留空则源结果列原样写入同名列。自动生成后可逐行微调源列名与类型转换。</div>
          <div class="pl-map">
            <div class="pl-map__head"><span>源列（from）</span><span>目标列（to）</span><span>类型转换</span><span></span></div>
            <div v-for="(m, i) in form.columnMap" :key="i" class="pl-map__row">
              <a-input v-model:value="m.from" size="small" placeholder="源列名" />
              <a-input v-model:value="m.to" size="small" placeholder="目标列名" />
              <a-select v-model:value="m.cast" size="small" :options="castOptions" style="width:100%" />
              <a-button size="small" type="text" danger @click="form.columnMap.splice(i, 1)">删</a-button>
            </div>
            <a-button size="small" type="dashed" block @click="form.columnMap.push({ from: '', to: '', cast: '' })">+ 添加映射行</a-button>
          </div>
        </template>

        <!-- 演示/通用字段 -->
        <a-row :gutter="12" style="margin-top:16px">
          <a-col :span="12">
            <a-form-item label="数据来源（展示用）">
              <a-input v-model:value="form.source" placeholder="例：B域数仓" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="目标对象（展示用）">
              <a-input v-model:value="form.target" placeholder="例：Customer对象" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item v-if="form.engine === 'mock'" label="关联数据源">
          <a-select v-model:value="form.datasource_id" :options="dsOptions" allow-clear placeholder="— 不绑定 —" />
          <div class="pl-help">执行成功后，将以该数据源的记录数作为本次同步记录数</div>
        </a-form-item>
        <a-form-item label="步骤定义（每行一个步骤）*">
          <a-textarea v-model:value="form.stepsText" :rows="3" />
          <div class="pl-help">至少一个步骤；真实引擎按「抽取/转换/加载」三段推进，此处文本用作步骤标签。</div>
        </a-form-item>
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item v-if="form.engine === 'mock'" label="单步执行时长（毫秒）">
              <a-input-number v-model:value="form.step_duration_ms" :min="100" :max="60000" style="width:100%" />
              <div class="pl-help">范围 100 - 60000</div>
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="调度（Cron 文本）">
              <a-input v-model:value="form.schedule" placeholder="可选，仅作为展示字段" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="标签（逗号分隔）">
          <a-input v-model:value="form.tags" />
        </a-form-item>
      </a-form>
      <template #extra>
        <a-space>
          <a-button @click="showEditor = false">取消</a-button>
          <a-button type="primary" @click="handleSave">{{ editing ? '保存修改' : '创建管线' }}</a-button>
        </a-space>
      </template>
    </a-drawer>

    <!-- 详情抽屉 -->
    <a-drawer v-model:open="showDetail" :title="detail ? '管线详情 — ' + detail.name : ''" width="760" destroy-on-close>
      <div v-if="detail" class="pl-detail">
        <div class="pl-detail__grid">
          <div class="pl-detail__row"><div class="pl-detail__lbl">管线 ID</div><div class="pl-detail__val">{{ detail.id }}</div></div>
          <div class="pl-detail__row"><div class="pl-detail__lbl">引擎</div><div class="pl-detail__val">{{ detail.engine === 'real' ? '真实 ETL' : '演示' }}</div></div>
          <div class="pl-detail__row"><div class="pl-detail__lbl">状态</div><div class="pl-detail__val">{{ statusLabel(detail.status) }}</div></div>
          <div class="pl-detail__row"><div class="pl-detail__lbl">数据来源</div><div class="pl-detail__val">{{ detail.source || '—' }}</div></div>
          <div class="pl-detail__row"><div class="pl-detail__lbl">目标对象</div><div class="pl-detail__val">{{ detail.target || '—' }}</div></div>
          <div class="pl-detail__row"><div class="pl-detail__lbl">调度</div><div class="pl-detail__val">{{ detail.schedule || '—' }}</div></div>
          <template v-if="detail.engine === 'real'">
            <div class="pl-detail__row"><div class="pl-detail__lbl">源连接</div><div class="pl-detail__val">{{ connName(detail.config_json?.source?.connection_id) }}</div></div>
            <div class="pl-detail__row"><div class="pl-detail__lbl">目标</div><div class="pl-detail__val">{{ connName(detail.config_json?.target?.connection_id) }} · {{ detail.config_json?.target?.table }}（{{ writeModeLabel(detail.config_json?.target?.write_mode) }}）</div></div>
            <div class="pl-detail__row" style="grid-column:1/-1"><div class="pl-detail__lbl">抽取 SQL</div><div class="pl-detail__val" style="font-family:monospace">{{ detail.config_json?.source?.query || '—' }}</div></div>
          </template>
          <div class="pl-detail__row"><div class="pl-detail__lbl">标签</div><div class="pl-detail__val">{{ (detail.tags || []).join(', ') || '—' }}</div></div>
        </div>
        <div v-if="detail.description" class="pl-detail__desc">{{ detail.description }}</div>

        <div class="pl-detail__section">
          <div class="pl-detail__title">步骤定义（{{ detail.steps.length }}）</div>
          <div class="pl-detail__steps">
            <span v-for="(s, i) in detail.steps" :key="i" class="pl-detail__stepchip">{{ i + 1 }}. {{ s }}</span>
          </div>
        </div>

        <div class="pl-detail__section">
          <div class="pl-detail__title">执行历史（{{ (detail.recent_runs || []).length }}）</div>
          <div v-if="!detail.recent_runs || detail.recent_runs.length === 0" class="pl-detail__empty">暂无执行记录</div>
          <a-table v-else :columns="runCols" :data-source="detail.recent_runs" :pagination="false" size="small" row-key="id">
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'status'">
                <span class="pl-tag" :style="tagStyle(record.status)">{{ statusLabel(record.status) }}</span>
              </template>
              <template v-else-if="column.key === 'step'">#{{ record.step_index + 1 }} {{ record.step_label || '—' }}</template>
              <template v-else-if="column.key === 'rw'">{{ fmtNum(record.records_read) }} → {{ fmtNum(record.records_written) }}</template>
              <template v-else-if="column.key === 'records'">{{ fmtNum(record.records) }}</template>
              <template v-else-if="column.key === 'duration'">{{ fmtDur(record.duration_ms) }}</template>
              <template v-else-if="column.key === 'started'">{{ fmtDate(record.started_at) }}</template>
              <template v-else-if="column.key === 'error'">
                <span v-if="record.error" style="color:#ef4444">{{ record.error }}</span><span v-else>—</span>
              </template>
            </template>
          </a-table>
        </div>
      </div>
    </a-drawer>

    <!-- 预览弹窗 -->
    <a-modal v-model:open="showPreview" title="转换预览（Dry-run，不写库）" width="760" :footer="null">
      <div v-if="previewLoading" class="pl-detail__empty">抽取中…</div>
      <template v-else-if="previewData">
        <div class="pl-preview__meta">
          抽取 {{ fmtNum(previewData.records_read) }} 行 · 目标表 <b>{{ previewData.target_table }}</b> · 写入模式 {{ writeModeLabel(previewData.write_mode) }} · 展示前 {{ previewData.rows.length }} 行
        </div>
        <a-table :columns="previewCols" :data-source="previewRows" :pagination="false" size="small" :scroll="{ x: true }" bordered />
      </template>
      <div v-else-if="previewError" class="pl-preview__err">{{ previewError }}</div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { message } from 'ant-design-vue'
import * as dsApi from '../../../api/datasource'
import * as plApi from '../../../api/pipelines'
import type { Pipeline, PipelineRun, PipelineSummary, PipelineConfig, ColumnMap, WriteMode, CastType } from '../../../api/pipelines'
import { listConnections, listTablesOfConnection, getConnectionTableSchema } from '../../../api/connection'
import type { Connection } from '../../../types/connection'
import type { DataSource } from '../../../types/datasource'

const STATUS_LABEL: Record<string, string> = {
  idle: '空闲', running: '运行中', stopped: '已停止', error: '错误', success: '成功', pending: '排队中',
}
const STATUS_COLOR: Record<string, string> = {
  running: '#10b981', success: '#10b981', idle: '#9ca3af',
  stopped: '#9ca3af', error: '#ef4444', pending: '#3b82f6',
}

const pipelines = ref<Pipeline[]>([])
const summary = ref<PipelineSummary>({
  total: 0, running: 0, success: 0, stopped: 0, error: 0, idle: 0, total_records_last_run: 0,
})
const activeRuns = reactive<Record<string, PipelineRun>>({})
const datasources = ref<DataSource[]>([])
const connections = ref<Connection[]>([])
const keyword = ref('')
const statusFilter = ref<string | undefined>(undefined)

const showEditor = ref(false)
const showDetail = ref(false)
const editing = ref<Pipeline | null>(null)
const detail = ref<Pipeline | null>(null)

const targetTables = ref<string[]>([])
const loadingTables = ref(false)
const loadingCols = ref(false)

const showPreview = ref(false)
const previewLoading = ref(false)
const previewError = ref('')
const previewData = ref<plApi.PipelinePreview | null>(null)

const form = reactive({
  name: '', description: '', source: '', target: '',
  datasource_id: undefined as string | undefined,
  stepsText: '抽取\n清洗\n本体映射',
  tags: '', schedule: '', step_duration_ms: 1500,
  engine: 'mock' as 'mock' | 'real',
  srcConn: undefined as string | undefined,
  srcQuery: '',
  tgtConn: undefined as string | undefined,
  tgtTable: undefined as string | undefined,
  writeMode: 'append' as WriteMode,
  upsertKeysText: '',
  columnMap: [] as ColumnMap[],
})

const statusOptions = [
  { value: undefined, label: '全部状态' },
  { value: 'idle', label: '空闲' },
  { value: 'running', label: '运行中' },
  { value: 'success', label: '成功' },
  { value: 'stopped', label: '已停止' },
  { value: 'error', label: '错误' },
]
const writeModeOptions = [
  { value: 'append', label: '追加（append）' },
  { value: 'upsert', label: '更新插入（upsert，按主键）' },
  { value: 'truncate_insert', label: '清空重写（truncate_insert）' },
]
const castOptions = [
  { value: '', label: '不转换' },
  { value: 'int', label: '整数 int' },
  { value: 'float', label: '小数 float' },
  { value: 'str', label: '文本 str' },
  { value: 'bool', label: '布尔 bool' },
]

const filtered = computed(() => pipelines.value)

const dsOptions = computed(() =>
  datasources.value.map((d) => ({
    value: d.id,
    label: `${d.name} (${(d as any).type || (d as any).engine || ''})`,
  }))
)

const dbConnOptions = computed(() =>
  connections.value
    .filter((c) => c.category === 'database')
    .map((c) => ({ value: c.id, label: `${c.name} (${c.type})${c.writable ? '' : ' · 只读'}` }))
)

const targetTableOptions = computed(() => targetTables.value.map((t) => ({ value: t, label: t })))

const runCols = computed(() => {
  const base = [
    { title: '状态', key: 'status', width: 80 },
    { title: '步骤', key: 'step', width: 120 },
  ]
  if (detail.value?.engine === 'real') {
    base.push({ title: '读取→写入', key: 'rw', width: 110 } as any)
    base.push({ title: '错误', key: 'error' } as any)
  } else {
    base.push({ title: '记录数', key: 'records', width: 90 } as any)
  }
  base.push({ title: '耗时', key: 'duration', width: 80 } as any)
  base.push({ title: '开始时间', key: 'started', width: 140 } as any)
  return base
})

const previewCols = computed(() =>
  (previewData.value?.columns || []).map((c) => ({ title: c, dataIndex: c, key: c, ellipsis: true }))
)
const previewRows = computed(() =>
  (previewData.value?.rows || []).map((r, ri) => {
    const obj: Record<string, unknown> = { __k: ri }
    ;(previewData.value?.columns || []).forEach((c, ci) => { obj[c] = r[ci] })
    return obj
  })
)

function fmtNum(v: number | string | undefined | null) {
  if (v == null || v === '' || isNaN(Number(v))) return '—'
  return Number(v).toLocaleString()
}
function fmtDur(ms?: number | null) {
  if (ms == null) return '—'
  if (ms < 1000) return ms + ' ms'
  return (ms / 1000).toFixed(1) + ' s'
}
function fmtDate(s?: string | null) {
  if (!s) return '—'
  const d = new Date(s)
  if (isNaN(d.getTime())) return s
  const p = (n: number) => (n < 10 ? '0' + n : '' + n)
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
function statusLabel(s: string) { return STATUS_LABEL[s] || s }
function statusColor(s: string) { return STATUS_COLOR[s] || '#9ca3af' }
function activeStatus(p: Pipeline) { return activeRuns[p.id]?.status || p.status }
function stepCount(p: Pipeline) { return (p.steps || []).length || 3 }
function writeModeLabel(m?: string) {
  return ({ append: '追加', upsert: '更新插入', truncate_insert: '清空重写' } as Record<string, string>)[m || 'append'] || (m || '追加')
}
function connName(id?: string | null) {
  if (!id) return '—'
  return connections.value.find((c) => c.id === id)?.name || id
}
function tagStyle(s: string) {
  const c = STATUS_COLOR[s] || '#9ca3af'
  return { background: c + '15', color: c, border: '1px solid ' + c + '30' }
}
function engineTagStyle(engine: string) {
  const real = engine === 'real'
  const c = real ? '#7c3aed' : '#9ca3af'
  return { background: c + '12', color: c, border: '1px solid ' + c + '30' }
}
function badgeStyle(color: string, _border: string, _bold: boolean) {
  return { color, border: '1px solid #e5e7eb', background: '#fff', fontWeight: 400 }
}
function stepBadgeStyle(p: Pipeline, idx: number) {
  const run = activeRuns[p.id]
  if (run && run.step_index === idx) return { color: '#10b981', border: '1px solid #10b981', background: '#fff', fontWeight: 600 }
  if (run && run.step_index > idx) return { color: '#10b981', border: '1px solid #a7f3d0', background: '#fff', fontWeight: 400 }
  return { color: '#9ca3af', border: '1px solid #e5e7eb', background: '#fff', fontWeight: 400 }
}
function dsName(id?: string | null) {
  if (!id) return ''
  const d = datasources.value.find((x) => x.id === id)
  return d?.name || id
}

async function refreshList() {
  try {
    const params: { keyword?: string; status?: string } = {}
    if (keyword.value) params.keyword = keyword.value
    if (statusFilter.value) params.status = statusFilter.value
    const res = await plApi.listPipelines(params)
    pipelines.value = res.items || []
    summary.value = res.summary
    const runs = await plApi.listActiveRuns()
    Object.keys(activeRuns).forEach((k) => delete activeRuns[k])
    ;(runs.items || []).forEach((r) => { activeRuns[r.pipeline_id] = r })
  } catch (e: any) {
    message.error('加载管线失败: ' + (e?.message || e))
  }
}

let pollTimer: number | null = null
function startPolling() {
  if (pollTimer) return
  const tick = async () => {
    await refreshList()
    const delay = Object.keys(activeRuns).length > 0 ? 800 : 1500
    pollTimer = window.setTimeout(tick, delay)
  }
  tick()
}
function stopPolling() {
  if (pollTimer) { clearTimeout(pollTimer); pollTimer = null }
}

let searchDebounce: number | null = null
watch(keyword, () => {
  if (searchDebounce) clearTimeout(searchDebounce)
  searchDebounce = window.setTimeout(refreshList, 250)
})
watch(statusFilter, refreshList)

function onEngineChange() {
  if (form.engine === 'real' && form.stepsText === '抽取\n清洗\n本体映射') {
    form.stepsText = '抽取\n转换\n加载'
  }
}

async function loadTargetTables() {
  targetTables.value = []
  if (!form.tgtConn) return
  loadingTables.value = true
  try {
    targetTables.value = await listTablesOfConnection(form.tgtConn)
  } catch (e: any) {
    message.error('拉取表失败: ' + (e?.response?.data?.detail || e?.message || e))
  } finally {
    loadingTables.value = false
  }
}
function onTgtConnChange() { form.tgtTable = undefined; loadTargetTables() }
function onTgtTableChange() { /* 选表后可点“拉取目标列自动生成” */ }

async function autoMapFromTarget() {
  if (!form.tgtConn || !form.tgtTable) { message.warning('先选目标连接与目标表'); return }
  loadingCols.value = true
  try {
    const schema = await getConnectionTableSchema(form.tgtConn, form.tgtTable)
    const cols = schema.columns || []
    form.columnMap = cols.map((c) => ({ from: c.name, to: c.name, cast: '' as CastType }))
    message.success(`已生成 ${cols.length} 条映射，可微调源列名与类型转换`)
  } catch (e: any) {
    message.error('拉取目标列失败: ' + (e?.response?.data?.detail || e?.message || e))
  } finally {
    loadingCols.value = false
  }
}

function resetForm() {
  Object.assign(form, {
    name: '', description: '', source: '', target: '',
    datasource_id: undefined, stepsText: '抽取\n清洗\n本体映射',
    tags: '', schedule: '', step_duration_ms: 1500,
    engine: 'mock', srcConn: undefined, srcQuery: '', tgtConn: undefined,
    tgtTable: undefined, writeMode: 'append', upsertKeysText: '', columnMap: [],
  })
  targetTables.value = []
}

function openCreate() {
  editing.value = null
  resetForm()
  showEditor.value = true
}

function openEdit(p: Pipeline) {
  editing.value = p
  const cfg: PipelineConfig = p.config_json || {}
  Object.assign(form, {
    name: p.name, description: p.description, source: p.source, target: p.target,
    datasource_id: p.datasource_id || undefined,
    stepsText: p.steps.join('\n'),
    tags: p.tags.join(','), schedule: p.schedule, step_duration_ms: p.step_duration_ms,
    engine: p.engine || 'mock',
    srcConn: cfg.source?.connection_id, srcQuery: cfg.source?.query || '',
    tgtConn: cfg.target?.connection_id, tgtTable: cfg.target?.table,
    writeMode: (cfg.target?.write_mode || 'append') as WriteMode,
    upsertKeysText: (cfg.upsert_keys || []).join(','),
    columnMap: (cfg.transform?.column_map || []).map((m) => ({ from: m.from, to: m.to, cast: (m.cast || '') as CastType })),
  })
  if (form.tgtConn) loadTargetTables()
  showEditor.value = true
}

async function openDetail(p: Pipeline) {
  try {
    const full = await plApi.getPipeline(p.id)
    detail.value = full
    showDetail.value = true
  } catch (e: any) {
    message.error('加载失败: ' + (e?.message || e))
  }
}

async function openPreview(p: Pipeline) {
  showPreview.value = true
  previewLoading.value = true
  previewError.value = ''
  previewData.value = null
  try {
    previewData.value = await plApi.previewPipeline(p.id, 20)
  } catch (e: any) {
    previewError.value = e?.response?.data?.detail || e?.message || String(e)
  } finally {
    previewLoading.value = false
  }
}

function buildConfig(): PipelineConfig {
  if (form.engine !== 'real') return {}
  return {
    source: { connection_id: form.srcConn, query: form.srcQuery.trim() },
    transform: { column_map: form.columnMap.filter((m) => m.from && m.to) },
    target: { connection_id: form.tgtConn, table: form.tgtTable, write_mode: form.writeMode },
    upsert_keys: form.writeMode === 'upsert'
      ? form.upsertKeysText.split(',').map((s) => s.trim()).filter(Boolean)
      : [],
  }
}

async function handleSave() {
  if (!form.name.trim()) { message.warning('请输入管线名称'); return }
  const steps = form.stepsText.split(/\r?\n/).map((s) => s.trim()).filter(Boolean)
  if (steps.length === 0) { message.warning('至少需要一个步骤'); return }
  const dur = Number(form.step_duration_ms)
  if (!Number.isFinite(dur) || dur < 100 || dur > 60000) { message.warning('单步耗时范围 100~60000'); return }
  if (form.engine === 'real') {
    if (!form.srcConn || !form.srcQuery.trim()) { message.warning('真实引擎需填写源连接与抽取 SQL'); return }
    if (!form.tgtConn || !form.tgtTable) { message.warning('真实引擎需选择目标连接与目标表'); return }
    if (form.writeMode === 'upsert' && !form.upsertKeysText.trim()) { message.warning('upsert 模式需填写主键列'); return }
  }
  const tags = form.tags.split(',').map((s) => s.trim()).filter(Boolean)
  const payload: plApi.PipelinePayload = {
    name: form.name.trim(), description: form.description, source: form.source,
    target: form.target, datasource_id: form.datasource_id || null, steps, tags,
    schedule: form.schedule, step_duration_ms: dur,
    engine: form.engine, config_json: buildConfig(),
  }
  try {
    if (editing.value) {
      await plApi.updatePipeline(editing.value.id, payload)
      message.success('管线已更新')
    } else {
      await plApi.createPipeline(payload)
      message.success('管线已创建')
    }
    showEditor.value = false
    await refreshList()
  } catch (e: any) {
    message.error('保存失败: ' + (e?.response?.data?.detail || e?.message || e))
  }
}

async function runPipeline(p: Pipeline) {
  try {
    await plApi.runPipeline(p.id)
    message.success(p.engine === 'real' ? '真实 ETL 已开始执行' : '管线已开始执行')
    await refreshList()
  } catch (e: any) {
    message.error('启动失败: ' + (e?.response?.data?.detail || e?.message || e))
  }
}

async function stopPipeline(p: Pipeline) {
  try {
    await plApi.stopPipeline(p.id)
    message.success('已停止')
    await refreshList()
  } catch (e: any) {
    message.error('停止失败: ' + (e?.response?.data?.detail || e?.message || e))
  }
}

async function deletePipeline(p: Pipeline) {
  try {
    await plApi.deletePipeline(p.id)
    message.success('管线已删除')
    await refreshList()
  } catch (e: any) {
    message.error('删除失败: ' + (e?.response?.data?.detail || e?.message || e))
  }
}

onMounted(async () => {
  try {
    const r = await dsApi.listDataSources()
    datasources.value = Array.isArray(r) ? r : ((r as any).items || [])
  } catch (e) { /* ignore */ }
  try {
    connections.value = await listConnections()
  } catch (e) { /* ignore */ }
  startPolling()
})
onBeforeUnmount(stopPolling)
</script>

<style scoped>
.pl-tab { display: flex; flex-direction: column; gap: 16px; }

.pl-header {
  display: flex; align-items: flex-start; justify-content: space-between;
  flex-wrap: wrap; gap: 16px;
  background: #fff; border: 1px solid var(--neutral-100); border-radius: var(--radius-xl);
  padding: 16px 20px; box-shadow: var(--shadow-xs);
}
.pl-stats { display: flex; gap: 32px; align-items: center; flex-wrap: wrap; }
.pl-stat { min-width: 80px; }
.pl-stat__lbl { font-size: 12px; color: var(--neutral-600); }
.pl-stat__num { font-size: 22px; font-weight: 700; margin-top: 2px; }
.pl-toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }

.pl-empty {
  text-align: center; padding: 60px 20px; color: var(--neutral-500);
  background: #fff; border: 1px dashed var(--neutral-300); border-radius: 10px;
}
.pl-empty--small { padding: 36px; border-style: solid; border-color: var(--neutral-200); }
.pl-empty__title { font-size: 15px; margin-bottom: 8px; color: var(--neutral-800); font-weight: 600; }
.pl-empty__sub { font-size: 13px; margin-bottom: 20px; }

.pl-list { display: flex; flex-direction: column; gap: 10px; }
.pl-card {
  display: flex; align-items: flex-start; justify-content: space-between; gap: 16px;
  padding: 14px 18px; background: #fff;
  border: 1px solid var(--neutral-100); border-left: 3px solid #9ca3af;
  border-radius: 8px; box-shadow: var(--shadow-xs);
  transition: box-shadow var(--transition-fast);
}
.pl-card:hover { box-shadow: var(--shadow-sm); }
.pl-card__body { flex: 1; min-width: 0; }
.pl-card__head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.pl-card__name { font-weight: 600; font-size: 14px; color: var(--neutral-900); }
.pl-card__meta { font-size: 12px; color: var(--neutral-600); }
.pl-card__actions { display: flex; gap: 6px; flex-shrink: 0; flex-wrap: wrap; justify-content: flex-end; }

.pl-tag {
  display: inline-block; padding: 1px 8px; border-radius: 4px;
  font-size: 11px; line-height: 1.6;
}
.pl-steps { display: flex; align-items: center; flex-wrap: wrap; gap: 0; }
.pl-step {
  padding: 2px 8px; font-size: 12px;
  border: 1px solid var(--neutral-200); border-radius: 4px; background: #fff;
}
.pl-arrow { color: var(--neutral-300); margin: 0 6px; font-size: 11px; }

.pl-progress {
  margin-top: 8px; max-width: 480px; height: 6px;
  background: var(--neutral-100); border-radius: 3px; overflow: hidden;
}
.pl-progress__bar { height: 100%; background: #10b981; transition: width 0.3s; }

.pl-lastrun {
  margin-top: 8px; padding: 6px 12px; background: #f0fdf4; border-radius: 6px;
  border: 1px solid #bbf7d0; font-size: 12px; display: inline-flex;
}
.pl-lastrun--real { background: #f5f3ff; border-color: #ddd6fe; }

.pl-help { font-size: 11px; color: var(--neutral-500); margin-top: 4px; }
.pl-section-title {
  font-size: 13px; font-weight: 600; color: var(--neutral-800);
  margin: 8px 0 10px; padding-bottom: 6px; border-bottom: 1px solid var(--neutral-100);
  display: flex; align-items: center;
}

.pl-map { border: 1px solid var(--neutral-100); border-radius: 6px; padding: 10px; background: var(--neutral-50); }
.pl-map__head, .pl-map__row {
  display: grid; grid-template-columns: 1fr 1fr 120px 40px; gap: 8px; align-items: center;
}
.pl-map__head { font-size: 11px; color: var(--neutral-500); margin-bottom: 6px; }
.pl-map__row { margin-bottom: 6px; }

.pl-detail__grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 20px; }
.pl-detail__lbl { font-size: 11px; color: var(--neutral-600); margin-bottom: 2px; }
.pl-detail__val { font-size: 13px; color: var(--neutral-900); word-break: break-all; }
.pl-detail__desc {
  margin-bottom: 20px; padding: 12px; background: var(--neutral-50);
  border-radius: 6px; font-size: 13px; color: var(--neutral-700); line-height: 1.6;
}
.pl-detail__section { margin-bottom: 20px; }
.pl-detail__title { font-size: 13px; font-weight: 600; margin-bottom: 8px; color: var(--neutral-800); }
.pl-detail__steps { display: flex; flex-wrap: wrap; gap: 6px; }
.pl-detail__stepchip {
  padding: 4px 10px; background: var(--neutral-100); border-radius: 4px;
  font-size: 12px; color: var(--neutral-700);
}
.pl-detail__empty { color: var(--neutral-500); font-size: 12px; padding: 20px; text-align: center; }

.pl-preview__meta { font-size: 12px; color: var(--neutral-600); margin-bottom: 12px; }
.pl-preview__err { color: #ef4444; font-size: 13px; padding: 12px; }
</style>
