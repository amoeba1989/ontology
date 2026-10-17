<template>
  <div class="mil">
    <header class="mil__head">
      <div>
        <h1 class="mil__title">{{ cfg.title }}</h1>
        <p class="mil__desc">{{ cfg.desc }}</p>
      </div>
      <button class="mil__btn mil__btn--ghost" :disabled="loading" @click="loadAll">{{ loading ? '加载…' : '刷新态势' }}</button>
    </header>

    <div class="mil__stats">
      <div class="mil__stat"><span class="mil__stat-num">{{ ov?.targets_total ?? '-' }}</span><span class="mil__stat-label">在踪目标</span></div>
      <div class="mil__stat mil__stat--danger"><span class="mil__stat-num">{{ ov?.hostile_targets ?? '-' }}</span><span class="mil__stat-label">敌对目标</span></div>
      <div class="mil__stat"><span class="mil__stat-num">{{ ov ? `${ov.active_sensors}/${ov.sensors_total}` : '-' }}</span><span class="mil__stat-label">在役传感器</span></div>
      <div class="mil__stat"><span class="mil__stat-num">{{ ov?.events_total ?? '-' }}</span><span class="mil__stat-label">行为事件</span></div>
      <div class="mil__stat mil__stat--danger"><span class="mil__stat-num">{{ ov?.hostile_assessments ?? '-' }}</span><span class="mil__stat-label">敌对研判</span></div>
      <div class="mil__stat"><span class="mil__stat-num mil__stat-num--sm">{{ ov?.latest_update ?? '-' }}</span><span class="mil__stat-label">最新情报</span></div>
    </div>

    <div class="mil__body">
      <aside class="mil__list">
        <h2 class="mil__list-title">目标清单</h2>
        <div
          v-for="t in targets"
          :key="t.target_id"
          class="mil__tcard"
          :class="{ 'mil__tcard--active': t.target_id === selectedId }"
          @click="select(t.target_id)"
        >
          <div class="mil__tcard-head">
            <span class="mil__tcard-name">{{ t.name }}</span>
            <span class="mil__badge" :class="`mil__badge--${t.threat_level}`">{{ t.threat_level }}</span>
          </div>
          <div class="mil__tcard-meta">{{ t.target_type }} · {{ t.last_known_location }} · {{ t.speed_knots }} {{ cfg.speedUnit }}</div>
          <div class="mil__tcard-meta">事件 {{ t.event_count }} · {{ t.updated_at }}</div>
          <div class="mil__tcard-ooda">
            <span
              v-for="(st, i) in OODA_STEPS"
              :key="st.key"
              class="mil__mini-dot"
              :class="miniClass(t.ooda_stage, i)"
              :title="st.label"
            ></span>
            <span v-if="t.ooda_stage === 'closed'" class="mil__mini-closed">闭环</span>
          </div>
        </div>
        <div v-if="!targets.length" class="mil__empty">暂无目标数据</div>
      </aside>

      <section v-if="sit" class="mil__detail">
        <div class="mil__seats">
          <button
            v-for="s in SEATS"
            :key="s.key"
            class="mil__seat"
            :class="{ 'mil__seat--active': seat === s.key }"
            @click="seat = s.key"
          >{{ s.label }}</button>
        </div>

        <div v-show="seat === 'intel'" class="mil__pane">
          <h3 class="mil__h3">目标档案</h3>
          <div class="mil__kv">
            <div><label>编号</label><span>{{ sit.target.target_id }}</span></div>
            <div><label>名称</label><span>{{ sit.target.name }}</span></div>
            <div><label>类型</label><span>{{ sit.target.target_type }}</span></div>
            <div><label>威胁等级</label><span class="mil__badge" :class="`mil__badge--${sit.target.threat_level}`">{{ sit.target.threat_level }}</span></div>
            <div><label>位置</label><span>{{ sit.target.last_known_location }}</span></div>
            <div><label>速度/航向</label><span>{{ sit.target.speed_knots }} {{ cfg.speedUnit }} / {{ sit.target.heading_deg }}°</span></div>
            <div><label>情报更新</label><span>{{ sit.target.updated_at }}</span></div>
            <div><label>高置信事件</label><span>{{ sit.high_confidence_events.length }} 条</span></div>
          </div>

          <h3 class="mil__h3">行为证据（{{ sit.events.length }}）</h3>
          <div v-if="!sit.events.length" class="mil__empty">暂无行为事件</div>
          <div v-for="e in sit.events" :key="e.event_id" class="mil__ev" :class="{ 'mil__ev--effect': e.event_type === '处置效果' }">
            <div class="mil__ev-head">
              <span class="mil__ev-type">{{ e.event_type }}</span>
              <span class="mil__conf" :class="{ 'mil__conf--high': e.confidence >= 0.8 }">置信度 {{ e.confidence }}</span>
            </div>
            <div class="mil__ev-desc">{{ e.description }}</div>
            <div class="mil__ev-time">{{ e.observed_at }}</div>
          </div>

          <h3 class="mil__h3">传感器覆盖</h3>
          <div class="mil__sensors">
            <div v-for="s in sit.sensors" :key="s.sensor_id" class="mil__sensor" :class="{ 'mil__sensor--off': !s.is_active }">
              <span class="mil__sensor-name">{{ s.name }}</span>
              <span class="mil__sensor-meta">{{ s.sensor_type }} · 覆盖 {{ s.coverage_radius_km }} km · {{ s.is_active ? '在役' : '停用' }}</span>
            </div>
          </div>
        </div>

        <div v-show="seat === 'analyst'" class="mil__pane">
          <div class="mil__subtabs">
            <button class="mil__subtab" :class="{ 'mil__subtab--active': analystSub === 'rules' }" @click="analystSub = 'rules'">规则命中</button>
            <button class="mil__subtab" :class="{ 'mil__subtab--active': analystSub === 'agent' }" @click="analystSub = 'agent'">智能体研判</button>
          </div>

          <div v-show="analystSub === 'rules'">
            <p class="mil__hint">对当前目标最新研判（{{ currentAssessId || '无' }}）逐条评估结构化业务规则</p>
            <div v-for="r in structuredRules" :key="r.id" class="mil__rule">
              <div class="mil__rule-head">
                <span class="mil__rule-name">{{ r.name }}</span>
                <button class="mil__btn" :disabled="!currentAssessId || !!evalRunning[r.id]" @click="evalRule(r)">{{ evalRunning[r.id] ? '评估中…' : '评估' }}</button>
              </div>
              <div class="mil__rule-desc">{{ r.description }}</div>
              <div v-if="evalResults[r.id]" class="mil__rule-res" :class="{ 'mil__rule-res--hit': evalResults[r.id].triggered }">
                {{ evalResults[r.id].triggered ? '命中' : '未命中' }} · 匹配 {{ evalResults[r.id].matched_count }}/{{ evalResults[r.id].total_count }} · 置信度 {{ evalResults[r.id].confidence }}
                <ul class="mil__conds">
                  <li v-for="(c, ci) in evalResults[r.id].conditions" :key="ci" :class="{ 'mil__cond--ok': c.matched }">
                    {{ c.display }} {{ c.operator }} {{ c.expected }} → 实际 {{ c.actual }}（{{ c.matched ? '满足' : '不满足' }}）
                  </li>
                </ul>
              </div>
            </div>
            <div v-if="!structuredRules.length" class="mil__empty">暂无结构化规则</div>
          </div>

          <div v-show="analystSub === 'agent'">
            <div class="mil__agent-bar">
              <input v-model="agentQuestion" class="mil__input" :placeholder="`询问智能体，默认针对 ${selectedId || '当前目标'}`" @keydown.enter="askAgent" />
              <button class="mil__btn mil__btn--primary" :disabled="streaming || !agentId" @click="askAgent">{{ streaming ? '研判中…' : '智能体研判' }}</button>
            </div>
            <div ref="agentOutRef" class="mil__agent-out">
              <div v-if="agentTrace" class="mil__trace" v-html="renderMarkdown(agentTrace)"></div>
              <div v-if="agentAnswer" class="mil__answer" v-html="renderMarkdown(agentAnswer)"></div>
              <div v-if="!agentTrace && !agentAnswer && !streaming" class="mil__empty">
                点击「智能体研判」，由目标行为研判智能体结合本体数据与业务规则给出 OODA 处置建议
              </div>
            </div>
          </div>
        </div>

        <div v-show="seat === 'command'" class="mil__pane">
          <p class="mil__hint">汇总研判结论与规则命中，由指挥员确认威胁等级并选定处置行动</p>
          <div v-if="!sit.assessments.length" class="mil__empty">暂无研判结论，请先在研判席完成研判（规则命中或智能体研判）</div>
          <template v-else>
            <div class="mil__sum">
              <span class="mil__sum-label">最新研判</span>
              威胁判定 <b>{{ latestAssessment?.threat_assessment }}</b>
              · OODA {{ latestAssessment?.ooda_phase }}
              · 建议动作 <b>{{ latestAssessment?.recommended_action }}</b>
              <span class="mil__sum-meta">{{ latestAssessment?.assessed_by }} · {{ latestAssessment?.assessed_at }}</span>
            </div>
            <div class="mil__kv mil__kv--form">
              <div>
                <label>确认威胁等级</label>
                <select v-model="dForm.confirmed_threat" class="mil__select">
                  <option value="friendly">friendly（友方）</option>
                  <option value="unknown">unknown（不明）</option>
                  <option value="hostile">hostile（敌对）</option>
                  <option value="critical">critical（严重威胁）</option>
                </select>
              </div>
              <div>
                <label>选定处置行动</label>
                <select v-model="dForm.selected_action_id" class="mil__select">
                  <option value="">（待定）</option>
                  <option v-for="a in actions" :key="a.id" :value="a.id">{{ a.name }}</option>
                </select>
              </div>
              <div>
                <label>指挥员</label>
                <input v-model="dForm.decided_by" class="mil__input" />
              </div>
            </div>
            <div class="mil__order">
              <label>处置指令</label>
              <textarea v-model="dForm.order_text" class="mil__input" :rows="2" :placeholder="autoOrder"></textarea>
            </div>
            <div class="mil__order-ops">
              <button class="mil__btn mil__btn--primary" :disabled="decisionSaving" @click="saveDecision">
                {{ decisionSaving ? '提交中…' : '生成处置指令' }}
              </button>
            </div>
            <div v-if="latestDecision" class="mil__decision">
              ⚡ 指令 {{ latestDecision.decision_id }} 已下达 · 威胁 {{ latestDecision.confirmed_threat }}
              · 行动 {{ latestDecision.selected_action_name || '待定' }}
              · {{ latestDecision.decided_by }} {{ latestDecision.decided_at }}
            </div>
          </template>
        </div>

        <div v-show="seat === 'action'" class="mil__pane">
          <p class="mil__hint">执行指挥席选定的行动；执行后回填效果（Assess），驱动 OODA 闭环</p>
          <div v-if="latestDecision" class="mil__decision">
            ⚡ 执行指令 {{ latestDecision.decision_id }} · 选定行动：{{ latestDecision.selected_action_name || '待定' }}
          </div>
          <div v-for="a in actions" :key="a.id" class="mil__act" :class="{ 'mil__act--chosen': a.id === latestDecision?.selected_action_id }">
            <div class="mil__act-head">
              <span class="mil__act-name">⚡ {{ a.name }}<span v-if="a.id === latestDecision?.selected_action_id" class="mil__act-chosen-tag"> 指令选定</span></span>
              <button class="mil__btn mil__btn--primary" :disabled="!!actRunning[a.id]" @click="runAction(a)">{{ actRunning[a.id] ? '执行中…' : '执行' }}</button>
            </div>
            <div class="mil__act-desc">{{ a.description }}</div>
            <div class="mil__act-params">参数：{{ actParams(a) }}</div>
            <div v-if="actResults[a.id]" class="mil__act-result">{{ actResults[a.id] }}</div>
            <div v-if="isActionSuccess(a.id)" class="mil__effect">
              <div class="mil__effect-label">效果回填（Assess → Observe）</div>
              <input v-model="effectText" class="mil__input" placeholder="如：目标转向离开管控区，威胁解除" />
              <div class="mil__effect-ops">
                <select v-model="effectThreat" class="mil__select">
                  <option :value="null">威胁等级不变</option>
                  <option value="friendly">调整为 friendly</option>
                  <option value="unknown">调整为 unknown</option>
                  <option value="hostile">调整为 hostile</option>
                  <option value="critical">调整为 critical</option>
                </select>
                <button class="mil__btn" :disabled="effectSaving" @click="submitEffect">{{ effectSaving ? '回填中…' : '回填效果' }}</button>
              </div>
            </div>
          </div>
          <div v-if="!actions.length" class="mil__empty">暂无可执行行动</div>
          <h3 v-if="sit.effects.length" class="mil__h3">已回填效果（{{ sit.effects.length }}）</h3>
          <div v-for="e in sit.effects" :key="e.event_id" class="mil__ev mil__ev--effect">
            <div class="mil__ev-head"><span class="mil__ev-type">{{ e.event_type }}</span></div>
            <div class="mil__ev-desc">{{ e.description }}</div>
            <div class="mil__ev-time">{{ e.observed_at }}</div>
          </div>
        </div>
      </section>
      <section v-else class="mil__detail"><div class="mil__empty">选择左侧目标查看态势</div></section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { marked } from 'marked'
