<template>
  <div class="instances">
    <p v-if="error" class="instances__notice">{{ error }}</p>
    <p v-else-if="loading" class="instances__notice">正在读取实例…</p>
    <template v-else>
      <p v-if="page" class="instances__source">数据来源：{{ page.asset_name }} <span>· {{ page.asset_id }}</span></p>
      <p v-if="!page?.instances.length" class="instances__notice">当前数据资产没有可显示的实例。</p>
      <div v-else class="instances__list">
        <button v-for="item in page.instances" :key="String(item.$id)" type="button"
          class="instances__item" :class="{ 'is-selected': selected?.$id === item.$id }"
          @click="selectInstance(item)">
          <strong>{{ titleOf(item) }}</strong><small>ID {{ item.$id }}</small>
        </button>
      </div>
      <div v-if="page && page.count === page.limit" class="instances__paging">
        <button type="button" :disabled="offset === 0" @click="changePage(-1)">上一页</button>
        <span>第 {{ Math.floor(offset / page.limit) + 1 }} 页</span>
        <button type="button" @click="changePage(1)">下一页</button>
      </div>
      <section v-if="selected" class="instances__detail">
        <h4>{{ titleOf(selected) }}</h4>
        <dl><template v-for="[key, value] in Object.entries(selected)" :key="key">
          <dt>{{ key === '$id' ? '实例 ID' : key }}</dt><dd>{{ value ?? '—' }}</dd>
        </template></dl>
        <h4>真实关联</h4>
        <p v-if="relationLoading" class="instances__notice">正在查询关联…</p>
        <p v-else-if="relationError" class="instances__notice">{{ relationError }}</p>
        <p v-else-if="!relations.length" class="instances__notice">该类型没有出向关系定义。</p>
        <svg v-if="graphNodes.length" class="instances__graph" viewBox="0 0 300 220" role="img" aria-label="当前实例及真实关联实例图">
          <g v-for="node in graphNodes" :key="node.key">
            <line x1="150" y1="110" :x2="node.x" :y2="node.y" stroke="#94a3b8" stroke-width="1.5" />
            <text :x="(150 + node.x) / 2" :y="(110 + node.y) / 2 - 5" class="instances__edge-label">{{ node.relation.label }}</text>
            <g class="instances__graph-target" @click="openRelated(node.relation, node.item)">
              <circle :cx="node.x" :cy="node.y" r="24" fill="#dbeafe" stroke="#4f6ef7" />
              <text :x="node.x" :y="node.y + 4" text-anchor="middle">{{ titleOf(node.item).slice(0, 5) }}</text>
            </g>
          </g>
          <circle cx="150" cy="110" r="28" fill="#4f6ef7" />
          <text x="150" y="114" text-anchor="middle" fill="white">{{ titleOf(selected).slice(0, 5) }}</text>
        </svg>
        <div v-for="relation in relations" :key="relation.name" class="instances__relation">
          <strong>{{ relation.label || relation.name }}</strong>
          <p v-if="relation.status === 'mapping_required'">待配置实例连接字段；当前只定义了类型关系。</p>
          <p v-else-if="!relation.instances.length">没有匹配的实例。</p>
          <template v-else>
            <p class="instances__source">目标来源：{{ relation.asset_name }}</p>
            <button v-for="related in relation.instances" :key="String(related.$id)" type="button"
              class="instances__related" @click="openRelated(relation, related)">
              {{ titleOf(related) }} <small>→</small>
            </button>
          </template>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ontologyInstancesApi, type InstancePage, type InstanceRelation, type OntologyInstance } from '../../api/ontologyInstances'

const props = defineProps<{ objectName: string; titleProperty?: string; focusId?: string | number | null }>()
const emit = defineEmits<{ (e: 'navigate', name: string, id: string | number): void }>()
const page = ref<InstancePage | null>(null)
const offset = ref(0)
const selected = ref<OntologyInstance | null>(null)
const relations = ref<InstanceRelation[]>([])
const loading = ref(false)
const relationLoading = ref(false)
const error = ref('')
const relationError = ref('')
let requestId = 0
const graphNodes = computed(() => {
  const pairs = relations.value.filter(relation => relation.status === 'queried')
    .flatMap(relation => relation.instances.map(item => ({ relation, item }))).slice(0, 6)
  return pairs.map((pair, index) => {
    const angle = -Math.PI / 2 + 2 * Math.PI * index / pairs.length
    return { ...pair, key: `${pair.relation.name}:${pair.item.$id}`, x: 150 + 100 * Math.cos(angle), y: 110 + 73 * Math.sin(angle) }
  })
})

