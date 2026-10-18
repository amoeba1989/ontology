<template>
  <div class="os-view">
    <header class="os-bar">
      <div class="os-bar__id"><h1>本体拓扑工作台</h1><p>对象、关系、规则与业务事件的二维网络</p></div>
      <div class="os-bar__switch">
        <button v-for="opt in scenarioOptions" :key="opt.key" class="os-btn" :class="{ active: scenario === opt.key }" @click="scenario = opt.key">{{ opt.label }}</button>
      </div>
      <div class="os-bar__tools">
        <select v-model="layoutName" title="拓扑布局"><option value="fcose">关系网络</option><option value="concentric">同心分析</option><option value="grid">网格总览</option></select>
        <button class="os-btn" @click="graphRef?.runLayout(layoutName)">重新布局</button>
        <button class="os-btn" @click="graphRef?.fit()">适应画布</button>
        <button class="os-btn" @click="load">刷新数据</button>
      </div>
      <div class="os-bar__stats"><span><b>{{ summary.node_count }}</b>对象</span><span><b>{{ summary.edge_count }}</b>关系</span><span><b>{{ summary.rule_count }}</b>规则</span><span><b>{{ summary.instance_count }}</b>实例</span></div>
    </header>

    <div v-if="err" class="os-message error">{{ err }}</div>
    <div v-if="loading && !scene" class="os-message">正在加载本体拓扑…</div>

    <CytoscapeGraph v-if="scene" ref="graphRef" :scene="scene" :selected-id="selectedId" :active-event="flight" :layout-name="layoutName" @select="selectedId = $event" @hover="hoveredId = $event" />
    <SceneRail v-if="scene" :scene="scene" :selected-id="selectedId" @focus="selectFromRail" @reset="reset" @refresh="load" />
    <HudPanel v-if="scene" :node="selectedNode" :scene="scene" :events="events" :active-event-id="flight?.id ?? null" @focus="selectNode" />

    <div class="os-legend">
      <span><i class="diamond" />核心对象</span><span><i class="rect" />关联对象</span><span><i class="round" />事件对象</span>
      <span><i class="rule" />橙框表示绑定规则</span><span><i class="line" />箭头表示关系方向</span><em>节点尺寸随实例数量对数增长</em>
    </div>

    <div class="os-timeline"><EventTimeline :events="events" :index="index" :playing="playing" :speed="speed" @toggle="playing = !playing" @step="step" @jump="jump" @speed="speed = $event" /></div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { ontologySceneApi, type OntologyScene, type SceneEvent, type SceneNode } from '../../api/ontologyScene'
import { domainLabel } from './components/ontology-space/topologyMeta'
import CytoscapeGraph from './components/ontology-space/CytoscapeGraph.vue'
import SceneRail from './components/ontology-space/SceneRail.vue'
import HudPanel from './components/ontology-space/HudPanel.vue'
import EventTimeline from './components/ontology-space/EventTimeline.vue'

type LayoutName = 'fcose' | 'concentric' | 'grid'
const scene = ref<OntologyScene | null>(null)
const events = ref<SceneEvent[]>([])
const loading = ref(false)
const err = ref('')
const scenario = ref('all')
const layoutName = ref<LayoutName>('fcose')
const selectedId = ref<string | null>(null)
const hoveredId = ref<string | null>(null)
const index = ref(0)
const playing = ref(false)
const speed = ref(1)
const flight = ref<SceneEvent | null>(null)
const graphRef = shallowRef<{ fit: () => void; runLayout: (name: LayoutName) => void; focus: (id: string) => void } | null>(null)
let timer = 0

const summary = computed(() => scene.value?.summary ?? { node_count: 0, edge_count: 0, domain_count: 0, attribute_count: 0, rule_count: 0, instance_count: 0 })
const scenarioOptions = computed(() => [{ key: 'all', label: '全部场景' }, ...(scene.value?.domains ?? []).filter(d => d.key).map(d => ({ key: d.key, label: domainLabel(d.key) }))])
const selectedNode = computed<SceneNode | null>(() => scene.value?.nodes.find(node => node.id === selectedId.value) ?? null)

async function load() {
  loading.value = true; err.value = ''
  const domain = scenario.value === 'all' ? undefined : scenario.value
  try {
    const [nextScene, nextEvents] = await Promise.all([ontologySceneApi.scene(domain), ontologySceneApi.events(domain, 30)])
    scene.value = nextScene; events.value = nextEvents.events
    index.value = Math.max(0, events.value.length - 1); flight.value = events.value[index.value] ?? null
    if (!nextScene.nodes.some(node => node.id === selectedId.value)) selectedId.value = null
    playing.value = false
  } catch (error) { err.value = '拓扑数据加载失败：' + (error instanceof Error ? error.message : String(error)) }
  finally { loading.value = false }
}