import { sceneDataApi, type MilOverview, type MilSituation, type MilTarget } from '../../api/military'
import { ruleApi, type RuleEvaluateResult } from '../../api/rules'
import { actionApi, type ActionItem } from '../../api/actions'
import { agentsApi } from '../../api/agents'

export interface SceneWorkbenchConfig {
  apiPrefix: string
  title: string
  desc: string
  agentName: string
  speedUnit: string
}

const props = defineProps<{ config: SceneWorkbenchConfig }>()
const cfg = props.config

const api = sceneDataApi(cfg.apiPrefix)

const OODA_STEPS = [
  { key: 'observe', label: '观察' },
  { key: 'orient', label: '判断' },
  { key: 'decide', label: '决策' },
  { key: 'act', label: '行动' },
]

const SEATS = [
  { key: 'intel', label: '情报席 · 观察' },
  { key: 'analyst', label: '研判席 · 判断' },
  { key: 'command', label: '指挥席 · 决策' },
  { key: 'action', label: '行动席 · 行动' },
]

const SEAT_BY_STAGE: Record<string, string> = {
  observe: 'intel',
  orient: 'analyst',
  decide: 'command',
  act: 'action',
}

const loading = ref(false)
const ov = ref<MilOverview | null>(null)
const targets = ref<MilTarget[]>([])
const selectedId = ref('')
const sit = ref<MilSituation | null>(null)
const seat = ref('intel')
const analystSub = ref<'rules' | 'agent'>('rules')

