<template>
  <div class="skill-detail" v-if="skill">
    <div class="skill-detail__header">
      <div>
        <h1 class="skill-detail__title">{{ skill.name }}</h1>
        <p class="skill-detail__desc">{{ skill.description }}</p>
      </div>
      <div class="skill-detail__actions">
        <span class="skill-detail__badge" :class="'skill-detail__badge--' + skill.status">{{ statusLabel(skill.status) }}</span>
        <span class="skill-detail__version">v{{ skill.current_version }}</span>
        <button class="skill-detail__btn" @click="handleDeprecate" v-if="skill.status === 'active'">废弃</button>
      </div>
    </div>

    <div v-if="skill.skill_type === 'configured'" class="skill-detail__section skill-run">
      <h3>运行技能 · 查询真实数据库</h3>
      <p>受已发布应用约束；结果最多取样 20 行。也可在智能体问答中调用。</p>
      <label v-for="(property, name) in skill.input_schema?.properties || {}" :key="name">
        {{ name }}
        <select v-if="property.enum" v-model="params[name]"><option v-for="choice in property.enum" :key="choice">{{ choice }}</option></select>
        <input v-else v-model="params[name]" />
      </label>
      <button class="run-button" :disabled="running || skill.status !== 'active'" @click="executeSkill">{{ running ? '查询中…' : '运行技能' }}</button>
      <button class="run-button secondary" @click="router.push('/agent/manage')">进入智能体问答</button>
      <p v-if="runError" role="alert">{{ runError }}</p>
      <template v-if="runResult">
        <p :class="{ failure: !runResult.success }">{{ runResult.summary }}</p>
        <p>执行编号：{{ runResult.run_id }} · 应用版本：{{ runResult.release_number || '—' }}</p>
        <div v-if="runResult.data?.columns" class="result-scroll"><table><thead><tr><th v-for="column in runResult.data.columns" :key="column">{{ column }}</th></tr></thead>
          <tbody><tr v-for="(row, index) in runResult.data.rows" :key="index"><td v-for="(cell, ci) in row" :key="ci">{{ cell }}</td></tr></tbody></table></div>
        <pre v-else>{{ JSON.stringify(runResult.data, null, 2) }}</pre>
      </template>
      <h3>最近执行记录</h3>
      <p v-for="run in runs" :key="run.id">{{ new Date(run.created_at).toLocaleString() }} · {{ run.source.startsWith('agent:') ? '智能体问答' : run.source === 'workflow' ? '业务编排' : '技能运行' }} · {{ run.status === 'success' ? '成功' : '失败' }} · {{ run.result.summary }}</p>
    </div>

    <div class="skill-detail__section">
      <h3>输入参数</h3>
      <pre>{{ JSON.stringify(skill.input_schema, null, 2) }}</pre>
    </div>

    <div class="skill-detail__section">
      <h3>输出结构</h3>
      <pre>{{ JSON.stringify(skill.output_schema, null, 2) }}</pre>
    </div>

    <div class="skill-detail__section">
      <h3>Prompt 模板</h3>
      <pre class="skill-detail__prompt">{{ skill.prompt_template }}</pre>
    </div>

    <div class="skill-detail__section" v-if="skill.tools?.length">
      <h3>工具列表</h3>
      <div v-for="(tool, i) in skill.tools" :key="i" class="skill-detail__tool">
        <strong>{{ tool.name }}</strong> — {{ tool.description }}
        <pre class="skill-detail__code">{{ tool.code }}</pre>
      </div>
    </div>

    <div class="skill-detail__section" v-if="skill.test_cases?.length">
      <h3>测试用例</h3>
      <pre>{{ JSON.stringify(skill.test_cases, null, 2) }}</pre>
    </div>

    <div class="skill-detail__section">
      <h3>版本历史</h3>
      <div v-if="versions.length" class="skill-detail__versions">
        <div v-for="v in versions" :key="v.id" class="skill-detail__ver-item" :class="{ 'skill-detail__ver-item--current': v.version === skill.current_version }">
          <span class="skill-detail__ver-num">v{{ v.version }}</span>
          <span class="skill-detail__ver-log">{{ v.change_log || '无说明' }}</span>
          <span class="skill-detail__ver-time">{{ v.published_at?.slice(0, 16) }}</span>
          <button v-if="v.version !== skill.current_version" class="skill-detail__ver-rollback" @click="handleRollback(v.version)">回滚</button>
        </div>
      </div>
      <p v-else class="skill-detail__empty">暂无版本记录</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { skillsApi, type SkillItem, type VersionItem } from '../../../api/skills'

