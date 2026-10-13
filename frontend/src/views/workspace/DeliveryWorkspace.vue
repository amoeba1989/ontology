<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import { Select as ASelect } from 'ant-design-vue'
import { get, post, put } from '../../api/client'

type Option = { id: string; name: string; status?: string; engine?: string; entity_id?: string }
type Config = { goal: string; audience: string; questions: string; expected_actions: string; acceptance: string;
  asset_ids: string[]; processing_mode: 'pipeline' | 'direct'; processing_note: string; pipeline_ids: string[];
  output_asset_ids: string[]; entity_ids: string[]; action_ids: string[]; version_id: string | null; acceptance_evidence: string }
type Project = { id: string; name: string; config: Config; revision: number; release_number: number;
  published_revision: number | null; updated_at: string; steps: { name: string; ready: boolean; issues: string[] }[] }
type Sample = { entity?: string; columns: string[]; rows: unknown[][]; asset_name: string; queried_at: string }
type Event = { id: string; kind: string; status: string; message: string; created_at: string; revision: number }
const names = ['需求分析', '数据源表', '数据处理', '子图建模', '本体库', '本体应用']
const descriptions = ['先明确业务目标和交付标准', '选择已接入的数据资产', '形成可以用于建模的数据结果', '将数据映射为业务对象与关系', '关联经过校验的本体发布版本', '试运行、验收并交付业务应用']
const defaults = (): Config => ({ goal: '', audience: '', questions: '', expected_actions: '', acceptance: '',
  asset_ids: [], processing_mode: 'pipeline', processing_note: '', pipeline_ids: [], output_asset_ids: [],
  entity_ids: [], action_ids: [], version_id: null, acceptance_evidence: '' })
const route = useRoute(), router = useRouter()
const projects = ref<Project[]>([]), current = ref<Project | null>(null)
const form = ref({ name: '', config: defaults() })
const resources = ref<Record<string, Option[]>>({ assets: [], pipelines: [], entities: [], versions: [], actions: [] })
const step = ref(0), busy = ref(false), loading = ref(true), error = ref(''), notice = ref('')
const events = ref<Event[]>([]), samples = ref<Sample[]>([]), baseline = ref('')
const examples = ref<{ key: string; name: string; goal: string; boundary: string }[]>([])
const showExamples = ref(false)
const dirty = computed(() => JSON.stringify(form.value) !== baseline.value)
const progress = computed(() => current.value?.steps.filter(s => s.ready).length || 0)
const missing = computed(() => current.value?.steps[step.value]?.issues || [])
const actions = computed(() => resources.value.actions?.filter(a => form.value.config.entity_ids.includes(a.entity_id || '')) || [])
const options = (items: Option[] = []) => items.map(x => ({ value: x.id,
  label: `${x.name}${x.engine === 'mock' ? '（模拟）' : ''}${x.status ? ` · ${x.status}` : ''}` }))