const rules = ref<any[]>([])
const evalResults = reactive<Record<string, RuleEvaluateResult>>({})
const evalRunning = reactive<Record<string, boolean>>({})

const actions = ref<ActionItem[]>([])
const actRunning = reactive<Record<string, boolean>>({})
const actResults = reactive<Record<string, string>>({})

const dForm = reactive({
  confirmed_threat: 'unknown',
  selected_action_id: '',
  order_text: '',
  decided_by: '指挥员',
})
const decisionSaving = ref(false)

const effectText = ref('')
const effectThreat = ref<string | null>(null)
const effectSaving = ref(false)

const agentId = ref('')
const agentQuestion = ref('')
const agentTrace = ref('')
const agentAnswer = ref('')
const streaming = ref(false)
const agentOutRef = ref<HTMLElement | null>(null)

const structuredRules = computed(() => rules.value.filter((r) => Array.isArray(r.conditions_json) && r.conditions_json.length))
const currentAssessId = computed(() => sit.value?.assessments[0]?.assessment_id || '')
const latestAssessment = computed(() => sit.value?.assessments[0] || null)
const latestDecision = computed(() => sit.value?.decisions?.[0] || null)

const selectedActionName = computed(() => actions.value.find((a) => a.id === dForm.selected_action_id)?.name || '')
const autoOrder = computed(() =>
  `对目标「${sit.value?.target.name || ''}」执行「${selectedActionName.value || '待定行动'}」，按确认后威胁等级组织处置。`,
)

