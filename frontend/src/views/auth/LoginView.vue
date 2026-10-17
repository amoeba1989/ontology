<template>
  <div class="login">
    <!-- 装饰层：等距底图 + 蒙版 + 知识图谱（双层景深，程序化生成，纯视觉不承载信息） -->
    <div class="login__photo" aria-hidden="true"></div>
    <div class="login__scrim" aria-hidden="true"></div>

    <svg class="login__graph" :viewBox="graph.vb" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <!-- 远景：细碎节点 + 最近邻连线，只负责铺出"网络"的密度 -->
      <g class="graph__far">
        <g class="graph__lines">
          <line v-for="(e, i) in graph.farEdges" :key="'fe' + i" :x1="e.x1" :y1="e.y1" :x2="e.x2" :y2="e.y2" />
        </g>
        <g class="graph__dots">
          <circle v-for="(n, i) in graph.farNodes" :key="'fn' + i" :cx="n.x" :cy="n.y" :r="n.r" />
        </g>
      </g>

      <!-- 近景：中心留白，实体绕着卡片成环分布 -->
      <g class="graph__near">
        <g class="graph__lines">
          <line v-for="(e, i) in graph.edges" :key="'ne' + i" :x1="e.x1" :y1="e.y1" :x2="e.x2" :y2="e.y2" />
        </g>
        <g class="graph__rings">
          <circle v-for="(n, i) in graph.hubs" :key="'hr' + i" :cx="n.x" :cy="n.y" :r="n.r + 6.5" />
        </g>
        <g>
          <circle
            v-for="(n, i) in graph.nodes"
            :key="'nn' + i"
            :cx="n.x"
            :cy="n.y"
            :r="n.r"
            :fill="n.c"
            :fill-opacity="n.o"
          />
        </g>
        <path class="graph__flow" :d="graph.flowPath" fill="none" />
      </g>
    </svg>

    <button class="toggle" type="button" :title="themeStore.isDark ? '切换到明快模式' : '切换到暗黑模式'" @click="themeStore.toggle()">
      <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
        <g v-if="themeStore.isDark">
          <circle cx="8" cy="8" r="3.2" stroke="currentColor" stroke-width="1.3" />
          <path d="M8 1.4v1.6M8 13v1.6M1.4 8h1.6M13 8h1.6M3.4 3.4l1.1 1.1M11.5 11.5l1.1 1.1M12.6 3.4l-1.1 1.1M4.5 11.5l-1.1 1.1" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" />
        </g>
        <path v-else d="M13.4 9.8A5.8 5.8 0 016.2 2.6a5.6 5.6 0 107.2 7.2z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round" />
      </svg>
    </button>

    <main class="card">
      <div class="brand">
        <div class="brand__mark">
          <img src="/images/ontology/zhibi.png" alt="知彼" />
        </div>
        <h1 class="brand__name">知彼<span>ONTOLOGY</span></h1>
        <p class="brand__tag">目标行为研判 · OODA 杀伤链本体平台</p>
      </div>

      <form class="form" @submit.prevent="handleLogin">
        <label class="field">
          <span class="field__label">用户名</span>
          <span class="field__box">
            <svg class="field__icon" width="15" height="15" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="5.5" r="2.6" stroke="currentColor" stroke-width="1.3" />
              <path d="M3 13.2c.7-2.3 2.5-3.4 5-3.4s4.3 1.1 5 3.4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" />
            </svg>
            <input
              v-model="username"
              type="text"
              class="field__input"
              placeholder="请输入用户名"
              autocomplete="username"
              autofocus
            />
          </span>
        </label>

        <label class="field">
          <span class="field__label">密码</span>
          <span class="field__box">
            <svg class="field__icon" width="15" height="15" viewBox="0 0 16 16" fill="none">
              <rect x="3.2" y="7" width="9.6" height="6.2" rx="1.6" stroke="currentColor" stroke-width="1.3" />
              <path d="M5.6 7V5.4a2.4 2.4 0 014.8 0V7" stroke="currentColor" stroke-width="1.3" />
            </svg>
            <input
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              class="field__input"
              placeholder="请输入密码"
              autocomplete="current-password"
            />
            <button
              type="button"
              class="field__reveal"
              :title="showPassword ? '隐藏密码' : '显示密码'"
              @click="showPassword = !showPassword"
            >
              <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                <path d="M1.6 8c1.6-2.8 3.8-4.2 6.4-4.2S12.8 5.2 14.4 8c-1.6 2.8-3.8 4.2-6.4 4.2S3.2 10.8 1.6 8z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round" />
                <circle cx="8" cy="8" r="1.8" stroke="currentColor" stroke-width="1.3" />
                <path v-if="showPassword" d="M3 13L13 3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
              </svg>
            </button>
          </span>
        </label>

        <p v-if="error" class="form__error">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
            <circle cx="8" cy="8" r="6.2" stroke="currentColor" stroke-width="1.3" />
            <path d="M8 4.8v4M8 11h.01" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
          </svg>
          {{ error }}
        </p>

        <button type="submit" class="form__btn" :disabled="loading">
          {{ loading ? '登录中...' : '登录' }}
        </button>
      </form>
    </main>

    <footer class="login__foot">{{ buildInfo }}</footer>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../../store/auth'