function selectNode(id: string) { selectedId.value = id; graphRef.value?.focus(id) }
function selectFromRail(id: string) { selectedId.value = selectedId.value === id ? null : id }
function reset() { selectedId.value = null; graphRef.value?.fit() }
function jump(next: number) { index.value = Math.min(Math.max(next, 0), events.value.length - 1); flight.value = events.value[index.value] ?? null }
function step(delta: number) { if (events.value.length) jump((index.value + delta + events.value.length) % events.value.length) }
function restartTimer() { window.clearInterval(timer); if (playing.value && events.value.length > 1) timer = window.setInterval(() => step(1), 2200 / speed.value) }

watch(scenario, () => { selectedId.value = null; load() })
watch([playing, speed, () => events.value.length], restartTimer)
function onKey(event: KeyboardEvent) { if (event.key === 'Escape') reset() }
onMounted(() => { load(); window.addEventListener('keydown', onKey) })
onBeforeUnmount(() => { window.clearInterval(timer); window.removeEventListener('keydown', onKey) })
</script>

<style scoped>
.os-view{position:relative;margin:-24px -32px;height:calc(100vh - 56px);min-height:660px;overflow:hidden;background:#f6f8fc}.os-bar{position:absolute;z-index:12;left:16px;right:16px;top:14px;display:flex;align-items:center;gap:16px;padding:10px 14px;border:1px solid #dbe3ef;border-radius:12px;background:rgba(255,255,255,.94);box-shadow:0 8px 24px rgba(40,67,104,.09);backdrop-filter:blur(10px)}.os-bar__id{min-width:190px}.os-bar__id h1{margin:0;color:#172b4d;font-size:15px}.os-bar__id p{margin:3px 0 0;color:#8190a6;font-size:10.5px}.os-bar__switch,.os-bar__tools{display:flex;align-items:center;gap:5px}.os-bar__switch{flex:1;overflow:auto}.os-bar__tools{border-left:1px solid #e5e9f0;padding-left:12px}.os-bar__tools select,.os-btn{height:30px;border:1px solid #dbe2ec;border-radius:7px;background:#fff;color:#53657e;font-size:11px;padding:0 10px;white-space:nowrap;cursor:pointer}.os-btn:hover{border-color:#748ffc;color:#4263eb}.os-btn.active{border-color:#4c6ef5;background:#4c6ef5;color:#fff}.os-bar__stats{display:flex;gap:10px;color:#8291a6;font-size:9.5px}.os-bar__stats span{text-align:center}.os-bar__stats b{display:block;color:#3451b2;font-size:14px}.os-message{position:absolute;z-index:20;left:50%;top:50%;transform:translate(-50%,-50%);padding:10px 16px;border:1px solid #dbe3ef;border-radius:9px;background:#fff;color:#687b95;font-size:12px}.os-message.error{top:86px;color:#c92a2a;background:#fff5f5;border-color:#ffc9c9}.os-legend{position:absolute;z-index:10;left:276px;right:356px;bottom:82px;display:flex;align-items:center;gap:16px;padding:8px 12px;border:1px solid #dbe3ef;border-radius:9px;background:rgba(255,255,255,.92);color:#53657e;font-size:10.5px;pointer-events:none}.os-legend span{display:flex;align-items:center;gap:6px;white-space:nowrap}.os-legend em{margin-left:auto;color:#8b98aa;font-style:normal}.os-legend i{display:inline-block;width:10px;height:10px;background:#4263eb}.os-legend .diamond{transform:rotate(45deg)}.os-legend .rect{width:14px;border-radius:3px;background:#12b886}.os-legend .round{border-radius:50%;background:#f08c00}.os-legend .rule{background:transparent;border:3px solid #f59f00;border-radius:50%}.os-legend .line{width:18px;height:0;border-top:2px solid #849bb8;background:transparent}.os-timeline{position:absolute;z-index:10;left:16px;right:356px;bottom:16px}
html[data-theme="dark"] .os-view{background:#17191e}html[data-theme="dark"] .os-bar,html[data-theme="dark"] .os-legend{background:rgba(32,35,42,.94);border-color:#383e49;box-shadow:0 8px 24px rgba(0,0,0,.35)}html[data-theme="dark"] .os-bar__id h1{color:#edf0f4}html[data-theme="dark"] .os-bar__id p,html[data-theme="dark"] .os-bar__stats,html[data-theme="dark"] .os-legend{color:#98a4b5}html[data-theme="dark"] .os-bar__tools{border-color:#3b404b}html[data-theme="dark"] .os-bar__tools select,html[data-theme="dark"] .os-btn{background:#292d35;border-color:#414754;color:#c8d0dc}html[data-theme="dark"] .os-btn.active{background:#4c6ef5;color:#fff}html[data-theme="dark"] .os-bar__stats b{color:#91a7ff}
@media(max-width:1200px){.os-bar__stats{display:none}.os-legend{right:16px}.os-timeline{right:16px}}@media(max-width:900px){.os-bar__id{display:none}.os-bar__tools .os-btn:not(:last-child){display:none}.os-legend{display:none}}
</style>
