<template>
  <div class="scene-hub">
    <div class="scene-hub__header">
      <div>
        <h1 class="scene-hub__title">场景管理</h1>
        <p class="scene-hub__desc">按业务场景组织研判工作：每个场景汇聚一组本体资产与研判席位</p>
      </div>
      <a-button type="primary" @click="openCreate">＋ 新建场景</a-button>
    </div>
    <a-spin :spinning="loading">
      <div v-if="!loading && scenes.length === 0" class="scene-hub__empty">暂无场景，点击右上角「新建场景」创建</div>
      <div class="scene-hub__grid">
        <div
          v-for="item in scenes"
          :key="item.id"
          class="scene-card"
          :class="{ 'scene-card--disabled': item.status !== 'enabled' }"
          @click="enterScene(item)"
        >
          <div class="scene-card__icon" :style="{ background: item.color }">{{ item.icon }}</div>
          <div class="scene-card__body">
            <h2 class="scene-card__name">{{ item.name }}</h2>
            <p class="scene-card__desc">{{ item.description }}</p>
            <div v-if="assetChips(item).length" class="scene-card__assets">
              <span v-for="chip in assetChips(item)" :key="chip" class="scene-card__chip">{{ chip }}</span>
            </div>
            <p v-if="!item.route" class="scene-card__hint">未绑定工作台</p>
          </div>
          <span class="scene-card__tag" :class="item.status === 'enabled' ? 'scene-card__tag--active' : ''">
            {{ item.status === 'enabled' ? '已启用' : '已停用' }}
          </span>
          <div class="scene-card__ops" @click.stop>
            <a @click="openEdit(item)">编辑</a>
            <a-popconfirm title="确认删除该场景？" @confirm="removeScene(item)">
              <a class="scene-card__del">删除</a>
            </a-popconfirm>
          </div>
        </div>
      </div>
    </a-spin>

    <a-modal
      v-model:open="dialogVisible"
      :title="editingId ? '编辑场景' : '新建场景'"
      @ok="submit"
      :confirm-loading="submitting"
    >
      <a-form layout="vertical">
        <a-form-item label="场景名称" required>
          <a-input v-model:value="form.name" placeholder="如：边海空情目标研判" />
        </a-form-item>
        <a-form-item label="描述">
          <a-textarea v-model:value="form.description" :rows="3" placeholder="一句话说明该场景的分析目标" />
        </a-form-item>
        <div class="scene-form__row">
          <a-form-item label="图标（emoji）">
            <a-input v-model:value="form.icon" style="width: 90px" />
          </a-form-item>
          <a-form-item label="主题色">
            <input type="color" v-model="form.color" class="scene-form__color" />
          </a-form-item>
        </div>
        <a-form-item label="绑定工作台路由">
          <a-auto-complete
            v-model:value="form.route"
            :options="ROUTE_OPTIONS"
            placeholder="选择或输入前端路由，留空表示暂不绑定"
            allow-clear
          />
        </a-form-item>
        <a-form-item label="引用本体资产（声明该场景消费了哪些本体能力）">
          <div class="scene-form__assets">
            <div v-if="assetOptions.object_classes.length" class="scene-form__asset-group">
              <div class="scene-form__asset-label">对象类</div>
              <a-checkbox-group v-model:value="form.assets.object_classes" class="scene-form__asset-list">
                <a-checkbox v-for="o in assetOptions.object_classes" :key="o" :value="o">{{ o }}</a-checkbox>
              </a-checkbox-group>
            </div>
            <div v-if="assetOptions.rules.length" class="scene-form__asset-group">
              <div class="scene-form__asset-label">业务规则</div>
              <a-checkbox-group v-model:value="form.assets.rule_ids" class="scene-form__asset-list">
                <a-checkbox v-for="r in assetOptions.rules" :key="r.id" :value="r.id">{{ r.name }}</a-checkbox>
              </a-checkbox-group>
            </div>
            <div v-if="assetOptions.actions.length" class="scene-form__asset-group">
              <div class="scene-form__asset-label">处置行动</div>
              <a-checkbox-group v-model:value="form.assets.action_ids" class="scene-form__asset-list">
                <a-checkbox v-for="a in assetOptions.actions" :key="a.id" :value="a.id">{{ a.name }}</a-checkbox>
              </a-checkbox-group>
            </div>
            <div v-if="assetOptions.agents.length" class="scene-form__asset-group">
              <div class="scene-form__asset-label">智能体</div>
              <a-checkbox-group v-model:value="form.assets.agent_ids" class="scene-form__asset-list">
                <a-checkbox v-for="g in assetOptions.agents" :key="g.id" :value="g.id">{{ g.name }}</a-checkbox>
              </a-checkbox-group>
            </div>
            <div v-if="!assetsAvailable" class="scene-form__asset-empty">暂无可引用的本体资产</div>
          </div>
        </a-form-item>
        <a-form-item label="状态">
          <a-radio-group v-model:value="form.status">
            <a-radio value="enabled">启用</a-radio>
            <a-radio value="disabled">停用</a-radio>
          </a-radio-group>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { listScenes, createScene, updateScene, deleteScene, type SceneRegistryItem, type SceneAssets } from '../../api/sceneRegistry'