function messageOf(error: unknown): string {
  const response = error as { response?: { data?: { detail?: string } } }
  return response.response?.data?.detail || '读取失败，请检查数据资产绑定及访问权限。'
}

function titleOf(item: OntologyInstance): string {
  const value = item[props.titleProperty || ''] ?? Object.entries(item).find(([key, v]) => key !== '$id' && v != null)?.[1]
  return String(value ?? item.$id)
}

async function loadPage() {
  const current = ++requestId
  loading.value = true
  error.value = ''
  selected.value = null
  relations.value = []
  try {
    const result = await ontologyInstancesApi.list(props.objectName, offset.value)
    if (current === requestId) {
      page.value = result
      if (props.focusId != null) {
        const matching = result.instances.find(item => String(item.$id) === String(props.focusId))
        const focused = matching || await ontologyInstancesApi.detail(props.objectName, props.focusId)
        if (current === requestId) void selectInstance(focused)
      }
    }
  } catch (cause) {
    if (current === requestId) { page.value = null; error.value = messageOf(cause) }
  } finally {
    if (current === requestId) loading.value = false
  }
}

async function selectInstance(item: OntologyInstance) {
  selected.value = item
  relations.value = []
  relationError.value = ''
  relationLoading.value = true
  const current = ++requestId
  try {
    const result = await ontologyInstancesApi.relations(props.objectName, item.$id)
    if (current === requestId) relations.value = result.relations
  } catch (cause) {
    if (current === requestId) relationError.value = messageOf(cause)
  } finally {
    if (current === requestId) relationLoading.value = false
  }
}

function openRelated(relation: InstanceRelation, item: OntologyInstance) {
  if (relation.target_api_name) emit('navigate', relation.target_api_name, item.$id)
}

function changePage(direction: number) {
  offset.value = Math.max(0, offset.value + direction * (page.value?.limit || 20))
  loadPage()
}

watch(() => props.objectName, () => { offset.value = 0; loadPage() }, { immediate: true })
</script>

<style scoped>
.instances { font-size: 12px; color: #334155; }
.instances__notice { padding: 12px; color: #64748b; background: #f8fafc; border-radius: 8px; line-height: 1.5; }
.instances__source { color: #64748b; font-size: 11px; overflow-wrap: anywhere; }
.instances__source span { opacity: .6; }
.instances__list { display: grid; gap: 6px; }
.instances__item, .instances__related { text-align: left; border: 1px solid #dbe3ef; border-radius: 8px; background: #fff; color: inherit; cursor: pointer; padding: 9px; }
.instances__item { display: flex; justify-content: space-between; gap: 8px; }
.instances__item strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.instances__item small { color: #64748b; white-space: nowrap; }
.instances__item.is-selected { border-color: #4f6ef7; background: #eff6ff; }
.instances__paging { display: flex; justify-content: space-between; align-items: center; margin: 10px 0; }
.instances__paging button { border: 0; background: none; color: #3b5bdb; cursor: pointer; }
.instances__paging button:disabled { color: #94a3b8; }
.instances__detail { margin-top: 16px; border-top: 1px solid #e2e8f0; }
.instances__detail h4 { margin: 12px 0 8px; }
.instances__detail dl { display: grid; grid-template-columns: minmax(70px, 1fr) 2fr; margin: 0; gap: 4px 8px; }
.instances__detail dt { color: #64748b; }
.instances__detail dd { margin: 0; overflow-wrap: anywhere; }
.instances__relation { padding: 9px; background: #f8fafc; border-radius: 8px; margin-bottom: 8px; }
.instances__relation p { margin: 5px 0; color: #64748b; }
.instances__related { display: block; width: 100%; margin-top: 5px; }
.instances__graph { display: block; width: 100%; max-height: 220px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 9px; margin: 8px 0; }
.instances__graph text { font-size: 8px; pointer-events: none; }
.instances__graph .instances__edge-label { fill: #64748b; font-size: 7px; }
.instances__graph-target { cursor: pointer; }
:global([data-theme="dark"]) .instances { color: #e0e1e3; }
:global([data-theme="dark"]) .instances__notice,
:global([data-theme="dark"]) .instances__relation,
:global([data-theme="dark"]) .instances__graph { background: #25262b; border-color: #44454a; }
:global([data-theme="dark"]) .instances__item,
:global([data-theme="dark"]) .instances__related { background: #2c2d31; color: #e0e1e3; border-color: #44454a; }
:global([data-theme="dark"]) .instances__item.is-selected { border-color: #748ffc; background: #343856; }
</style>