function miniClass(stage: string | undefined, i: number): string {
  if (!stage) return ''
  const idx = stage === 'closed' ? OODA_STEPS.length : OODA_STEPS.findIndex((x) => x.key === stage)
  if (idx < 0) return ''
  if (i < idx || idx === OODA_STEPS.length) return 'is-done'
  if (i === idx) return 'is-current'
  return ''
}

function isActionSuccess(actionId: string): boolean {
  return (actResults[actionId] || '').startsWith('执行成功')
}

function renderMarkdown(text: string): string {
  return marked.parse(text || '', { async: false }) as string
}

async function loadAll() {
  loading.value = true
  try {
    const [o, list] = await Promise.all([api.overview(), api.targets()])
    ov.value = o
    targets.value = list
    if (!selectedId.value && list.length) await select(list[0].target_id)
    else if (selectedId.value) await select(selectedId.value)
  } finally {
    loading.value = false
  }
}

async function select(id: string) {
  selectedId.value = id
  sit.value = await api.situation(id)
  for (const k of Object.keys(evalResults)) delete evalResults[k]
  for (const k of Object.keys(actResults)) delete actResults[k]
  effectText.value = ''
  effectThreat.value = null
  dForm.confirmed_threat = sit.value.target.threat_level || 'unknown'
  dForm.selected_action_id = ''
  dForm.order_text = ''
  // 按目标当前 OODA 阶段自动定位到对应席位
  seat.value = SEAT_BY_STAGE[sit.value.ooda_stage] || 'intel'
  if (sit.value.ooda_stage === 'closed') seat.value = 'intel'
  if (seat.value === 'analyst') analystSub.value = 'rules'
}

