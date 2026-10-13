<template>
  <div ref="viewRef" class="os-view" :class="{ 'is-hover': !!hoveredId }">
    <!-- 顶栏：场景切换 + 规模指标 -->
    <header class="os-bar">
      <div class="os-bar__id">
        <h1>本体态势舱</h1>
        <p>本体对象 · 关系 · 规则的业务全景</p>
      </div>

      <div class="os-bar__switch">
        <button
          v-for="opt in scenarioOptions"
          :key="opt.key"
          type="button"
          class="os-scn"
          :class="{ 'is-on': scenario === opt.key }"
          @click="scenario = opt.key"
        >{{ opt.label }}</button>
        <button type="button" class="os-scn" :class="{ 'is-on': spinning }" @click="spinning = !spinning">星系自转</button>
      </div>

      <div class="os-bar__stats">
        <span><b>{{ summary.node_count }}</b>本体</span>
        <span><b>{{ summary.edge_count }}</b>关系</span>
        <span><b>{{ summary.rule_count }}</b>规则</span>
        <span><b>{{ events.length }}</b>事件</span>
      </div>
    </header>

    <div v-if="err" class="os-err">{{ err }}</div>
    <div v-if="loading && !scene" class="os-loading">正在装载本体态势…</div>

    <!-- 三维场景 -->
    <SceneGraph
      v-if="scene"
      ref="sceneRef"
      :layout="layout"
      :selected-id="selectedId"
      :hovered-id="hoveredId"
      :spinning="spinning"
      @select="onCanvasSelect"
      @hover="onCanvasHover"
    />

    <!-- 左侧本体目录 -->
    <SceneRail
      v-if="scene"
      :scene="scene"
      :selected-id="selectedId"
      @focus="selectedId = $event === selectedId ? null : $event"
      @reset="selectedId = null"
      @refresh="load"
    />

    <!-- 右侧态势详情 -->
    <HudPanel
      v-if="scene"
      :node="selectedNode"
      :scene="scene"
      :events="events"
      :active-event-id="flight?.id ?? null"
      @focus="selectedId = $event"
    />

    <!-- 底部停靠区：图例与事件时间轴同列自下而上排，谁也不会压住谁 -->
    <div ref="dockRef" class="os-dock">
      <SceneLegend />

      <!-- 底部事件时间轴 -->
      <EventTimeline
        :events="events"
        :index="index"
        :playing="playing"
        :speed="speed"
        @toggle="togglePlay"
        @step="step"
        @jump="jump"
        @speed="setSpeed"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { ontologySceneApi, type OntologyScene, type SceneEvent, type SceneNode } from '../../api/ontologyScene'
import { buildLayout, domainLabel, type SceneLayout } from './components/ontology-space/layout'
import SceneGraph from './components/ontology-space/SceneGraph.vue'
import SceneRail from './components/ontology-space/SceneRail.vue'
import HudPanel from './components/ontology-space/HudPanel.vue'
import EventTimeline from './components/ontology-space/EventTimeline.vue'
import SceneLegend from './components/ontology-space/SceneLegend.vue'

const scene = ref<OntologyScene | null>(null)
const events = ref<SceneEvent[]>([])
const loading = ref(false)
const err = ref('')

const scenario = ref('all')
const selectedId = ref<string | null>(null)
const hoveredId = ref<string | null>(null)
// 相机默认交给用户：星系自转是可关的辅助，进场自动聚焦已去掉（首屏保持宏观全景）
const spinning = ref(false)

const index = ref(0)
const playing = ref(false)
const speed = ref(1)
const flight = ref<SceneEvent | null>(null)
const sceneRef = shallowRef<{ spawn: (ev: SceneEvent | null) => void } | null>(null)
const viewRef = ref<HTMLElement | null>(null)
const dockRef = ref<HTMLElement | null>(null)
/**
 * 必须是稳定引用：写成模板里的内联箭头函数会让画布每次父级渲染都重绑指针事件，
 * 重绑时 Tres 对命中对象补发一轮 over/out，hover 回写又把整棵子树重渲染（recursive updates）。
 */
function onCanvasSelect(id: string | null) {
  selectedId.value = id
}
function onCanvasHover(id: string | null) {
  hoveredId.value = id
}
let timer = 0
let dockRoa: ResizeObserver | null = null

const summary = computed(() => scene.value?.summary ?? {
  node_count: 0, edge_count: 0, domain_count: 0, attribute_count: 0, rule_count: 0, instance_count: 0,
})

const scenarioOptions = computed(() => {
  const keys = (scene.value?.domains ?? []).filter(d => d.key).map(d => d.key)
  return [
    { key: 'all', label: '全部场景' },
    ...keys.map(k => ({ key: k, label: domainLabel(k) })),
  ]
})

const layout = computed<SceneLayout>(() =>
  scene.value
    ? buildLayout(scene.value, scenario.value)
    : { galaxies: [], nodeMap: {}, edgeMap: {} },
)

const selectedNode = computed<SceneNode | null>(
  () => scene.value?.nodes.find(n => n.id === selectedId.value) ?? null,
)