import { entityApi } from '../../api/ontology'
import { ruleApi } from '../../api/rules'
import { actionApi } from '../../api/actions'
import { agentsApi } from '../../api/agents'

const router = useRouter()

// 已有的工作台页面路由，供绑定下拉选择
const ROUTE_OPTIONS = [
  { value: '/scene/military', label: '边海空情目标研判' },
  { value: '/scene/drone', label: '无人机反制处置' },
  { value: '/aip', label: '流程编排' },
  { value: '/workspace/space', label: '本体态势舱' },
]

const scenes = ref<SceneRegistryItem[]>([])
const loading = ref(false)
const dialogVisible = ref(false)
const submitting = ref(false)
const editingId = ref<string | null>(null)

const form = reactive({
  name: '',
  description: '',
  icon: '🔹',
  color: '#2E5BFF',
  route: '' as string,
  status: 'enabled' as 'enabled' | 'disabled',
  assets: { object_classes: [] as string[], rule_ids: [] as string[], action_ids: [] as string[], agent_ids: [] as string[] },
})

// 可引用的本体资产选项（加载失败不阻塞场景编辑）
const assetOptions = reactive({
  object_classes: [] as string[],
  rules: [] as { id: string; name: string }[],
  actions: [] as { id: string; name: string }[],
  agents: [] as { id: string; name: string }[],
})
const assetsAvailable = computed(
  () => assetOptions.object_classes.length + assetOptions.rules.length + assetOptions.actions.length + assetOptions.agents.length > 0,
)

async function loadAssetOptions() {
  try {
    const [entities, rules, actions, agents] = await Promise.all([
      entityApi.list().catch(() => []),
      ruleApi.list().catch(() => []),
      actionApi.list().catch(() => []),
      agentsApi.list().catch(() => []),
    ])
    assetOptions.object_classes = (entities as any[]).map((e) => e.name).filter(Boolean)
    assetOptions.rules = (rules as any[]).map((r) => ({ id: r.id, name: r.name }))
    assetOptions.actions = (actions as any[]).map((a) => ({ id: a.id, name: a.name }))
    assetOptions.agents = (agents as any[]).map((a) => ({ id: a.id, name: a.name }))
  } catch {
    /* 资产选项加载失败不影响场景编辑 */
  }
}

function assetChips(item: SceneRegistryItem): string[] {
  const a: SceneAssets | null = item.assets
  if (!a) return []
  const chips: string[] = []
  if (a.object_classes?.length) chips.push(`对象类 ${a.object_classes.length}`)
  if (a.rule_ids?.length) chips.push(`规则 ${a.rule_ids.length}`)
  if (a.action_ids?.length) chips.push(`行动 ${a.action_ids.length}`)
  if (a.agent_ids?.length) chips.push(`智能体 ${a.agent_ids.length}`)
  if (a.seats?.length) chips.push(a.seats.join('→'))
  return chips
}