async function saveDecision() {
  if (!currentAssessId.value) {
    message.warning('暂无研判结论，请先在研判席完成研判')
    return
  }
  decisionSaving.value = true
  try {
    await api.createDecision(selectedId.value, {
      assessment_id: currentAssessId.value,
      confirmed_threat: dForm.confirmed_threat,
      selected_action_id: dForm.selected_action_id || null,
      selected_action_name: selectedActionName.value || null,
      order_text: dForm.order_text.trim() || autoOrder.value,
      decided_by: dForm.decided_by.trim() || '指挥员',
    })
    message.success('处置指令已生成，可转行动席执行')
    await select(selectedId.value)
  } finally {
    decisionSaving.value = false
  }
}

async function evalRule(r: any) {
  if (!currentAssessId.value) return
  evalRunning[r.id] = true
  try {
    evalResults[r.id] = await ruleApi.evaluate(r.id, currentAssessId.value)
  } catch (e: any) {
    evalResults[r.id] = {
      rule_id: r.id, rule_name: r.name, triggered: false,
      matched_count: 0, total_count: 0, confidence: 0,
      conditions: [], risk_level: null,
      ...({ error: e?.message } as any),
    }
  } finally {
    evalRunning[r.id] = false
  }
}

function actParams(a: ActionItem): string {
  return Object.entries(buildParams(a)).map(([k, v]) => `${k}=${v}`).join('，') || '无'
}

function buildParams(a: ActionItem): Record<string, any> {
  const latest = sit.value?.assessments[0]
  const declared = (a.parameters_json || []).map((p) => p.name)
  const pool: Record<string, any> = {
    target_id: selectedId.value,
    threat_level: sit.value?.target.threat_level,
    assessment_id: latest?.assessment_id,
    threat_assessment: latest?.threat_assessment,
  }
  if (!declared.length) return pool
  const out: Record<string, any> = {}
  for (const name of declared) if (name in pool) out[name] = pool[name]
  return out
}

async function runAction(a: ActionItem) {
  actRunning[a.id] = true
  actResults[a.id] = ''
  try {
    const res = await actionApi.execute(a.id, buildParams(a), false)
    actResults[a.id] = res.success ? `执行成功：${res.message}` : `执行失败：${res.message}`
    if (res.success) effectText.value = `${a.name} 已执行，`
  } catch (e: any) {
    actResults[a.id] = `执行异常：${e?.message || e}`
  } finally {
    actRunning[a.id] = false
  }
}

async function submitEffect() {
  if (!effectText.value.trim()) {
    message.warning('请填写处置效果说明')
    return
  }
  effectSaving.value = true
  try {
    await api.submitEffect(selectedId.value, {
      decision_id: latestDecision.value?.decision_id || null,
      effect_description: effectText.value.trim(),
      new_threat: effectThreat.value || null,
    })
    message.success('效果已回填，OODA 闭环完成')
    await loadAll()
  } finally {
    effectSaving.value = false
  }
}