async function load() {
  loading.value = true
  err.value = ''
  const dom = scenario.value === 'all' ? undefined : scenario.value
  try {
    const [s, e] = await Promise.all([
      ontologySceneApi.scene(dom),
      ontologySceneApi.events(dom, 30),
    ])
    scene.value = s
    events.value = e.events
    index.value = Math.max(0, e.events.length - 1)
    flight.value = events.value[index.value] ?? null
    if (!events.value.some(ev => ev.entity_id === selectedId.value)) selectedId.value = null
    playing.value = e.events.length > 0
    restartTimer()
  } catch (e) {
    err.value = '态势数据加载失败：' + (e instanceof Error ? e.message : String(e))
  } finally {
    loading.value = false
  }
}

/* ── 时间轴播放 ─────────────────────────────────────── */
function restartTimer() {
  window.clearInterval(timer)
  timer = 0
  if (!playing.value || events.value.length < 2) return
  timer = window.setInterval(() => step(1), 2200 / speed.value)
}

function step(delta: number) {
  const total = events.value.length
  if (!total) return
  const next = (index.value + delta + total) % total
  jump(next)
}

function jump(i: number) {
  index.value = Math.min(Math.max(i, 0), events.value.length - 1)
  const ev = events.value[index.value] ?? null
  flight.value = ev
  sceneRef.value?.spawn(ev)
}

function togglePlay() {
  playing.value = !playing.value
}

function setSpeed(v: number) {
  speed.value = v
}

watch(scenario, () => {
  selectedId.value = null
  hoveredId.value = null
  load()
})
watch([playing, speed, () => events.value.length], restartTimer)

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') selectedId.value = null
  if (e.key === ' ') {
    const el = document.activeElement
    if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA')) return
    e.preventDefault()
    togglePlay()
  }
}

onMounted(() => {
  load()
  window.addEventListener('keydown', onKey)
  /* 图例行数随窗口宽度变化，停靠区高度不是常量：量到多少就让出多少，目录底部永远不会压在图例上 */
  const view = viewRef.value
  const dock = dockRef.value
  if (view && dock) {
    const sync = () => view.style.setProperty('--dock-h', dock.offsetHeight + 16 + 'px')
    dockRoa = new ResizeObserver(sync)
    dockRoa.observe(dock)
    sync()
  }
})

onBeforeUnmount(() => {
  window.clearInterval(timer)
  window.removeEventListener('keydown', onKey)
  dockRoa?.disconnect()
  dockRoa = null
})
</script>

<style scoped>
.os-view {
  /* 底部停靠区（图例 + 事件时间轴）从容器底沿占掉的高度，挂载后由 ResizeObserver 量出真实值；
     这里只是首帧前的兜底，本体目录的 bottom 由同一个变量让位 */
  --dock-h: 188px;
  position: relative;
  margin: -24px -32px;
  height: calc(100vh - 56px);
  min-height: 620px;
  overflow: hidden;
  background: linear-gradient(180deg, #f4f8fd 0%, #e2ecf9 100%);
}
.os-view.is-hover :deep(canvas) { cursor: pointer; }

/* 底部停靠区：图例在上、时间轴在下，同列自下而上堆叠；高度由内容决定，父级按实测值给目录让位 */
.os-dock {
  position: absolute;
  left: 16px;
  right: 356px;
  bottom: 16px;
  /* 窗口极窄时图例撑高，上限挡住它继续吞掉三维画布，超出部分图例内部滚动 */
  max-height: calc(100% - 220px);
  z-index: 9;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  gap: 8px;
  pointer-events: none;
}

.os-bar {
  position: absolute;
  left: 50%;
  top: 14px;
  transform: translateX(-50%);
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 8px 18px;
  max-width: calc(100% - 24px);
  padding: 8px 16px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(160, 187, 226, 0.5);
  box-shadow: 0 12px 30px rgba(46, 87, 148, 0.12);
  backdrop-filter: blur(12px);
  font-family: var(--font-sans);
  /* 浮层不拦截指针：窄屏换行时仍可点到底下的本体目录与详情列 */
  pointer-events: none;
}
.os-bar button { pointer-events: auto; }
.os-bar__id { white-space: nowrap; }
.os-bar__id h1 { margin: 0; font-size: 15px; color: #14284a; letter-spacing: 0.04em; }
.os-bar__id p { margin: 2px 0 0; font-size: 10.5px; color: #8aa3c8; }
.os-bar__switch { display: flex; gap: 4px; }
.os-scn {
  padding: 5px 12px;
  border-radius: 9px;
  border: 1px solid transparent;
  background: transparent;
  color: #64748b;
  font-size: 11.5px;
  cursor: pointer;
}
.os-scn:hover { color: #3b5bdb; background: rgba(238, 242, 255, 0.8); }
.os-scn.is-on { background: #4c6ef5; color: #fff; font-weight: 600; }
.os-bar__stats { display: flex; gap: 14px; font-size: 10.5px; color: #8aa3c8; }
.os-bar__stats b { display: block; font-size: 15px; color: #3b5bdb; }
/* 窄屏优先保证顶栏单行，避免浮层压到左右两列 */
@media (max-width: 1180px) {
  .os-bar__stats { display: none; }
}
@media (max-width: 920px) {
  .os-bar__id p { display: none; }
}

.os-loading,
.os-err {  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  z-index: 12;
  padding: 10px 18px;
  border-radius: 12px;
  font-family: var(--font-sans);
  font-size: 12.5px;
}
.os-loading { background: rgba(255, 255, 255, 0.85); color: #6b87b0; }
.os-err {
  top: 76px;
  background: #fff4e6;
  border: 1px solid #ffd8a8;
  color: #d9480f;
}
</style>