const fmt = (date: string) => new Date(date).toLocaleString()
function message(e: any) { return typeof e?.response?.data?.detail === 'string' ? e.response.data.detail : e?.message || '操作失败，请重试' }
async function perform(fn: () => Promise<void>) {
  busy.value = true; error.value = ''; notice.value = ''
  try { await fn() } catch (e) { error.value = message(e) } finally { busy.value = false }
}
function useProject(p: Project) {
  current.value = p
  form.value = { name: p.name, config: { ...defaults(), ...JSON.parse(JSON.stringify(p.config)) } }
  baseline.value = JSON.stringify(form.value)
}
async function reloadList() { projects.value = await get<Project[]>('/delivery-projects') }
async function load(id?: string) {
  if (!id) { current.value = null; form.value = { name: '', config: defaults() }; baseline.value = JSON.stringify(form.value); events.value = []; samples.value = []; return }
  useProject(await get<Project>(`/delivery-projects/${id}`))
  events.value = await get<Event[]>(`/delivery-projects/${id}/events`)
  samples.value = []
}
async function selectProject(id?: string) {
  if (dirty.value && !window.confirm('当前有未保存的修改，是否放弃修改并切换项目？')) return
  if (!id && !route.query.project) { await load(); return }
  await router.push({ path: '/workspace/projects', query: id ? { project: id } : {} })
}
async function save() {
  if (!form.value.name.trim()) throw new Error('请填写项目名称')
  const body = { ...form.value, revision: current.value?.revision || 1 }
  const p = current.value ? await put<Project>(`/delivery-projects/${current.value.id}`, body) : await post<Project>('/delivery-projects', body)
  useProject(p)
  await reloadList()
  if (route.query.project !== p.id) await router.replace({ query: { project: p.id } })
  notice.value = '已保存，完成情况根据实际资源重新校验。'
  return p
}
async function refresh() {
  if (dirty.value) { error.value = '请先保存当前修改，再刷新资源。'; return }
  await perform(async () => {
    resources.value = await get('/delivery-projects/resources')
    await reloadList(); await load(current.value?.id)
  })
}
async function test() {
  await perform(async () => {
    const p = await save()
    const result = await post<{ samples: Sample[]; project: Project }>(`/delivery-projects/${p.id}/test`)
    useProject(result.project); samples.value = result.samples
    events.value = await get(`/delivery-projects/${p.id}/events`)
    notice.value = '真实数据试运行成功。请核对样本与业务验收条件；样本检查不代表全量数据质量检查。'
  })
}
async function publish() {
  await perform(async () => {
    if (dirty.value) throw new Error('请先保存并试运行最新配置，再发布。')
    if (!current.value) return
    useProject(await post<Project>(`/delivery-projects/${current.value.id}/publish`))
    await reloadList(); events.value = await get(`/delivery-projects/${current.value.id}/events`)
    notice.value = '应用已发布，可以打开运行页面。'
  })
}
async function createExample(key: string) {
  if (dirty.value && !window.confirm('当前草稿未保存，是否放弃修改并创建独立验收样例？')) return
  await perform(async () => {
    const p = await post<Project>(`/delivery-projects/examples/${key}`)
    useProject(p); await reloadList(); resources.value = await get('/delivery-projects/resources')
    await router.replace({ query: { project: p.id } }); showExamples.value = false; step.value = 0
    notice.value = '已创建独立合成数据。请确认需求，然后在数据处理步骤运行管道。'
  })
}
async function projectOperation(operation: string) {
  if (operation === 'run-pipelines' && !window.confirm('将执行所选真实管道并写入其目标表。确认运行？')) return
  await perform(async () => {
    const p = await save()
    useProject(await post<Project>(`/delivery-projects/${p.id}/${operation}`))
    resources.value = await get('/delivery-projects/resources'); await reloadList()
    events.value = await get(`/delivery-projects/${p.id}/events`)
    notice.value = operation === 'run-pipelines' ? '数据处理完成，可以继续检查对象映射。' : '项目本体已发布，可以继续试运行应用。'
  })
}
watch(() => route.query.project, id => {
  // Saving or creating a project already loaded its response; don't race it
  // with a second request when only its URL changes.
  if (id === current.value?.id) return
  perform(() => load(typeof id === 'string' ? id : undefined))
})
onBeforeRouteLeave(() => !dirty.value || window.confirm('当前有未保存的修改，是否离开？'))
onMounted(async () => {
  await perform(async () => {
    resources.value = await get('/delivery-projects/resources')
    examples.value = await get('/delivery-projects/examples/catalog')
    await reloadList(); await load(typeof route.query.project === 'string' ? route.query.project : undefined)
  }); loading.value = false
})
</script>

