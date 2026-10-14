<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import client from '../../api/client'

type Attribute = { name: string; label: string; type: string; required: boolean; unit: string; description: string }
type Entity = { name: string; label: string; description: string; reuse_id?: string | null; attributes: Attribute[] }
type Rule = { id: string; name: string; entity: string; kind: string; origin: string; basis: string; assumptions: string; exceptions: string; confirmed: boolean; status: string; clauses: { field: string; operator: string; value: unknown }[]; examples: { label: string; values: Record<string, unknown>; expected: boolean }[] }
type Content = { entities: Entity[]; relations: { name: string; label: string; source: string; target: string; cardinality: string }[]; rules: Rule[]; questions: string[] }
type Draft = { id: string; name: string; scenario: string; revision: number; content: Content; proposal?: { model: string; content: Content }; materialized?: { entity_ids: string[]; rule_ids: string[] } }
const route = useRoute(), router = useRouter()
const blank = (): Content => ({ entities: [], relations: [], rules: [], questions: [] })
const draft = ref<Draft>({ id: '', name: '新的业务模型', scenario: '', revision: 1, content: blank() })
const saved = ref(JSON.stringify(draft.value)), busy = ref(false), error = ref(''), notice = ref('')
const drafts = ref<{ id: string; name: string; imported: boolean }[]>([])
const catalog = ref<(Entity & { id: string })[]>([]), reuseId = ref(''), tab = ref('entities')
const results = ref<{ rule_id: string; passed: boolean; cases: { label: string; passed: boolean; valid: boolean; expected: boolean }[] }[]>([])
const dirty = computed(() => JSON.stringify(draft.value) !== saved.value)
const content = computed(() => draft.value.content)
const locked = computed(() => !!draft.value.materialized)
const root = () => `/modeling-drafts/${draft.value.id}`
const confirmReplace = () => window.confirm('用演示模板替换当前内容？')
function assign(value: Draft) { draft.value = value; saved.value = JSON.stringify(value); results.value = [] }
async function run(task: () => Promise<void>) {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try { await task() } catch (e: any) {
    const detail = e.response?.data?.detail
    error.value = Array.isArray(detail) ? detail.map((v: any) => `${v.loc.join('.')}: ${v.msg}`).join('；') : (detail || e.message || '操作失败')
  } finally { busy.value = false }
}
async function list() { drafts.value = (await client.get('/modeling-drafts')).data }
async function save() {
  if (locked.value) return
  const body = { name: draft.value.name, scenario: draft.value.scenario, content: content.value, revision: draft.value.revision }
  assign((await (draft.value.id ? client.put(root(), body) : client.post('/modeling-drafts', body))).data)
  await router.replace({ query: { id: draft.value.id } }); await list()
}
function discardOK() { return !dirty.value || window.confirm('当前有未保存的修改，确定放弃吗？') }
async function open(id: string) { if (discardOK()) await run(async () => { assign((await client.get(`/modeling-drafts/${id}`)).data); await router.replace({ query: { id } }) }) }
async function fresh() { if (discardOK()) { assign({ id: '', name: '新的业务模型', scenario: '', revision: 1, content: blank() }); tab.value = 'entities'; await router.replace({ query: {} }) } }
function addEntity() { content.value.entities.push({ name: `Object${content.value.entities.length + 1}`, label: '新对象', description: '', attributes: [] }) }
function addAttribute(e: Entity) { e.attributes.push({ name: `field_${e.attributes.length + 1}`, label: '新属性', type: 'string', required: false, unit: '', description: '' }) }
function renameEntity(e: Entity, name: string) {
  const old = e.name; e.name = name
  content.value.relations.forEach(r => { if (r.source === old) r.source = name; if (r.target === old) r.target = name })
  content.value.rules.forEach(r => { if (r.entity === old) r.entity = name })
}
function removeEntity(index: number) {
  const name = content.value.entities[index]!.name
  if (!window.confirm('删除该对象及其草稿中的关系和规则？')) return
  content.value.entities.splice(index, 1)
  content.value.relations = content.value.relations.filter(r => r.source !== name && r.target !== name)
  content.value.rules = content.value.rules.filter(r => r.entity !== name)
}
function reuse() {
  const entity = catalog.value.find(e => e.id === reuseId.value)
  if (!entity || content.value.entities.some(e => e.name === entity.name)) return
  content.value.entities.push({ name: entity.name, label: entity.label, description: entity.description,
    reuse_id: entity.id, attributes: structuredClone(entity.attributes.map(a => ({ ...a }))) })
}
function addRule() {
  const entity = content.value.entities[0]
  if (!entity) { error.value = '请先添加对象及属性'; return }
  content.value.rules.push({ id: `rule-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, name: '新业务规则', entity: entity.name,
    kind: 'business', origin: 'manual', basis: '', assumptions: '', exceptions: '', confirmed: false, status: 'pending',
    clauses: [{ field: entity.attributes[0]?.name || '', operator: 'required', value: null }],
    examples: [{ label: '符合约束', values: {}, expected: true }, { label: '违反约束', values: {}, expected: false }] })
}
function parseValue(text: string): unknown { try { return JSON.parse(text) } catch { return text } }
function exampleValues(rule: Rule, index: number, event: Event) {
  try {
    const data = JSON.parse((event.target as HTMLTextAreaElement).value)
    if (!data || Array.isArray(data) || typeof data !== 'object') throw new Error()
    rule.examples[index]!.values = data; error.value = ''
  } catch { error.value = '样例数据必须是 JSON 对象，例如 {"height_agl":30}'; (event.target as HTMLTextAreaElement).value = JSON.stringify(rule.examples[index]!.values) }
}
async function generate() { await run(async () => { await save(); assign((await client.post(root() + '/generate', { revision: draft.value.revision })).data); notice.value = 'AI 建议已保存，预览后可采纳；当前草稿尚未替换。' }) }
async function apply() { await run(async () => { assign((await client.post(root() + '/apply-proposal', { revision: draft.value.revision })).data); notice.value = '已采纳到草稿，请编辑并审核规则。' }) }
async function testRules() { await run(async () => { if (dirty.value || !draft.value.id) await save(); results.value = (await client.post(root() + '/test-rules', { revision: draft.value.revision })).data.results }) }
async function review(id: string, decision: string) {
  await run(async () => {
    if (dirty.value || !draft.value.id) await save()
    if (decision === 'accepted') {
      const rule = content.value.rules.find(r => r.id === id)!
      if (!window.confirm(`确认“${rule.name}”的依据、适用前提、单位与例外已经核对？接受只代表审核通过，尚未对业务数据启用。`)) return
      rule.confirmed = true; await save()
    }
    assign((await client.post(root() + '/review', { revision: draft.value.revision, rule_ids: [id], decision })).data)
    notice.value = '审核已保存。'
  })
}
async function materialize() {
  if (!window.confirm('将创建或复用对象与关系，并把已接受规则写入规则管理（草稿状态）。后续仍需绑定数据并发布，是否继续？')) return
  await run(async () => { if (dirty.value || !draft.value.id) await save(); assign((await client.post(root() + '/materialize', { revision: draft.value.revision })).data); await list(); notice.value = '已入库，可继续到映射管理绑定业务数据。' })
}
function leave(e: BeforeUnloadEvent) { if (dirty.value) { e.preventDefault(); e.returnValue = '' } }
onBeforeRouteLeave(() => discardOK())
onMounted(() => { window.addEventListener('beforeunload', leave); run(async () => { await list(); catalog.value = (await client.get('/modeling-drafts/catalog')).data; if (route.query.id) assign((await client.get(`/modeling-drafts/${route.query.id}`)).data) }) })
onBeforeUnmount(() => window.removeEventListener('beforeunload', leave))
</script>

<template>
  <main class="draft-workspace">
    <header><div><span class="eyebrow">本体中心 / 建模工作区 · 迭代 1</span><h1>从业务描述，到可审核的本体模型</h1><p>AI 辅助与表单手动共用一份数据库草稿。先核对业务含义，再接入真实数据。</p></div><button :disabled="busy" @click="fresh">＋ 新建草稿</button></header>
    <div class="journey"><b>需求分析</b><span>→ 数据源表 → 数据处理 →</span><b>子图建模</b><span>→ 本体库 → 本体应用</span></div>
    <p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="notice" class="notice" role="status">{{ notice }}</p>
    <div class="workspace-grid">
      <aside><h3>我的建模草稿</h3><p v-if="!drafts.length">创建后可随时回来继续编辑。</p><button v-for="d in drafts" :key="d.id" :class="{ chosen: d.id === draft.id }" :disabled="busy" @click="open(d.id)">{{ d.name }}<small>{{ d.imported ? '已入库' : '草稿' }}</small></button><RouterLink to="/browser">查看已有对象与关系 →</RouterLink></aside>
      <section>
        <div class="card">
          <div class="section-head"><h2>1. 明确业务目标</h2><span>修订 {{ draft.revision }} · {{ dirty ? '尚未保存' : (draft.id ? '已保存' : '新草稿') }}</span></div>
          <fieldset :disabled="busy || locked"><label>模型名称<input v-model="draft.name" aria-label="模型名称" /></label><label>业务场景与验收目标<textarea v-model="draft.scenario" rows="3" placeholder="描述管理哪些对象、需要回答什么问题、已有数据在哪里，以及哪些情况需要提示异常。" /></label>
          <div class="actions"><button class="primary" @click="generate">{{ busy ? '处理中…' : 'AI 生成建议' }}</button><button @click="run(async () => { await save(); notice = '草稿已保存。' })">保存草稿</button><button @click="run(async () => { if (content.entities.length && !confirmReplace()) return; draft.content = (await client.get('/modeling-drafts/templates/drone')).data; draft.scenario = '无人机观测数据管理：识别离地高度异常，业务人员核对适用前提。'; })">载入无人机演示模板</button></div>
          </fieldset><p class="hint">AI 使用系统已配置的建模模型；演示模板为固定示例。AI 推荐依据需人工核实，无法确定的条件会列为待澄清问题。</p>
          <div v-if="draft.proposal" class="proposal"><h3>AI 建议预览 · {{ draft.proposal.model }}</h3><p>{{ draft.proposal.content.entities.length }} 个对象 · {{ draft.proposal.content.relations.length }} 条关系 · {{ draft.proposal.content.rules.length }} 条待审核规则</p><details><summary>展开完整建议</summary><pre>{{ JSON.stringify(draft.proposal.content, null, 2) }}</pre></details><button class="primary" :disabled="busy || dirty" @click="apply">采纳建议，替换当前草稿</button><small>采纳前请核对；编辑并保存当前草稿会使建议失效。</small></div>
        </div>
        <div class="card">
          <div class="section-head"><h2>2. 编辑对象、关系与规则</h2><span>AI / 表单共用</span></div>
          <nav><button v-for="t in [{ key: 'entities', label: '对象与属性' }, { key: 'relations', label: '对象关系' }, { key: 'rules', label: '规则与样例' }, { key: 'questions', label: '待澄清问题' }]" :key="t.key" :class="{ chosen: tab === t.key }" @click="tab = t.key">{{ t.label }}</button></nav>
          <fieldset :disabled="busy || locked">
            <div v-if="tab === 'entities'">
              <div class="actions"><button @click="addEntity">＋ 手动添加对象</button><select v-model="reuseId" aria-label="选择已有对象"><option value="">选择已有对象复用</option><option v-for="e in catalog" :key="e.id" :value="e.id">{{ e.label }} ({{ e.name }})</option></select><button @click="reuse">加入草稿</button></div>
              <p v-if="!content.entities.length" class="empty">从空白表单开始，或先描述场景让 AI 提供建议。</p>
              <article v-for="(e, i) in content.entities" :key="i" class="object-card">
                <div class="section-head"><b>对象 {{ i + 1 }} {{ e.reuse_id ? '· 复用已有定义' : '' }}</b><button @click="removeEntity(i)">移除</button></div>
                <fieldset :disabled="!!e.reuse_id"><div class="fields"><label>英文标识<input :value="e.name" @change="renameEntity(e, ($event.target as HTMLInputElement).value)" /></label><label>显示名称<input v-model="e.label" /></label><label>业务说明<input v-model="e.description" /></label></div>
                <div class="table-scroll"><table><thead><tr><th>属性标识</th><th>显示名称</th><th>类型</th><th>单位</th><th>必填</th><th>说明</th><th></th></tr></thead><tbody><tr v-for="(a, j) in e.attributes" :key="j"><td><input v-model="a.name" /></td><td><input v-model="a.label" /></td><td><select v-model="a.type"><option v-for="v in ['string','number','boolean','date','json']" :key="v">{{ v }}</option></select></td><td><input v-model="a.unit" /></td><td><input v-model="a.required" type="checkbox" /></td><td><input v-model="a.description" /></td><td><button @click="e.attributes.splice(j, 1)">移除</button></td></tr></tbody></table></div><button @click="addAttribute(e)">＋ 属性</button></fieldset>
              </article>
            </div>
            <div v-if="tab === 'relations'">
              <button @click="content.relations.push({ name: 'relatedTo', label: '关联', source: content.entities[0]?.name || '', target: content.entities[1]?.name || content.entities[0]?.name || '', cardinality: 'N:N' })">＋ 手动添加关系</button>
              <article v-for="(r, i) in content.relations" :key="i" class="object-card"><div class="fields"><label>来源对象<select v-model="r.source"><option v-for="e in content.entities" :key="e.name" :value="e.name">{{ e.label }}</option></select></label><label>关系英文标识<input v-model="r.name" /></label><label>显示名称<input v-model="r.label" /></label><label>目标对象<select v-model="r.target"><option v-for="e in content.entities" :key="e.name" :value="e.name">{{ e.label }}</option></select></label><label>数量关系<select v-model="r.cardinality"><option v-for="v in ['1:1','1:N','N:1','N:N']" :key="v">{{ v }}</option></select></label><button @click="content.relations.splice(i, 1)">移除</button></div><p class="relation-preview">{{ r.source }} ── {{ r.label || r.name }} ({{ r.cardinality }}) → {{ r.target }}</p></article>
            </div>
            <div v-if="tab === 'rules'">
              <div class="actions"><button @click="addRule">＋ 业务规则</button><button @click="testRules">保存并测试全部样例</button></div><p class="hint">条件为“数据必须满足的约束”，多条件同时满足。样例预期“合格”表示满足约束。变更条件、对象属性或场景后须重新审核。</p>
              <article v-for="(r, i) in content.rules" :key="r.id" class="object-card">
                <div class="section-head"><b>{{ r.name }}</b><span class="badge">{{ { pending: '待审核', accepted: '已接受', rejected: '已拒绝' }[r.status] || r.status }} · {{ r.origin }}</span><button @click="content.rules.splice(i, 1)">移除</button></div>
                <div class="fields"><label>规则名称<input v-model="r.name" /></label><label>关联对象<select v-model="r.entity"><option v-for="e in content.entities" :key="e.name">{{ e.name }}</option></select></label><label>分类<select v-model="r.kind"><option value="structure">结构约束</option><option value="common">通用规则</option><option value="business">业务规则</option></select></label></div>
                <label>依据（AI 推荐不等于权威标准）<textarea v-model="r.basis" rows="2" /></label><div class="fields"><label>适用前提与单位<textarea v-model="r.assumptions" rows="2" /></label><label>例外与适用边界<textarea v-model="r.exceptions" rows="2" /></label></div>
                <div v-for="(c, j) in r.clauses" :key="j" class="fields"><label>属性<select v-model="c.field"><option v-for="a in content.entities.find(e => e.name === r.entity)?.attributes || []" :key="a.name">{{ a.name }}</option></select></label><label>约束<select v-model="c.operator"><option v-for="v in ['required','eq','ne','gt','gte','lt','lte','in']" :key="v">{{ v }}</option></select></label><label>阈值（数值、文本或 JSON 数组）<input :disabled="c.operator === 'required'" :value="typeof c.value === 'string' ? c.value : JSON.stringify(c.value)" @change="c.value = parseValue(($event.target as HTMLInputElement).value)" /></label><button @click="r.clauses.splice(j, 1)">移除条件</button></div><button @click="r.clauses.push({ field: '', operator: 'required', value: null })">＋ 条件</button>
                <div v-for="(e, j) in r.examples" :key="j" class="fields"><label>样例名称<input v-model="e.label" /></label><label>样例数据 JSON<textarea :value="JSON.stringify(e.values)" rows="2" @change="exampleValues(r, j, $event)" /></label><label>预期<select v-model="e.expected"><option :value="true">合格</option><option :value="false">违反约束</option></select></label><button @click="r.examples.splice(j, 1)">移除样例</button></div><button @click="r.examples.push({ label: '新样例', values: {}, expected: true })">＋ 样例</button>
                <div class="actions review"><button class="primary" @click="review(r.id, 'accepted')">核对并接受</button><button @click="review(r.id, 'rejected')">拒绝此规则</button><button @click="review(r.id, 'pending')">撤回审核</button></div>
                <div v-for="result in results.filter(v => v.rule_id === r.id)" :key="result.rule_id" :class="result.passed ? 'notice' : 'error'"><b>{{ dirty ? '修改前测试结果，请重新测试' : (result.passed ? '正反样例通过' : '样例未通过或缺少正反例') }}</b><p v-for="(c, n) in result.cases" :key="n">{{ c.label }}：实际{{ c.valid ? '合格' : '违反约束' }} / 预期{{ c.expected ? '合格' : '违反约束' }} · {{ c.passed ? '符合预期' : '不符合预期' }}</p></div>
              </article>
            </div>
            <div v-if="tab === 'questions'"><p class="hint">记录来源、单位、阈值等尚未确认的问题；回答后应落实到对象或规则中。</p><div v-for="(_, i) in content.questions" :key="i" class="actions"><input v-model="content.questions[i]" /><button @click="content.questions.splice(i, 1)">移除</button></div><button @click="content.questions.push('')">＋ 待澄清问题</button></div>
          </fieldset>
        </div>
        <div class="card"><h2>3. 入库并继续业务链路</h2><p>对象与关系进入现有管理模块；已接受规则以草稿状态保存，绑定数据后再验证启用。</p><div v-if="!locked" class="actions"><button :disabled="busy" @click="run(async () => { await save(); notice = '草稿已保存。' })">保存草稿</button><button class="primary" :disabled="busy || !content.entities.length" @click="materialize">审核完成，写入本体管理</button></div><div v-else class="notice">已入库：{{ draft.materialized?.entity_ids.length }} 个对象、{{ draft.materialized?.rule_ids.length }} 条规则。<RouterLink to="/browser">查看对象</RouterLink> · <RouterLink to="/data/mapping">绑定业务数据</RouterLink> · <RouterLink to="/logic/rules">查看规则草稿</RouterLink></div></div>
      </section>
    </div>
  </main>
</template>

<style scoped>
.draft-workspace{padding:28px;color:#203247;background:#f3f6fb;min-height:100%;overflow:auto;font-size:14px}.eyebrow{color:#5264bf;font-weight:600;font-size:12px}header,.section-head{display:flex;justify-content:space-between;align-items:center;gap:14px}h1{font-size:25px;margin:8px 0}h2{font-size:18px;margin:0 0 12px}h3{font-size:15px}p{line-height:1.7}header p,.hint,small{color:#62748b}.journey{display:flex;gap:16px;flex-wrap:wrap;padding:18px;background:#e7edff;border-radius:10px;margin:20px 0;color:#4756a1}.workspace-grid{display:grid;grid-template-columns:210px minmax(0,1fr);gap:20px}aside{background:white;padding:16px;border:1px solid #e0e6ef;border-radius:12px;align-self:start}aside button{display:block;width:100%;text-align:left;margin-bottom:8px;white-space:normal}aside small{display:block;margin-top:5px}aside a{display:block;margin-top:20px}.card{padding:22px;background:#fff;border:1px solid #e0e6ef;border-radius:12px;margin-bottom:18px}.section-head span{font-size:12px;color:#62748b}fieldset{border:0;padding:0;margin:0;min-width:0}label{display:flex;flex-direction:column;gap:6px;margin:10px 0;flex:1;min-width:120px}input,textarea,select{padding:9px;border:1px solid #cbd5e1;border-radius:6px;background:#fff;color:#203247;max-width:100%;font:inherit}textarea{resize:vertical}button{padding:8px 12px;border:1px solid #ccd6e4;background:white;border-radius:6px;color:#30435b;cursor:pointer;font:inherit}button:hover{border-color:#5563d8;background:#f5f6ff}button.primary{background:#4e5ed0;color:white;border-color:#4e5ed0}button:disabled,fieldset:disabled{opacity:.6}button:disabled{cursor:not-allowed}.actions,.fields,nav{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.actions{margin:12px 0}.actions input{flex:1}.fields label{min-width:150px}.object-card{border:1px solid #dce3ef;background:#fafcff;padding:16px;border-radius:9px;margin:14px 0}.chosen{background:#e9edff;border-color:#6675d7;color:#3343a5}nav{margin-bottom:16px;border-bottom:1px solid #e0e6ef;padding-bottom:12px}table{border-collapse:collapse;width:100%;font-size:12px}th{text-align:left;color:#62748b;padding:8px 4px}td{padding:4px}td input:not([type=checkbox]){width:100%;min-width:80px}td input[type=checkbox]{width:auto}.table-scroll{overflow:auto;margin-bottom:10px}.error,.notice{padding:12px;border-radius:8px;margin:12px 0}.error{background:#fff0ed;color:#a43d2b}.notice{background:#eaf6f0;color:#23614a}.proposal{background:#f1f0ff;padding:18px;border-radius:8px}.proposal small{display:block;margin-top:10px}pre{white-space:pre-wrap;max-height:350px;overflow:auto;font-size:12px}.hint{font-size:12px}.badge{background:#e8edf7;padding:5px 9px;border-radius:20px}.review{border-top:1px solid #e0e6ef;padding-top:12px}.relation-preview{color:#4e5ed0;font-family:monospace}.empty{padding:30px;color:#7a8899;text-align:center}a{color:#4e5ed0}@media(max-width:900px){.workspace-grid{grid-template-columns:1fr}.draft-workspace{padding:16px}header{align-items:flex-start}h1{font-size:21px}}
</style>
