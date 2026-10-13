<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { get, post } from '../../api/client'
type Action = { id: string; name: string; parameters: { name: string; type: string; required?: boolean; description?: string; default_value?: string }[] }
type Runtime = { name: string; goal: string; release_number: number; published_at: string;
  objects: { id: string; label: string; asset_name: string }[]; actions: Action[];
  relations: { name: string; from_id: string; to_id: string; cardinality: string }[] }
type Result = { columns: string[]; rows: unknown[][]; asset_name: string; queried_at: string }
const route = useRoute(), app = ref<Runtime | null>(null), selected = ref(''), result = ref<Result | null>(null)
const actionId = ref(''), params = ref<Record<string, any>>({}), actionResult = ref<any>(null), busy = ref(false), error = ref('')
const action = computed(() => app.value?.actions.find(a => a.id === actionId.value))
watch(actionId, () => { params.value = Object.fromEntries((action.value?.parameters || []).map(p => [p.name, p.default_value ?? ''])); actionResult.value = null })
const root = `/delivery-projects/${encodeURIComponent(String(route.params.id))}`
async function run(fn: () => Promise<void>) {
  busy.value = true; error.value = ''
  try { await fn() } catch (e: any) { error.value = e?.response?.data?.detail || e.message || '操作失败' } finally { busy.value = false }
}
async function query() {
  result.value = null
  await run(async () => { result.value = await get(`${root}/runtime/${encodeURIComponent(selected.value)}`) })
}
async function execute(dryRun: boolean) {
  if (!dryRun && !window.confirm('即将执行真实业务操作，可能改变业务数据。确认执行？')) return
  actionResult.value = null
  await run(async () => {
    const body: Record<string, any> = {}
    for (const p of action.value?.parameters || []) {
      const value = params.value[p.name]
      if (value === '' || value == null) { if (p.required !== false) throw new Error(`请填写${p.description || p.name}`); continue }
      body[p.name] = ['number', 'integer'].includes(p.type) ? Number(value) : p.type === 'boolean' ? value === 'true' : ['object', 'array'].includes(p.type) ? JSON.parse(value) : value
    }
    actionResult.value = await post(`${root}/runtime/actions/${actionId.value}`, { params: body, dry_run: dryRun })
  })
}
onMounted(async () => {
  await run(async () => { app.value = await get<Runtime>(`${root}/runtime`); selected.value = app.value.objects[0]?.id || '' })
  if (selected.value) await query()
})
</script>

<template>
  <div class="runtime">
    <RouterLink :to="{ path: '/workspace/projects', query: { project: String(route.params.id) } }">← 返回业务项目</RouterLink>
    <header v-if="app"><div><span>本体应用 · v{{ app.release_number }}</span><h1>{{ app.name }}</h1><p>{{ app.goal }}</p></div><small>发布于 {{ new Date(app.published_at).toLocaleString() }}</small></header>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="!app && busy">正在加载应用…</p>
    <template v-if="app">
      <section><div class="bar"><h2>业务对象</h2><select v-model="selected" aria-label="查询对象" :disabled="busy" @change="query"><option v-for="o in app.objects" :key="o.id" :value="o.id">{{ o.label }}</option></select><button :disabled="busy || !selected" @click="query">{{ busy ? '处理中…' : '刷新数据' }}</button></div>
        <template v-if="result"><p class="meta">来源：{{ result.asset_name }} · 查询时间：{{ new Date(result.queried_at).toLocaleString() }} · 展示最多 20 行样本</p><div class="scroll"><table><thead><tr><th v-for="c in result.columns" :key="c">{{ c }}</th></tr></thead><tbody><tr v-for="(row, i) in result.rows" :key="i"><td v-for="(value, j) in row" :key="j">{{ value ?? '—' }}</td></tr></tbody></table></div><p v-if="!result.rows.length">当前没有数据。可检查数据源与处理任务。</p></template>
      </section>
      <section v-if="app.relations?.length"><h2>对象关系定义</h2><p class="meta">来自已发布本体的有向关系。这里展示模型定义，实例关联需按数据关联键验证。</p><div class="scroll"><table><thead><tr><th>起点对象</th><th>关系谓词</th><th>终点对象</th><th>关系数量</th></tr></thead><tbody><tr v-for="(r, i) in app.relations" :key="i"><td>{{ app.objects.find(o => o.id === r.from_id)?.label }}</td><td>{{ r.name }} →</td><td>{{ app.objects.find(o => o.id === r.to_id)?.label }}</td><td>{{ r.cardinality }}</td></tr></tbody></table></div></section>
      <section v-if="app.actions.length"><h2>业务行动</h2><p class="meta">先检查参数，再执行操作。执行结果会记录在项目运行记录中。</p><select v-model="actionId" aria-label="选择行动" :disabled="busy"><option value="">请选择行动</option><option v-for="a in app.actions" :key="a.id" :value="a.id">{{ a.name }}</option></select>
        <template v-if="actionId"><label v-for="p in action?.parameters" :key="p.name" class="parameter">{{ p.description || p.name }}{{ p.required !== false ? ' *' : '' }}<select v-if="p.type === 'boolean'" v-model="params[p.name]" :disabled="busy"><option value="">请选择</option><option value="true">是</option><option value="false">否</option></select><input v-else v-model="params[p.name]" :type="['number','integer'].includes(p.type) ? 'number' : 'text'" :disabled="busy" :placeholder="p.name" /></label><div class="bar"><button :disabled="busy" @click="execute(true)">验证参数与配置</button><button class="primary" :disabled="busy" @click="execute(false)">执行行动</button></div></template>
        <div v-if="actionResult" :class="actionResult.success ? 'success' : 'error'" role="status"><strong>{{ actionResult.message }}</strong><pre>{{ JSON.stringify(actionResult.output, null, 2) }}</pre></div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.parameter{display:flex;flex-direction:column;gap:6px;margin:16px 0}.parameter input{border:1px solid #dce1eb;border-radius:7px;padding:10px;background:var(--surface-card,#fff);color:inherit;font:inherit}
.runtime{max-width:1200px;margin:auto;padding:32px;color:var(--neutral-900,#17233d)}a,header span{color:#4f46e5;font-size:13px}header{display:flex;justify-content:space-between;gap:20px;margin:28px 0}h1{font-size:28px;margin:10px 0}header p{color:#64748b;white-space:pre-wrap}small,.meta{color:#7c879a;font-size:12px;line-height:1.8}section{padding:24px;border:1px solid #e1e6ef;border-radius:12px;margin-bottom:24px;background:var(--surface-card,#fff)}h2{font-size:18px;margin:0 auto 0 0}.bar{display:flex;align-items:center;gap:12px;flex-wrap:wrap}select,button,textarea{border:1px solid #dce1eb;border-radius:7px;padding:10px;background:var(--surface-card,#fff);color:inherit;font:inherit;font-size:13px}button{cursor:pointer}button:disabled{opacity:.5;cursor:wait}.primary{background:#4f46e5;color:white}textarea{display:block;box-sizing:border-box;min-height:100px;width:100%;margin:10px 0;font-family:monospace}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px;white-space:nowrap}th,td{text-align:left;padding:12px;border-bottom:1px solid #e5e7eb}th{background:#f8fafc}.error,.success{padding:15px;border-radius:8px;margin-top:16px;white-space:pre-wrap}.error{color:#b91c1c;background:#fff1f2}.success{color:#047857;background:#ecfdf5}pre{overflow:auto;font-size:12px}li,label{font-size:13px;line-height:1.9}
</style>