const route = useRoute()
const router = useRouter()
const skill = ref<SkillItem | null>(null)
const versions = ref<VersionItem[]>([])
const params = ref<Record<string, any>>({})
const runs = ref<any[]>([])
const running = ref(false)
const runError = ref('')
const runResult = ref<any>(null)
async function executeSkill() {
  if (!skill.value) return
  running.value = true; runError.value = ''
  try {
    runResult.value = await skillsApi.execute(skill.value.id, params.value)
    runs.value = await skillsApi.runs(skill.value.id)
  } catch (e: any) { runError.value = e.response?.data?.detail || '技能运行失败' }
  finally { running.value = false }
}

function statusLabel(status: string) {
  const map: Record<string, string> = { active: '生效', draft: '草稿', deprecated: '已废弃' }
  return map[status] || status
}

async function load() {
  const id = route.params.id as string
  skill.value = await skillsApi.get(id)
  versions.value = await skillsApi.versions(id)
  if (skill.value?.skill_type === 'configured') {
    params.value = { ...(skill.value.test_cases?.[0]?.params || {}) }
    runs.value = await skillsApi.runs(id)
  }
}

async function handleDeprecate() {
  if (!skill.value || !confirm('确定要废弃该技能吗？')) return
  await skillsApi.deprecate(skill.value.id)
  await load()
}

async function handleRollback(version: number) {
  if (!skill.value || !confirm(`确定回滚到 v${version} 吗？`)) return
  await skillsApi.rollback(skill.value.id, version)
  await load()
}

onMounted(load)
</script>