<template>
  <div class="delivery">
    <header class="heading"><div><span class="eyebrow">业务交付工作区 · V1</span><h1>从业务需求，到可运行的本体应用</h1><p>连接已有能力，让每一步都有输入、结果和依据。</p></div>
      <div class="links"><button :disabled="busy" @click="showExamples = !showExamples">非军事验收样例</button><button :disabled="busy" @click="selectProject()">＋ 新建项目</button></div></header>
    <section v-if="showExamples" class="panel"><h3>用完整场景验证六步数据链路</h3><p class="muted">管理员可创建独立合成数据。每次创建得到新的样例项目，业务约束以可执行 SQL 规则实现。</p><div class="example-grid"><article v-for="example in examples" :key="example.key"><strong>{{ example.name }}</strong><p>{{ example.goal }}</p><small>{{ example.boundary }}</small><button :disabled="busy" @click="createExample(example.key)">创建验收项目</button></article></div></section>
    <div v-if="error" class="message error" role="alert">{{ error }}</div>
    <div v-if="notice" class="message success" role="status">{{ notice }}</div>
    <p v-if="loading">正在加载项目与数据资产…</p>
    <div v-else class="layout">
      <aside class="projects"><h3>业务项目 <span>{{ projects.length }}</span></h3>
        <p v-if="!projects.length" class="muted">从填写业务目标开始创建第一个项目。</p>
        <button v-for="p in projects" :key="p.id" class="project" :class="{ selected: p.id === current?.id }" :disabled="busy" @click="selectProject(p.id)">
          <strong>{{ p.name }}</strong><small>{{ p.steps.filter(s => s.ready).length }}/6 步就绪 · {{ p.release_number ? `已发布 v${p.release_number}` : '草稿' }}</small>
        </button>
      </aside>
      <section class="workspace">
        <div class="project-title"><input v-model="form.name" aria-label="项目名称" placeholder="为项目起一个名字，例如：设备故障处置" maxlength="200" :disabled="busy" />
          <span class="badge">{{ dirty ? '未保存' : current ? `草稿 r${current.revision}` : '新项目' }}</span></div>
        <nav class="steps" aria-label="业务交付步骤"><button v-for="(name, i) in names" :key="name" :disabled="busy" :class="{ active: step === i, ready: current?.steps[i]?.ready }" @click="step = i">
          <span>{{ current?.steps[i]?.ready ? '✓' : i + 1 }}</span>{{ name }}</button></nav>
        <div class="progress"><div :style="{ width: `${progress / 6 * 100}%` }" /></div>
        <div class="toolbar"><span class="muted">已保存配置：{{ progress }}/6 步就绪</span><button :disabled="busy" @click="refresh">刷新资源与校验</button><button class="primary" :disabled="busy" @click="perform(async () => { await save() })">{{ busy ? '处理中…' : '保存草稿' }}</button></div>
        <section class="editor"><h2>{{ names[step] }}</h2><p class="muted">{{ descriptions[step] }}</p>
          <fieldset :disabled="busy">
          <template v-if="step === 0">
            <label>业务目标 <textarea v-model="form.config.goal" placeholder="希望解决什么问题，改善什么结果？" maxlength="4000" /></label>
            <label>使用者 <input v-model="form.config.audience" placeholder="例如：设备运维人员、值班负责人" maxlength="1000" /></label>
            <label>核心问题 <textarea v-model="form.config.questions" placeholder="例如：哪些设备异常？关联哪些工单？" maxlength="4000" /></label>
            <label>预期业务操作（仅查询时可留空）<textarea v-model="form.config.expected_actions" placeholder="例如：创建维修工单、分派人员" maxlength="4000" /></label>
            <label>验收条件 <textarea v-model="form.config.acceptance" placeholder="描述可以实际核对的结果，例如：修改源数据后查询能看到最新状态" maxlength="4000" /></label>
          </template>
          <template v-if="step === 1">
            <label>项目使用的数据资产<ASelect v-model:value="form.config.asset_ids" mode="multiple" :options="options(resources.assets)" :disabled="busy" option-filter-prop="label" placeholder="选择已采集的表或视图" /></label>
            <div class="links"><RouterLink to="/data/connections" target="_blank">配置数据连接 ↗</RouterLink><RouterLink to="/data/assets" target="_blank">采集结构与预览数据 ↗</RouterLink></div>
            <p class="tip">在资产目录完成结构采集，返回后点击“刷新资源与校验”。选择资产并不代表已经验证实际数据，最终需进行真实试运行。</p>
          </template>
          <template v-if="step === 2">
            <label>数据处理方式<select v-model="form.config.processing_mode"><option value="pipeline">使用真实数据管道</option><option value="direct">数据已就绪，直接映射</option></select></label>
            <template v-if="form.config.processing_mode === 'pipeline'">
              <label>处理管道<ASelect v-model:value="form.config.pipeline_ids" mode="multiple" :options="options(resources.pipelines.filter(p => p.engine === 'real'))" :disabled="busy" option-filter-prop="label" /></label>
              <label>处理后的输出资产<ASelect v-model:value="form.config.output_asset_ids" mode="multiple" :options="options(resources.assets)" :disabled="busy" option-filter-prop="label" /></label>
              <p class="tip">输出资产必须对应管道目标表。模拟管道不计入交付，最近一次真实运行需成功。</p>
              <button class="primary" :disabled="busy || !form.config.pipeline_ids.length" @click="projectOperation('run-pipelines')">保存并运行项目管道</button>
            </template>
            <label>{{ form.config.processing_mode === 'direct' ? '无需加工的原因（必填，切换后请清空原有管道和输出资产）' : '处理说明' }}<textarea v-model="form.config.processing_note" maxlength="2000" /></label>
            <button v-if="form.config.processing_mode === 'direct'" @click="form.config.pipeline_ids = []; form.config.output_asset_ids = []">清空管道和输出资产</button>
            <div class="links"><RouterLink to="/data/pipeline" target="_blank">配置、预览与运行数据管道 ↗</RouterLink><RouterLink to="/data/assets" target="_blank">登记输出资产 ↗</RouterLink></div>
          </template>
          <template v-if="step === 3">
            <label>业务对象<ASelect v-model:value="form.config.entity_ids" mode="multiple" :options="options(resources.entities)" :disabled="busy" option-filter-prop="label" /></label>
            <label>可执行行动（可选）<ASelect v-model:value="form.config.action_ids" mode="multiple" :options="options(actions)" :disabled="busy" option-filter-prop="label" /></label>
            <p class="tip">每个对象需要主键和唯一主数据绑定，绑定到本项目输出资产。直连模式绑定到源资产。V1 的过滤和字段转换在数据处理步骤完成。</p>
            <div class="links"><RouterLink to="/builder" target="_blank">构建对象与关系 ↗</RouterLink><RouterLink to="/data/mapping" target="_blank">配置数据映射 ↗</RouterLink><RouterLink to="/logic/actions" target="_blank">配置业务行动 ↗</RouterLink></div>
          </template>
          <template v-if="step === 4">
            <label>已发布本体版本<ASelect :value="form.config.version_id || undefined" @change="value => form.config.version_id = value ? String(value) : null" allow-clear :options="options(resources.versions.filter(v => v.status === 'published'))" :disabled="busy" placeholder="选择包含全部项目对象的已发布版本" /></label>
            <p class="tip">当前对象结构需与发布版本一致。应用发布时固定字段映射和行动定义；数据查询每次读取当前数据。</p>
            <button class="primary" :disabled="busy" @click="projectOperation('publish-ontology')">校验并发布项目本体（管理员）</button>
            <p class="tip">项目本体单独发布，不切换平台全局活动版本。</p>
            <div class="links"><RouterLink to="/ontology/publish" target="_blank">本体校验与版本发布 ↗</RouterLink></div>
          </template>
          <template v-if="step === 5">
            <div class="application"><strong>对象查询与行动应用</strong><p>交付一个可独立打开的页面：读取对象实例、查看来源、执行所选业务行动。</p></div>
            <label>业务验收结果<textarea v-model="form.config.acceptance_evidence" placeholder="核对需求后，记录已验证内容及未覆盖范围。保存后再试运行，成功后即可发布。" maxlength="4000" /></label>
            <div class="links"><button :disabled="busy" @click="test">保存并真实试运行</button><button class="primary" :disabled="busy || dirty || progress !== 6" @click="publish">发布应用</button>
              <RouterLink v-if="current?.release_number" :to="`/apps/projects/${current.id}`" target="_blank">打开应用 v{{ current.release_number }} ↗</RouterLink></div>
            <p v-if="current?.release_number" class="tip">已发布草稿版本 r{{ current.published_revision }}。草稿修改不会直接改变运行应用。当前访问范围为项目创建者及管理员。</p>
          </template>
          </fieldset>
          <div v-if="current" class="validation"><strong>{{ dirty ? '以下为上次保存后的校验结果' : '当前步骤校验' }}</strong><ul v-if="missing.length"><li v-for="item in missing" :key="item">{{ item }}</li></ul><p v-else class="ok">✓ 当前步骤已就绪</p></div>
          <div class="step-nav"><button :disabled="busy || step === 0" @click="step--">上一步</button><button :disabled="busy || step === 5" @click="step++">下一步</button></div>
        </section>
        <section v-for="(sample, i) in samples" :key="i" class="panel"><h3>{{ sample.entity }} · 实际数据样本</h3><p class="muted">来源：{{ sample.asset_name }} · {{ fmt(sample.queried_at) }} · 最多 20 行</p><div class="table-scroll"><table><thead><tr><th v-for="col in sample.columns" :key="col">{{ col }}</th></tr></thead><tbody><tr v-for="(row, j) in sample.rows" :key="j"><td v-for="(value, k) in row" :key="k">{{ value ?? '—' }}</td></tr></tbody></table></div><p v-if="!sample.rows.length">查询成功，当前没有数据。</p></section>
        <section v-if="events.length" class="panel"><h3>运行与交付记录</h3><div v-for="event in events" :key="event.id" class="event"><span :class="event.status === 'error' ? 'fail' : 'ok'">{{ event.status === 'error' ? '失败' : '成功' }}</span><span>{{ event.message }}</span><small>{{ fmt(event.created_at) }} · r{{ event.revision }}</small></div></section>
      </section>
    </div>
  </div>