import { useThemeStore } from '../../store/theme'

const router = useRouter()
const authStore = useAuthStore()
const themeStore = useThemeStore()
const buildInfo = __APP_BUILD_INFO__

const username = ref('admin')
const password = ref('bonc')
const showPassword = ref(false)
const error = ref('')
const loading = ref(false)

async function handleLogin() {
  error.value = ''
  loading.value = true
  try {
    await authStore.login({ username: username.value, password: password.value })
    router.push('/dashboard')
  } catch (e: any) {
    error.value = e?.message || '登录失败，请检查用户名和密码'
  } finally {
    loading.value = false
  }
}

/* ── 背景知识图谱：固定种子程序化生成，并按视口比例铺开 ──
 * viewBox 宽度固定、高度按当前宽高比换算，slice 就不会裁掉上下那圈节点；
 * 中心留白区按卡片实际尺寸换算，超宽屏也不会出现图谱压到表单的情况。
 */

type GNode = { x: number; y: number; r: number; c: string; o: number }
type GEdge = { x1: number; y1: number; x2: number; y2: number }

function mulberry32(seed: number) {
  let a = seed
  return () => {
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

// 主色为结构蓝，其余三层色标只做零星点缀
const PALETTE: Array<[string, number]> = [['#4c6ef5', 0.62], ['#20c997', 0.2], ['#7950f2', 0.1], ['#f59f00', 0.08]]
function pickColor(rnd: () => number) {
  const roll = rnd()
  let acc = 0
  for (const [c, w] of PALETTE) {
    acc += w
    if (roll <= acc) return c
  }
  return '#4c6ef5'
}

const VB_W = 1600

function currentBox() {
  const ratio = Math.min(Math.max(window.innerWidth / Math.max(window.innerHeight, 1), 0.42), 2.7)
  const w = VB_W
  const h = Math.round(VB_W / ratio)
  // slice 下的实际缩放：viewBox 单位 → CSS px
  const scale = Math.max(window.innerWidth / w, window.innerHeight / h)
  return {
    w,
    h,
    // 卡片半宽 206 + 余量、半高约 240 + 余量；窄屏卡片几乎占满宽度，
    // 留白区封顶在画面 30%/34%，让图谱退回上下两端而不是整层消失
    clearRx: Math.min((206 + 62) / scale, w * 0.3),
    clearRy: Math.min((240 + 70) / scale, h * 0.34),
  }
}

function buildGraph(seed: number) {
  const { w, h, clearRx, clearRy } = currentBox()
  const cx = w / 2
  const cy = h / 2
  const rnd = mulberry32(seed)

  const inClear = (x: number, y: number) => ((x - cx) / clearRx) ** 2 + ((y - cy) / clearRy) ** 2 < 1
  const outOfFrame = (x: number, y: number) => x < w * 0.022 || x > w * 0.978 || y < h * 0.03 || y > h * 0.97

  const hubs: GNode[] = []
  const nodes: GNode[] = []
  const edges: GEdge[] = []
  const farNodes: GNode[] = []
  const farEdges: GEdge[] = []

  const ratio = w / h
  const HUB_COUNT = 6 + (ratio > 1.85 ? 1 : 0) + (ratio > 2.2 ? 1 : 0)
  for (let i = 0; i < HUB_COUNT; i++) {
    const a = (i / HUB_COUNT) * Math.PI * 2 + (rnd() - 0.5) * 0.55
    hubs.push({
      x: cx + Math.cos(a) * (w * (0.31 + rnd() * 0.06)),
      y: cy + Math.sin(a) * (h * (0.33 + rnd() * 0.07)),
      r: 4.2 + rnd() * 1.4,
      c: '#4c6ef5',
      o: 0.9,
    })
  }

  const leafGroups: GNode[][] = []
  hubs.forEach((hub, hi) => {
    const leaves: GNode[] = [hub]
    for (let i = 0, count = 5 + Math.floor(rnd() * 4); i < count; i++) {
      let placed: GNode | null = null
      for (let attempt = 0; attempt < 6 && !placed; attempt++) {
        const a = rnd() * Math.PI * 2
        const d = w * 0.028 + rnd() * w * 0.062
        const x = hub.x + Math.cos(a) * d
        const y = hub.y + Math.sin(a) * d * 0.86
        if (inClear(x, y) || outOfFrame(x, y)) continue
        placed = { x, y, r: 1.9 + rnd() * 2.4, c: pickColor(rnd), o: 0.5 + rnd() * 0.4 }
      }
      if (!placed) continue
      leaves.push(placed)
      nodes.push(placed)
      edges.push({ x1: hub.x, y1: hub.y, x2: placed.x, y2: placed.y })
      // 组内弦：让每个簇看起来是网，而不是放射状的花瓣
      if (leaves.length > 3 && rnd() > 0.55) {
        const other = leaves[1 + Math.floor(rnd() * (leaves.length - 2))]
        edges.push({ x1: placed.x, y1: placed.y, x2: other.x, y2: other.y })
      }
    }
    leafGroups.push(leaves)
    // 枢纽成环
    const next = hubs[(hi + 1) % HUB_COUNT]
    edges.push({ x1: hub.x, y1: hub.y, x2: next.x, y2: next.y })
  })

  // 跨簇的少量长边
  for (let i = 0; i < 5; i++) {
    const g1 = leafGroups[Math.floor(rnd() * leafGroups.length)]
    const g2 = leafGroups[Math.floor(rnd() * leafGroups.length)]
    const a = g1[1 + Math.floor(rnd() * Math.max(1, g1.length - 1))]
    const b = g2[1 + Math.floor(rnd() * Math.max(1, g2.length - 1))]
    if (!a || !b || Math.hypot(a.x - b.x, a.y - b.y) > w * 0.34) continue
    edges.push({ x1: a.x, y1: a.y, x2: b.x, y2: b.y })
  }

  nodes.unshift(...hubs)

  // 远景：稀疏散点 + 最近邻连线，密度随面积走
  const farCount = Math.round((w * h) / 44000)
  for (let i = 0; i < farCount; i++) {
    let x = 0
    let y = 0
    for (let attempt = 0; attempt < 8; attempt++) {
      x = w * 0.02 + rnd() * w * 0.96
      y = h * 0.03 + rnd() * h * 0.94
      if (!inClear(x, y)) break
    }
    if (inClear(x, y)) continue
    farNodes.push({ x, y, r: 1.1 + rnd() * 1.1, c: '#4c6ef5', o: 0.4 + rnd() * 0.25 })
  }
  const linkMax = w * 0.16
  farNodes.forEach((n, i) => {
    let best = -1
    let bestD = Infinity
    farNodes.forEach((m, j) => {
      if (i === j) return
      const d = Math.hypot(n.x - m.x, n.y - m.y)
      if (d < bestD) {
        bestD = d
        best = j
      }
    })
    if (best >= 0 && bestD < linkMax && best > i) {
      farEdges.push({ x1: n.x, y1: n.y, x2: farNodes[best].x, y2: farNodes[best].y })
    }
  })

  const flowPath = hubs.map((p, i) => `${i ? 'L' : 'M'}${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ') + ' Z'

  return { vb: `0 0 ${w} ${h}`, hubs, nodes, edges, farNodes, farEdges, flowPath }
}

const GRAPH_SEED = 0x2f6a19
const graph = ref(buildGraph(GRAPH_SEED))
let resizeTimer: number | undefined

function onResize() {
  window.clearTimeout(resizeTimer)
  resizeTimer = window.setTimeout(() => {
    graph.value = buildGraph(GRAPH_SEED)
  }, 180)
}

onMounted(() => window.addEventListener('resize', onResize))
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  window.clearTimeout(resizeTimer)
})
</script>

<style scoped>
/*
 * 画面构成：底图（项目自带的等距方块场）→ 蒙版压住亮度 → 知识图谱层
 * （远景散点 + 近景枢纽成环，中心留白让卡片站住）→ 悬浮白卡。
 * 图谱整层透明度不到 0.5，只作为背景纹理存在；
 * 全页唯一的高饱和色块留给主按钮。
 */
.login {
  position: relative;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-5);
  padding: var(--space-8) var(--space-4);
  background: #e9edf6;
  overflow: hidden;
}

/* 底图：等距方块场，轻微放大避免边缘留白 */
.login__photo {
  position: absolute;
  inset: 0;
  background: url('/images/ontology/bg.png') center 62% / cover no-repeat;
  transform: scale(1.06);
  transform-origin: 50% 60%;
}

/* 蒙版：中心压亮让卡片站得住，四周透出底图纹理 */
.login__scrim {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(58% 54% at 50% 46%, rgba(248, 249, 250, 0.93), rgba(248, 249, 250, 0.6) 56%, rgba(248, 249, 250, 0.14) 100%),
    linear-gradient(180deg, rgba(233, 237, 246, 0.5), rgba(233, 237, 246, 0) 42%);
}

/*
 * 图谱层：整层透明度压到很低，只当作背景纹理。
 * 远景更细更淡、慢速反向漂移，近景稍快，两层错开形成景深。
 */
.login__graph {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  opacity: 0.42;
}
.graph__far {
  animation: driftFar 38s ease-in-out infinite alternate;
}
.graph__far .graph__lines {
  fill: none;
  stroke: #4c6ef5;
  stroke-width: 0.55;
  opacity: 0.3;
}
.graph__far .graph__dots circle {
  fill: #4c6ef5;
  opacity: 0.5;
}
.graph__near {
  animation: driftNear 26s ease-in-out infinite alternate;
}
.graph__near .graph__lines {
  fill: none;
  stroke: #4c6ef5;
  stroke-width: 0.85;
  opacity: 0.42;
}
.graph__rings {
  fill: none;
  stroke: #4c6ef5;
  stroke-width: 0.85;
  opacity: 0.3;
}
/* 沿枢纽环缓慢巡走的信号点，够慢够淡才不会抢焦点 */
.graph__flow {
  stroke: #4c6ef5;
  stroke-width: 1.2;
  stroke-linecap: round;
  stroke-dasharray: 1.5 34;
  opacity: 0.5;
  animation: flow 46s linear infinite;
}

@keyframes driftNear {
  from { transform: translate3d(-6px, 4px, 0); }
  to   { transform: translate3d(6px, -7px, 0); }
}
@keyframes driftFar {
  from { transform: translate3d(4px, -3px, 0); }
  to   { transform: translate3d(-4px, 3px, 0); }
}
@keyframes flow {
  to { stroke-dashoffset: -428; }
}

.toggle {
  position: absolute;
  top: var(--space-6);
  right: var(--space-6);
  z-index: 3;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  color: var(--neutral-600);
  background: rgba(255, 255, 255, 0.78);
  backdrop-filter: blur(8px);
  border: 1px solid var(--neutral-200);
  border-radius: var(--radius-full);
  cursor: pointer;
  box-shadow: var(--shadow-sm);
  transition: color var(--transition-fast), border-color var(--transition-fast), transform var(--transition-slow);
}
.toggle:hover {
  color: var(--semantic-600);
  border-color: var(--semantic-300);
  transform: rotate(-20deg);
}

/* ── 卡片 ── */
.card {
  position: relative;
  z-index: 2;
  width: min(412px, 100%);
  padding: var(--space-8) var(--space-8) var(--space-6);
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(12px) saturate(1.2);
  border: 1px solid rgba(255, 255, 255, 0.85);
  border-radius: 22px;
  /* 贴地细节 + 环境扩散 + 一层蓝色氛围光 */
  box-shadow:
    0 1px 2px rgba(15, 17, 23, 0.05),
    0 18px 36px -18px rgba(15, 17, 23, 0.22),
    0 42px 84px -30px rgba(55, 79, 199, 0.42);
  animation: rise 540ms cubic-bezier(0.22, 1, 0.36, 1) both;
}
/* 卡顶那道蓝线 */
.card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 26px;
  right: 26px;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--semantic-500) 32%, var(--tier2-primary) 68%, transparent);
  opacity: 0.6;
}

@keyframes rise {
  from { opacity: 0; transform: translateY(12px) scale(0.985); }
  to   { opacity: 1; transform: none; }
}

/* ── 品牌区 ── */
.brand {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 28px;
}
.brand__mark {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  margin-bottom: var(--space-4);
  border-radius: 16px;
  background: var(--neutral-0);
  box-shadow:
    0 0 0 1px rgba(76, 110, 245, 0.14),
    0 0 0 5px rgba(76, 110, 245, 0.06),
    0 8px 18px -10px rgba(76, 110, 245, 0.55);
}
.brand__mark img {
  width: 40px;
  height: 40px;
  border-radius: 10px;
}
.brand__name {
  display: flex;
  align-items: baseline;
  gap: 7px;
  margin: 0;
  font-size: 21px;
  font-weight: 600;
  letter-spacing: 0.6px;
  line-height: 1.2;
  color: var(--neutral-900);
}
.brand__name span {
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 2.2px;
  color: var(--neutral-500);
}
.brand__tag {
  margin: 8px 0 0;
  font-size: var(--text-caption-size);
  letter-spacing: 0.2px;
  color: var(--neutral-600);
}

/* ── 表单 ── */
.form {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
.field {
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.field__label {
  font-size: var(--text-code-size);
  font-weight: 500;
  letter-spacing: 0.2px;
  color: var(--neutral-700);
}
.field__box {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  height: 44px;
  padding: 0 13px;
  background: var(--neutral-50);
  border: 1px solid var(--neutral-200);
  border-radius: 11px;
  box-shadow: inset 0 1px 2px rgba(15, 17, 23, 0.035);
  transition: border-color var(--transition-normal), background var(--transition-normal), box-shadow var(--transition-normal);
}
.field__box:hover {
  border-color: var(--neutral-300);
}
.field__box:focus-within {
  background: var(--neutral-0);
  border-color: var(--semantic-500);
  box-shadow: 0 0 0 3.5px rgba(76, 110, 245, 0.13);
}
.field__icon {
  flex-shrink: 0;
  color: var(--neutral-500);
  transition: color var(--transition-normal);
}
.field__box:focus-within .field__icon {
  color: var(--semantic-600);
}
.field__input {
  flex: 1;
  min-width: 0;
  height: 100%;
  border: none;
  background: transparent;
  color: var(--neutral-900);
  font-size: var(--text-body-size);
  outline: none;
}
.field__input::placeholder {
  color: var(--neutral-500);
}
.field__reveal {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  margin-right: -4px;
  padding: 5px;
  border: none;
  background: transparent;
  color: var(--neutral-500);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: color var(--transition-fast), background var(--transition-fast);
}
.field__reveal:hover {
  color: var(--semantic-600);
  background: var(--neutral-100);
}

.form__error {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  padding: 9px 11px;
  font-size: var(--text-code-size);
  color: var(--status-error);
  background: var(--status-error-bg);
  border: 1px solid rgba(250, 82, 82, 0.24);
  border-radius: 9px;
}

.form__btn {
  position: relative;
  height: 44px;
  margin-top: var(--space-2);
  border: none;
  border-radius: 11px;
  background: linear-gradient(180deg, var(--semantic-600), var(--semantic-800));
  color: #fff;
  font-size: var(--text-body-medium-size);
  font-weight: 600;
  letter-spacing: 1px;
  cursor: pointer;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.22),
    0 8px 18px -10px rgba(76, 110, 245, 0.85);
  transition: transform var(--transition-fast), box-shadow var(--transition-normal), filter var(--transition-normal);
}
.form__btn:hover:not(:disabled) {
  transform: translateY(-1px);
  filter: brightness(1.05);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.26),
    0 12px 26px -10px rgba(76, 110, 245, 0.95);
}
.form__btn:active:not(:disabled) {
  transform: translateY(0);
  filter: brightness(0.96);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.16), 0 4px 10px -6px rgba(76, 110, 245, 0.8);
}
.form__btn:disabled {
  opacity: 0.62;
  cursor: not-allowed;
}

.login__foot {
  position: relative;
  z-index: 2;
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.3px;
  color: var(--neutral-600);
  opacity: 0.75;
}

/*
 * ── 暗黑 ──
 * 底图不反相（反相会把浅色方块场变成一片中灰，整页发灰）。
 * 改用 background-blend-mode: multiply 把浅蓝方块场压成深夜蓝环境，
 * 纹理结构保留、亮度自然落到深色；蒙版换成深色收缩中心 + 顶部蓝辉光 +
 * 右下角青绿辉光，卡片保持玻璃态。
 */
[data-theme="dark"] .login {
  background: #0b0d13;
}
[data-theme="dark"] .login__photo {
  background-color: #1d2f5e;
  background-blend-mode: multiply;
  opacity: 0.9;
}
[data-theme="dark"] .login__scrim {
  background:
    radial-gradient(52% 46% at 50% 47%, rgba(11, 13, 19, 0.95) 0%, rgba(11, 13, 19, 0.74) 54%, rgba(11, 13, 19, 0) 100%),
    radial-gradient(64% 40% at 50% -6%, rgba(92, 124, 250, 0.26), rgba(92, 124, 250, 0) 72%),
    radial-gradient(46% 34% at 90% 98%, rgba(32, 201, 151, 0.18), rgba(32, 201, 151, 0) 70%),
    linear-gradient(180deg, rgba(11, 13, 19, 0.3), rgba(11, 13, 19, 0.68));
}
[data-theme="dark"] .login__graph {
  opacity: 0.52;
}
[data-theme="dark"] .card {
  background: rgba(23, 25, 31, 0.82);
  border-color: rgba(255, 255, 255, 0.08);
  box-shadow:
    0 1px 2px rgba(0, 0, 0, 0.5),
    0 18px 36px -18px rgba(0, 0, 0, 0.75),
    0 42px 84px -30px rgba(76, 110, 245, 0.45);
}
[data-theme="dark"] .card::before {
  opacity: 0.85;
}
[data-theme="dark"] .toggle {
  background: rgba(26, 27, 30, 0.78);
  border-color: var(--neutral-200);
}
[data-theme="dark"] .toggle:hover {
  background: var(--neutral-100);
}
[data-theme="dark"] .brand__mark {
  background: var(--neutral-50);
}
/* 输入框在深色下靠更亮的描边和更深的底撑起层次 */
[data-theme="dark"] .field__box {
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.3);
}
[data-theme="dark"] .field__box:hover {
  border-color: var(--neutral-400);
}
[data-theme="dark"] .field__box:focus-within {
  box-shadow: 0 0 0 3.5px rgba(92, 124, 250, 0.22);
}
[data-theme="dark"] .form__btn {
  background: linear-gradient(180deg, var(--semantic-500), var(--semantic-700));
}

@media (max-width: 480px) {
  .card {
    padding: var(--space-6) var(--space-5) var(--space-5);
  }
  .toggle {
    top: var(--space-4);
    right: var(--space-4);
  }
  .login__graph {
    opacity: 0.3;
  }
}

@media (prefers-reduced-motion: reduce) {
  .card { animation: none; }
  .graph__near,
  .graph__far,
  .graph__flow { animation: none; }
  .toggle:hover,
  .form__btn:hover:not(:disabled) { transform: none; }
}
</style>