async function load() {
  loading.value = true
  try {
    scenes.value = await listScenes()
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  Object.assign(form, { name: '', description: '', icon: '🔹', color: '#2E5BFF', route: '', status: 'enabled' })
  form.assets = { object_classes: [], rule_ids: [], action_ids: [], agent_ids: [] }
  dialogVisible.value = true
}

function openEdit(item: SceneRegistryItem) {
  editingId.value = item.id
  Object.assign(form, {
    name: item.name,
    description: item.description,
    icon: item.icon,
    color: item.color,
    route: item.route || '',
    status: item.status === 'disabled' ? 'disabled' : 'enabled',
  })
  form.assets = {
    object_classes: item.assets?.object_classes ? [...item.assets.object_classes] : [],
    rule_ids: item.assets?.rule_ids ? [...item.assets.rule_ids] : [],
    action_ids: item.assets?.action_ids ? [...item.assets.action_ids] : [],
    agent_ids: item.assets?.agent_ids ? [...item.assets.agent_ids] : [],
  }
  dialogVisible.value = true
}

async function submit() {
  if (!form.name.trim()) {
    message.warning('请填写场景名称')
    return
  }
  submitting.value = true
  try {
    const payload = {
      name: form.name.trim(),
      description: form.description,
      icon: form.icon || '🔹',
      color: form.color,
      route: form.route || null,
      status: form.status,
      assets: {
        object_classes: form.assets.object_classes,
        rule_ids: form.assets.rule_ids,
        action_ids: form.assets.action_ids,
        agent_ids: form.assets.agent_ids,
      },
    }
    if (editingId.value) {
      await updateScene(editingId.value, payload)
      message.success('场景已更新')
    } else {
      await createScene(payload)
      message.success('场景已创建')
    }
    dialogVisible.value = false
    await load()
  } finally {
    submitting.value = false
  }
}

async function removeScene(item: SceneRegistryItem) {
  await deleteScene(item.id)
  message.success('场景已删除')
  await load()
}

function enterScene(item: SceneRegistryItem) {
  if (item.status !== 'enabled') {
    message.info('该场景已停用，请先编辑启用')
    return
  }
  if (!item.route) {
    message.info('该场景尚未绑定工作台，可点击「编辑」绑定路由')
    return
  }
  router.push(item.route)
}

onMounted(() => {
  load()
  loadAssetOptions()
})
</script>

<style scoped>
.scene-hub {
  padding: 32px;
  max-width: 1080px;
  margin: 0 auto;
}

.scene-hub__header {
  margin-bottom: 28px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.scene-hub__title {
  font-size: var(--text-h1-size);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.scene-hub__desc {
  font-size: var(--text-body-size);
  color: var(--text-secondary);
  margin: 6px 0 0;
}

.scene-hub__empty {
  padding: 60px 0;
  text-align: center;
  color: var(--text-tertiary);
}

.scene-hub__grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 20px;
}

.scene-card {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 24px;
  border-radius: var(--radius-lg, 12px);
  background: var(--bg-card, #fff);
  border: 1px solid var(--border-primary, #e5e7eb);
  cursor: pointer;
  transition: box-shadow 0.2s, border-color 0.2s;
  position: relative;
}

.scene-card:hover {
  border-color: var(--semantic-400, #38bdf8);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
}

.scene-card--disabled {
  opacity: 0.55;
}

.scene-card__icon {
  width: 44px;
  height: 44px;
  border-radius: var(--radius-md, 8px);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  flex-shrink: 0;
}

.scene-card__body {
  flex: 1;
  min-width: 0;
}

.scene-card__name {
  font-size: var(--text-h3-size);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 6px;
}

.scene-card__desc {
  font-size: var(--text-body-size);
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.5;
}

.scene-card__hint {
  font-size: var(--text-caption-size);
  color: var(--warning-600, #f59e0b);
  margin: 6px 0 0;
}

.scene-card__assets {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.scene-card__chip {
  font-size: var(--text-caption-size);
  padding: 1px 8px;
  border-radius: var(--radius-full, 999px);
  background: var(--semantic-50, #eff6ff);
  color: var(--semantic-600, #2563eb);
  border: 1px solid var(--semantic-100, #dbeafe);
}

.scene-form__assets {
  border: 1px solid var(--border-primary, #e5e7eb);
  border-radius: var(--radius-md, 8px);
  padding: 10px 12px;
  max-height: 240px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.scene-form__asset-label {
  font-size: var(--text-caption-size);
  color: var(--text-tertiary);
  margin-bottom: 4px;
}

.scene-form__asset-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
}

.scene-form__asset-empty {
  font-size: var(--text-caption-size);
  color: var(--text-tertiary);
}

.scene-card__tag {
  position: absolute;
  top: 12px;
  right: 12px;
  font-size: var(--text-caption-size);
  padding: 2px 8px;
  border-radius: var(--radius-full, 999px);
  background: var(--bg-secondary, #f3f4f6);
  color: var(--text-tertiary, #9ca3af);
  font-weight: 500;
}

.scene-card__tag--active {
  background: var(--success-100, #dcfce7);
  color: var(--success-700, #15803d);
}

.scene-card__ops {
  position: absolute;
  bottom: 12px;
  right: 12px;
  display: none;
  gap: 10px;
  font-size: var(--text-caption-size);
}

.scene-card:hover .scene-card__ops {
  display: flex;
}

.scene-card__del {
  color: var(--danger-600, #e03131);
}

.scene-form__row {
  display: flex;
  gap: 16px;
}

.scene-form__color {
  width: 90px;
  height: 32px;
  padding: 2px;
  border: 1px solid var(--border-primary, #e5e7eb);
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
}
</style>