</template>

<style scoped>
.example-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}.example-grid article{display:flex;flex-direction:column;gap:10px;padding:16px;border:1px solid #e2e8f0;border-radius:9px}.example-grid p{font-size:13px;line-height:1.6;margin:0}.example-grid small{font-size:11px;color:#64748b;line-height:1.6;flex:1}
.delivery{padding:28px;max-width:1600px;margin:auto;color:var(--neutral-900,#17233d)}.heading,.toolbar,.project-title,.step-nav{display:flex;align-items:center;justify-content:space-between;gap:12px}.heading{margin-bottom:24px}.eyebrow{color:#6366f1;font-size:12px;font-weight:700}h1{font-size:24px;margin:8px 0}h2{font-size:20px;margin:0}h3{font-size:15px;margin:0 0 12px}.heading p,.muted{color:var(--neutral-500,#768197);font-size:13px}.layout{display:grid;grid-template-columns:230px minmax(0,1fr);gap:22px}.projects,.workspace{min-width:0}.projects h3 span{color:#8b91a0}.project{display:flex;flex-direction:column;width:100%;align-items:flex-start;text-align:left;margin-bottom:8px;padding:14px;gap:8px}.project strong{overflow-wrap:anywhere}.project small{font-size:11px;color:#737e91}.project.selected{border-color:#6366f1;background:#eef2ff}button{border:1px solid #dce1eb;background:var(--surface-card,#fff);border-radius:8px;padding:9px 14px;cursor:pointer;color:inherit;font-size:13px}button:hover:not(:disabled){border-color:#6366f1}button:disabled{opacity:.5;cursor:not-allowed}button.primary{background:#4f46e5;color:#fff;border-color:#4f46e5}.project-title input{font-size:18px;font-weight:600;flex:1}.badge{font-size:12px;color:#6366f1;white-space:nowrap}.steps{display:grid;grid-template-columns:repeat(6,1fr);gap:6px;margin:22px 0 12px}.steps button{padding:12px 4px;display:flex;align-items:center;flex-direction:column;gap:8px}.steps span{display:grid;place-items:center;border-radius:50%;width:25px;height:25px;background:#f0f2f7}.steps .ready span{background:#dcfce7;color:#15803d}.steps .active{border-color:#6366f1;background:#eef2ff}.progress{height:4px;background:#eef0f4;border-radius:4px;overflow:hidden}.progress div{height:100%;background:#22c55e;transition:width .2s}.toolbar{margin:16px 0}.toolbar .muted{margin-right:auto}.editor,.panel{border:1px solid #e3e7ee;border-radius:12px;background:var(--surface-card,#fff);padding:22px;margin-bottom:18px}fieldset{border:0;padding:0;margin:20px 0;min-width:0}label{display:flex;flex-direction:column;gap:8px;font-size:13px;font-weight:600;margin:18px 0}input,textarea,select{width:100%;box-sizing:border-box;font:inherit;border:1px solid #dce1eb;background:var(--surface-card,#fff);color:inherit;border-radius:7px;padding:10px;font-weight:400}textarea{min-height:80px;resize:vertical}input:focus,textarea:focus{outline:2px solid #c7d2fe}.links{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-top:18px}a{color:#4f46e5;font-size:13px}.tip{font-size:12px;color:#737e91;line-height:1.8}.validation{padding:14px;background:#f8fafc;border-radius:8px;font-size:13px}.validation ul{padding-left:20px;color:#a16207;line-height:1.8}.ok{color:#15803d}.fail{color:#b91c1c}.step-nav{margin-top:18px}.application{padding:18px;background:#eef2ff;border-radius:9px}.application p{font-size:13px;color:#64748b}.message{padding:14px;border-radius:8px;margin:12px 0;font-size:13px;white-space:pre-wrap}.error{background:#fff1f2;color:#be123c}.success{background:#ecfdf5;color:#047857}.table-scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:12px;white-space:nowrap}td,th{padding:9px 12px;text-align:left;border-bottom:1px solid #e5e7eb}th{background:#f8fafc}.event{display:flex;gap:12px;font-size:12px;padding:10px 0;border-bottom:1px solid #eee}.event small{margin-left:auto;color:#8892a3}.event span:nth-child(2){flex:1;overflow-wrap:anywhere}@media(max-width:1000px){.layout{grid-template-columns:1fr}.projects{display:flex;gap:8px;overflow:auto}.projects h3{display:none}.project{min-width:180px}.steps{grid-template-columns:repeat(3,1fr)}.heading{align-items:flex-start}.delivery{padding:16px}}
</style>