<style scoped>
.skill-run { padding: 20px; border: 1px solid #c6d8eb; border-radius: 12px; background: #f6faff; }
.skill-run p { font-size: 12px; color: #4b5969; margin: 12px 0; }
.skill-run label { display: block; margin: 12px 0; }
.skill-run select, .skill-run input { padding: 6px 12px; margin-left: 12px; }
.run-button { padding: 9px 16px; background: #2463ab; color: white; border: 0; border-radius: 6px; cursor: pointer; margin: 6px 12px 12px 0; }
.run-button.secondary { background: #e4edf8; color: #245080; }
.result-scroll { overflow: auto; } table { border-collapse: collapse; min-width: 100%; font-size: 12px; }
th, td { text-align: left; padding: 10px; border-bottom: 1px solid #dfe6ef; white-space: nowrap; }
.failure { color: #b42318 !important; }
.skill-detail { max-width: 900px; margin: 0 auto; padding: 32px 24px; }
.skill-detail__header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 24px; }
.skill-detail__title { font-size: 22px; font-weight: 600; color: #1a1a2e; }
.skill-detail__desc { font-size: 13px; color: #666; margin-top: 4px; }
.skill-detail__actions { display: flex; align-items: center; gap: 12px; }
.skill-detail__badge { font-size: 12px; padding: 3px 10px; border-radius: 12px; }
.skill-detail__badge--active { background: #e6f7e9; color: #1a8a3a; }
.skill-detail__badge--draft { background: #fff3e0; color: #e65100; }
.skill-detail__badge--deprecated { background: #f0f0f0; color: #999; }
.skill-detail__version { font-size: 13px; color: #4a6fa5; font-weight: 600; }
.skill-detail__btn { padding: 6px 14px; border: 1px solid #d32f2f; color: #d32f2f; background: #fff; border-radius: 4px; font-size: 12px; cursor: pointer; }
.skill-detail__section { margin-bottom: 24px; }
.skill-detail__section h3 { font-size: 15px; font-weight: 600; margin-bottom: 10px; color: #333; }
.skill-detail__section pre { background: #f8f9fa; padding: 14px; border-radius: 8px; font-size: 12px; overflow-x: auto; white-space: pre-wrap; }
.skill-detail__prompt { white-space: pre-wrap; }
.skill-detail__tool { margin-bottom: 16px; }
.skill-detail__tool strong { font-size: 13px; }
.skill-detail__code { background: #1e1e1e; color: #d4d4d4; padding: 12px; border-radius: 6px; margin-top: 6px; }
.skill-detail__versions { border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden; }
.skill-detail__ver-item { display: flex; align-items: center; gap: 12px; padding: 10px 14px; border-bottom: 1px solid #f0f0f0; font-size: 13px; }
.skill-detail__ver-item:last-child { border-bottom: none; }
.skill-detail__ver-item--current { background: #f0f6ff; }
.skill-detail__ver-num { font-weight: 600; color: #4a6fa5; min-width: 40px; }
.skill-detail__ver-log { flex: 1; color: #555; }
.skill-detail__ver-time { font-size: 11px; color: #999; }
.skill-detail__ver-rollback { font-size: 11px; padding: 3px 8px; border: 1px solid #4a6fa5; color: #4a6fa5; background: #fff; border-radius: 4px; cursor: pointer; }
.skill-detail__empty { color: #999; font-size: 13px; }

/* ── 深色态覆盖：详情页/运行卡/版本列表/代码块随主题翻转 ── */
html[data-theme="dark"] .skill-run { border-color: var(--neutral-200); background: var(--surface-secondary); }
html[data-theme="dark"] .skill-run p { color: var(--neutral-600); }
html[data-theme="dark"] .run-button { background: var(--semantic-600); color: #fff; }
html[data-theme="dark"] .run-button.secondary { background: rgba(76, 110, 245, 0.16); color: var(--semantic-300); }
html[data-theme="dark"] .skill-run th, html[data-theme="dark"] .skill-run td { border-bottom-color: var(--neutral-200); }
html[data-theme="dark"] .skill-detail__title { color: var(--neutral-900); }
html[data-theme="dark"] .skill-detail__desc, html[data-theme="dark"] .skill-detail__ver-log, html[data-theme="dark"] .skill-detail__section h3 { color: var(--neutral-600); }
html[data-theme="dark"] .skill-detail__badge--active { background: rgba(26, 138, 58, 0.16); color: var(--dynamic-500); }
html[data-theme="dark"] .skill-detail__badge--draft { background: rgba(245, 159, 0, 0.14); color: var(--kinetic-500); }
html[data-theme="dark"] .skill-detail__badge--deprecated { background: var(--neutral-100); color: var(--neutral-500); }
html[data-theme="dark"] .skill-detail__version, html[data-theme="dark"] .skill-detail__ver-num { color: var(--semantic-300); }
html[data-theme="dark"] .skill-detail__btn { background: var(--surface-card); color: #ff8787; border-color: rgba(250, 82, 82, 0.4); }
html[data-theme="dark"] .skill-detail__section pre { background: var(--neutral-100); color: var(--neutral-800); }
html[data-theme="dark"] .skill-detail__versions { border-color: var(--neutral-200); }
html[data-theme="dark"] .skill-detail__ver-item { border-bottom-color: var(--neutral-200); }
html[data-theme="dark"] .skill-detail__ver-item--current { background: rgba(76, 110, 245, 0.12); }
html[data-theme="dark"] .skill-detail__ver-time { color: var(--neutral-500); }
html[data-theme="dark"] .skill-detail__ver-rollback { background: var(--surface-card); color: var(--semantic-300); border-color: rgba(92, 124, 250, 0.4); }
</style>