async function askAgent() {
  if (!agentId.value || streaming.value) return
  const q = agentQuestion.value.trim() || `研判 ${selectedId.value} 对应目标的威胁等级与处置建议`
  agentQuestion.value = ''
  agentTrace.value = ''
  agentAnswer.value = ''
  streaming.value = true
  let content = ''
  try {
    const response = await fetch(`/api/v1/agents/${agentId.value}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q }),
    })
    const reader = response.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const data = line.slice(6)
        if (data === '[DONE]') continue
        try {
          const evt = JSON.parse(data)
          if (evt.type === 'token' || evt.type === 'content') content += evt.content
          else if (evt.type === 'answer') content = evt.content
          else if (evt.type === 'tool_result') content += `\n> 🔧 ${evt.tool || ''}：${evt.summary || ''}\n`
        } catch { /* skip */ }
      }
      agentTrace.value = content
      await nextTick()
      if (agentOutRef.value) agentOutRef.value.scrollTop = agentOutRef.value.scrollHeight
    }
    const m = content.match(/```json\s*([\s\S]*?)```/)
    if (m) {
      try {
        const obj = JSON.parse(m[1])
        if (obj && typeof obj.answer === 'string') {
          agentAnswer.value = obj.answer
          agentTrace.value = content.slice(0, m.index).trim()
        } else {
          agentAnswer.value = content
          agentTrace.value = ''
        }
      } catch {
        agentAnswer.value = content
        agentTrace.value = ''
      }
    } else {
      agentAnswer.value = content
      agentTrace.value = ''
    }
  } finally {
    streaming.value = false
  }
}

onMounted(async () => {
  await loadAll()
  const [rs, acts, agents] = await Promise.all([ruleApi.list(), actionApi.list(), agentsApi.list()])
  rules.value = rs as any[]
  actions.value = acts
  const hit = agents.find((a) => a.name === cfg.agentName) || agents[0]
  if (hit) agentId.value = hit.id
})
</script>

<style scoped>
.mil { padding: 20px 24px; display: flex; flex-direction: column; gap: 16px; }
.mil__head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.mil__title { margin: 0; font-size: 20px; font-weight: 700; color: var(--text-primary, #111827); }
.mil__desc { margin: 4px 0 0; font-size: 13px; color: var(--text-secondary, #6b7280); }
.mil__stats { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; }
.mil__stat {
  background: var(--bg-card, #fff); border: 1px solid var(--border-primary, #e5e7eb);
  border-radius: 10px; padding: 12px 14px; display: flex; flex-direction: column; gap: 4px;
}
.mil__stat--danger .mil__stat-num { color: #dc2626; }
.mil__stat-num { font-size: 22px; font-weight: 700; color: var(--text-primary, #111827); }
.mil__stat-num--sm { font-size: 13px; font-weight: 600; line-height: 22px; }
.mil__stat-label { font-size: 12px; color: var(--text-secondary, #6b7280); }
.mil__body { display: grid; grid-template-columns: 300px 1fr; gap: 16px; align-items: start; }
.mil__list {
  background: var(--bg-card, #fff); border: 1px solid var(--border-primary, #e5e7eb);
  border-radius: 10px; padding: 12px; display: flex; flex-direction: column; gap: 8px;
}
.mil__list-title { margin: 0 0 4px; font-size: 14px; font-weight: 600; }
.mil__tcard {
  border: 1px solid var(--border-primary, #e5e7eb); border-radius: 8px;
  padding: 10px; cursor: pointer; transition: border-color 0.15s, background 0.15s;
}
.mil__tcard:hover { border-color: var(--semantic-400, #38bdf8); }
.mil__tcard--active { border-color: var(--semantic-600, #2563eb); background: var(--semantic-50, #eff6ff); }
.mil__tcard-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.mil__tcard-name { font-size: 13px; font-weight: 600; }
.mil__tcard-meta { font-size: 12px; color: var(--text-secondary, #6b7280); margin-top: 3px; }
.mil__tcard-ooda { display: flex; align-items: center; gap: 4px; margin-top: 6px; }
.mil__mini-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--neutral-200, #e5e7eb); }
.mil__mini-dot.is-done { background: #16a34a; }
.mil__mini-dot.is-current { background: #f59e0b; box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.25); }
.mil__mini-closed { font-size: 10px; color: #16a34a; font-weight: 600; margin-left: 2px; }
.mil__badge {
  font-size: 11px; padding: 1px 8px; border-radius: 999px; font-weight: 600;
  background: var(--neutral-100, #f3f4f6); color: var(--neutral-600, #4b5563);
}
.mil__badge--hostile, .mil__badge--critical { background: #fee2e2; color: #b91c1c; }
.mil__badge--unknown { background: #fef3c7; color: #b45309; }
.mil__badge--friendly { background: #dcfce7; color: #15803d; }
.mil__detail {
  background: var(--bg-card, #fff); border: 1px solid var(--border-primary, #e5e7eb);
  border-radius: 10px; padding: 12px 16px 16px; min-height: 480px;
}
.mil__seats { display: flex; gap: 6px; border-bottom: 1px solid var(--border-primary, #e5e7eb); margin-bottom: 12px; }
.mil__seat {
  border: none; background: transparent; padding: 8px 14px; font-size: 13px;
  color: var(--text-secondary, #6b7280); cursor: pointer; border-bottom: 2px solid transparent;
}
.mil__seat--active { color: var(--semantic-600, #2563eb); border-bottom-color: var(--semantic-600, #2563eb); font-weight: 600; }
.mil__subtabs { display: flex; gap: 6px; margin-bottom: 10px; }
.mil__subtab {
  border: 1px solid var(--border-primary, #e5e7eb); background: #fff; border-radius: 999px;
  padding: 4px 14px; font-size: 12px; color: var(--text-secondary, #6b7280); cursor: pointer;
}
.mil__subtab--active { background: var(--semantic-50, #eff6ff); border-color: var(--semantic-400, #38bdf8); color: var(--semantic-600, #2563eb); font-weight: 600; }
.mil__pane { display: flex; flex-direction: column; gap: 10px; }
.mil__h3 { margin: 6px 0 0; font-size: 14px; font-weight: 600; }
.mil__kv { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px 16px; }
.mil__kv > div { display: flex; flex-direction: column; gap: 2px; font-size: 13px; }
.mil__kv label { font-size: 11px; color: var(--text-tertiary, #9ca3af); }
.mil__kv--form { margin: 4px 0; }
.mil__select {
  border: 1px solid var(--border-primary, #e5e7eb); border-radius: 8px;
  padding: 6px 8px; font-size: 13px; background: #fff; outline: none;
}
.mil__select:focus { border-color: var(--semantic-400, #38bdf8); }
.mil__ev { border-left: 3px solid var(--semantic-300, #93c5fd); padding: 6px 10px; background: var(--neutral-50, #f9fafb); border-radius: 0 8px 8px 0; }
.mil__ev--effect { border-left-color: #16a34a; background: #f0fdf4; }
.mil__ev-head { display: flex; justify-content: space-between; gap: 8px; }
.mil__ev-type { font-size: 13px; font-weight: 600; }
.mil__conf { font-size: 12px; color: var(--text-secondary, #6b7280); }
.mil__conf--high { color: #b45309; font-weight: 600; }
.mil__ev-desc { font-size: 13px; margin-top: 2px; }
.mil__ev-time { font-size: 11px; color: var(--text-tertiary, #9ca3af); margin-top: 2px; }
.mil__sensors { display: flex; flex-direction: column; gap: 6px; }
.mil__sensor { display: flex; justify-content: space-between; gap: 8px; font-size: 13px; padding: 6px 10px; border: 1px solid var(--border-primary, #e5e7eb); border-radius: 8px; }
.mil__sensor--off { opacity: 0.55; }
.mil__sensor-meta { color: var(--text-secondary, #6b7280); font-size: 12px; }
.mil__hint { margin: 0; font-size: 12px; color: var(--text-secondary, #6b7280); }
.mil__sum {
  font-size: 13px; padding: 10px 12px; border-radius: 8px;
  background: var(--semantic-50, #eff6ff); border: 1px solid var(--semantic-100, #dbeafe);
}
.mil__sum-label { font-size: 11px; color: var(--semantic-600, #2563eb); font-weight: 600; margin-right: 8px; }
.mil__sum-meta { color: var(--text-tertiary, #9ca3af); font-size: 12px; margin-left: 8px; }
.mil__order { display: flex; flex-direction: column; gap: 4px; }
.mil__order label { font-size: 11px; color: var(--text-tertiary, #9ca3af); }
.mil__order-ops { display: flex; }
.mil__decision {
  font-size: 13px; padding: 10px 12px; border-radius: 8px;
  background: #fffbeb; border: 1px solid #fde68a; color: #92400e; font-weight: 500;
}
.mil__rule, .mil__act { border: 1px solid var(--border-primary, #e5e7eb); border-radius: 8px; padding: 10px 12px; }
.mil__act--chosen { border-color: #f59e0b; box-shadow: 0 0 0 1px rgba(245, 158, 11, 0.3); }
.mil__act-chosen-tag { font-size: 11px; color: #b45309; font-weight: 600; }
.mil__rule-head, .mil__act-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.mil__rule-name, .mil__act-name { font-size: 13px; font-weight: 600; }
.mil__rule-desc, .mil__act-desc { font-size: 12px; color: var(--text-secondary, #6b7280); margin-top: 4px; }
.mil__rule-res { margin-top: 8px; font-size: 12px; padding: 6px 10px; border-radius: 6px; background: var(--neutral-100, #f3f4f6); }
.mil__rule-res--hit { background: #fee2e2; color: #b91c1c; font-weight: 600; }
.mil__conds { margin: 6px 0 0; padding-left: 18px; font-weight: 400; color: var(--text-secondary, #4b5563); }
.mil__cond--ok { color: #15803d; }
.mil__act-params { font-size: 12px; color: var(--neutral-600, #4b5563); margin-top: 4px; }
.mil__act-result { font-size: 12px; margin-top: 6px; padding: 4px 8px; border-radius: 6px; background: var(--neutral-100, #f3f4f6); }
.mil__effect {
  margin-top: 8px; padding: 10px; border-radius: 8px;
  background: #f0fdf4; border: 1px dashed #86efac; display: flex; flex-direction: column; gap: 8px;
}
.mil__effect-label { font-size: 12px; font-weight: 600; color: #15803d; }
.mil__effect-ops { display: flex; gap: 8px; align-items: center; }
.mil__agent-bar { display: flex; gap: 8px; }
.mil__input {
  flex: 1; border: 1px solid var(--border-primary, #e5e7eb); border-radius: 8px;
  padding: 7px 10px; font-size: 13px; outline: none;
}
.mil__input:focus { border-color: var(--semantic-400, #38bdf8); }
.mil__agent-out {
  max-height: 460px; overflow-y: auto; font-size: 13px; line-height: 1.6;
  background: var(--neutral-50, #f9fafb); border-radius: 8px; padding: 10px 12px;
}
.mil__trace { white-space: pre-wrap; font-size: 12px; color: var(--neutral-500, #6b7280); border-left: 2px solid var(--neutral-300, #d1d5db); padding-left: 10px; margin-bottom: 8px; }
.mil__answer :deep(p) { margin: 6px 0; }
.mil__answer :deep(h2), .mil__answer :deep(h3) { margin: 10px 0 6px; font-weight: 600; }
.mil__answer :deep(h2) { font-size: 15px; }
.mil__answer :deep(h3) { font-size: 14px; }
.mil__answer :deep(ul), .mil__answer :deep(ol) { margin: 6px 0; padding-left: 20px; }
.mil__answer :deep(table) { border-collapse: collapse; margin: 8px 0; font-size: 12px; }
.mil__answer :deep(th), .mil__answer :deep(td) { border: 1px solid var(--neutral-300, #d1d5db); padding: 4px 8px; }
.mil__answer :deep(th) { background: var(--neutral-200, #e5e7eb); }
.mil__empty { font-size: 12px; color: var(--text-tertiary, #9ca3af); padding: 8px 0; }
.mil__btn {
  border: 1px solid var(--border-primary, #e5e7eb); background: #fff; border-radius: 8px;
  padding: 6px 14px; font-size: 13px; cursor: pointer;
}
.mil__btn:hover { background: var(--neutral-100, #f3f4f6); }
.mil__btn:disabled { opacity: 0.5; cursor: not-allowed; }
.mil__btn--ghost { border: none; background: transparent; }
.mil__btn--primary { background: var(--semantic-600, #2563eb); border-color: var(--semantic-600, #2563eb); color: #fff; }
.mil__btn--primary:hover { background: var(--semantic-700, #1d4ed8); }

/* ── 深色态覆盖：页内白底控件/彩色徐章/绿红 pills 随主题翻转 ── */
html[data-theme="dark"] .mil__subtab { background: var(--surface-card); }
html[data-theme="dark"] .mil__subtab--active { background: rgba(76,110,245,0.16); }
html[data-theme="dark"] .mil__select { background: var(--surface-card); color: var(--text-primary); }
html[data-theme="dark"] .mil__btn { background: var(--surface-card); }
html[data-theme="dark"] .mil__badge--hostile, html[data-theme="dark"] .mil__badge--critical { background: rgba(220,38,38,0.18); color: #ff8787; }
html[data-theme="dark"] .mil__badge--unknown { background: rgba(245,158,11,0.16); color: var(--kinetic-300); }
html[data-theme="dark"] .mil__badge--friendly { background: rgba(18,184,134,0.16); color: var(--dynamic-300); }
html[data-theme="dark"] .mil__stat--danger .mil__stat-num { color: #ff8787; }
html[data-theme="dark"] .mil__mini-closed { color: var(--dynamic-300); }
html[data-theme="dark"] .mil__ev--effect { background: rgba(18,184,134,0.1); }
html[data-theme="dark"] .mil__conf--high { color: var(--kinetic-300); }
html[data-theme="dark"] .mil__decision { background: rgba(245,158,11,0.12); border-color: rgba(245,158,11,0.4); color: var(--kinetic-300); }
html[data-theme="dark"] .mil__act-chosen-tag { color: var(--kinetic-300); }
html[data-theme="dark"] .mil__rule-res--hit { background: rgba(220,38,38,0.18); color: #ff8787; }
html[data-theme="dark"] .mil__cond--ok { color: var(--dynamic-300); }
html[data-theme="dark"] .mil__effect { background: rgba(18,184,134,0.1); border-color: rgba(134,239,172,0.4); }
html[data-theme="dark"] .mil__effect-label { color: var(--dynamic-300); }
</style>
