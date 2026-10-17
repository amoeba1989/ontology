<template>
  <!-- 灯效与坐标基准 -->
  <TresAmbientLight :intensity="0.72" />
  <TresHemisphereLight :args="[sceneEnv.hemiSky, sceneEnv.hemiGround, 0.85]" />
  <TresDirectionalLight :position="[24, 34, 18]" :intensity="1.15" />
  <TresDirectionalLight :position="[-20, 14, -18]" :intensity="0.35" color="#8fb3e8" />
  <TresFog :args="[sceneEnv.fog, 90, 260]" />

  <!-- 数字孪生基面：按场景各裁一张极坐标底盘 + 场景铭牌；
       一张跨场景的大方格会把两个星系的节点读成同一条带，网格也就不再承载"哪个场景" -->
  <template v-for="galaxy in layout.galaxies" :key="'floor-' + galaxy.key">
    <TresGroup :position="galaxy.center">
      <TresPolarGridHelper
        :args="[galaxy.span, 8, 3, 64, sceneEnv.grid1, sceneEnv.grid2]"
        :position="[0, -10.5, 0]"
      />
      <TresMesh :position="[0, -10.55, 0]" :rotation-x="-Math.PI / 2">
        <TresCircleGeometry :args="[galaxy.span * 0.98, 64]" />
        <TresMeshBasicMaterial :map="floorTexture" :color="sceneEnv.floor" />
      </TresMesh>
      <Html :position="[0, -10.4, galaxy.span * 0.82]" center :distance-factor="42" :z-index-range="[22, 10]">
        <div class="os-nameplate">
          <b>{{ galaxy.label }}</b>
          <span>{{ galaxy.nodes.length }} 类 · {{ galaxy.edges.length }} 关系</span>
        </div>
      </Html>
    </TresGroup>
  </template>

  <template v-for="galaxy in layout.galaxies" :key="galaxy.key">
    <!-- 自转写在实例上（见 setGalaxyGroup），不能走响应式：每帧改 ref 会让 Vue 递归重排 -->
    <TresGroup :position="galaxy.center" :ref="el => setGalaxyGroup(galaxy.key, el)">
      <!-- 轨道环：按 tier 分层 -->
      <TresMesh
        v-for="ring in galaxy.rings"
        :key="'ring-' + galaxy.key + ring.tier"
        :position="[0, ring.y, 0]"
        :rotation-x="Math.PI / 2"
      >
        <TresTorusGeometry :args="[ring.radius, 0.05, 8, 120]" />
        <TresMeshBasicMaterial :color="sceneEnv.ring" transparent :opacity="0.55" />
      </TresMesh>

      <!-- 本体关系细管：线型只承载 rel_type（粗细 / 双股） -->
      <template v-for="edge in galaxy.edges" :key="edge.id">
        <TresMesh v-for="(tube, ti) in edge.tubes" :key="edge.id + '-tube-' + ti">
          <TresTubeGeometry :args="tube.args" />
          <TresMeshStandardMaterial
            :color="edgeColor(edge)"
            :roughness="0.55"
            :metalness="0.05"
            :transparent="true"
            :opacity="edgeOpacity(edge)"
            :emissive="edgeColor(edge)"
            :emissive-intensity="edgeActive(edge) ? 0.45 : 0.08"
          />
        </TresMesh>
      </template>

      <!-- 方向箭头常驻：关系有向是语义，不是选中态才成立的事实 -->
      <TresMesh
        v-for="edge in galaxy.edges"
        :key="'arw-' + edge.id"
        :position="arrowOf(edge.id).pos"
        :quaternion="arrowOf(edge.id).quat"
      >
        <TresConeGeometry :args="[0.2, 0.6, 12]" />
        <TresMeshBasicMaterial :color="edgeColor(edge)" transparent :opacity="edgeActive(edge) ? 1 : 0.62" />
      </TresMesh>

      <!-- 关系名标签：仅悬停/选中相关边 -->
      <Html
        v-for="edge in galaxy.edges.filter(edgeActive)"
        :key="'el-' + edge.id"
        :position="edge.mid"
        center
        :distance-factor="30"
        :z-index-range="[26, 12]"
      >
        <div class="os-edge-tag">
          <b>{{ edge.nameCn || edge.label }}</b>
          <span>{{ edge.cardinality }}</span>
          <i>{{ edge.label }}</i>
        </div>
      </Html>

      <!-- 本体节点 -->
      <template v-for="node in galaxy.nodes" :key="node.id">
        <TresSprite
          :position="node.pos"
          :scale="[node.radius * 5.4, node.radius * 5.4, 1]"
          :render-order="2"
        >
          <TresSpriteMaterial
            :map="haloTexture()"
            :color="node.color"
            :transparent="true"
            :opacity="haloOpacity(node)"
            :depth-write="false"
          />
        </TresSprite>

        <!-- 类=球：尺寸=实例规模，色相=发布状态，线框=空壳 -->
        <TresMesh
          :position="node.pos"
          :scale="nodeScale(node)"
          @pointer-over="on('h' + node.id, () => hover(node.id))"
          @pointer-out="on('hOut', () => hover(null))"
          @click.stop="on('p' + node.id, () => pick(node.id))"
        >
          <TresSphereGeometry :args="[node.radius, 32, 20]" />
          <TresMeshStandardMaterial
            :color="node.color"
            :wireframe="node.hollow"
            :roughness="0.36"
            :metalness="0.16"
            :emissive="node.color"
            :emissive-intensity="node.hollow ? 0.06 : 0.18"
            :transparent="true"
            :opacity="nodeOpacity(node)"
          />
        </TresMesh>

        <Html v-if="showLabel(node)" :position="labelPos(node)" center :distance-factor="34" :z-index-range="[30, 14]">
          <div class="os-node-label" :class="{ 'is-active': isActive(node), 'is-dim': isDim(node) }">
            <span class="os-node-label__cn">{{ node.name_cn }}</span>
            <template v-if="isActive(node)">
              <span class="os-node-label__en">{{ node.name }}</span>
              <span class="os-node-label__meta">{{ metaText(node) }}</span>
            </template>
          </div>
        </Html>

        <!-- 属性卫星环：只解释当前这一个类，常驻会把星系糊成标签墙 -->
        <TresGroup v-if="selectedNode && selectedNode.id === node.id" :ref="setSatGroup">
          <template v-for="(attr, ai) in satelliteAttrs" :key="'sat-' + attr.id">
            <TresMesh :position="satPos(ai, satelliteAttrs.length)">
              <TresSphereGeometry :args="[0.3, 16, 12]" />
              <TresMeshStandardMaterial
                :color="attr.required ? '#f08c00' : '#7aa5d8'"
                :emissive="attr.required ? '#f08c00' : '#7aa5d8'"
                :emissive-intensity="0.3"
                :roughness="0.4"
              />
            </TresMesh>
            <Html :position="satPos(ai, satelliteAttrs.length)" center :distance-factor="22" :z-index-range="[34, 20]">
              <div class="os-attr" :class="{ 'is-required': attr.required }">
                {{ attr.name }}<i>{{ attr.type }}</i>
              </div>
            </Html>
          </template>
        </TresGroup>

        <!-- 规则=菱形（常驻挂在球顶），约束=三角（仅在该类绑定的资产真挂了质量规则时出现） -->
        <TresMesh
          v-for="badge in node.ruleBadges"
          :key="'rb-' + badge.id"
          :position="badge.pos"
          @pointer-over="on('b' + badge.id, () => hoverBadge(badge.id))"
          @pointer-out="on('bOut', () => hoverBadge(null))"
          @click.stop="on('p' + node.id, () => pick(node.id))"
        >
          <TresOctahedronGeometry :args="[0.44, 0]" />
          <TresMeshStandardMaterial
            :color="badge.color"
            :roughness="0.4"
            :metalness="0.1"
            :emissive="badge.color"
            :emissive-intensity="hoveredBadgeId === badge.id ? 0.75 : 0.3"
            :transparent="true"
            :opacity="badgeOpacity(node)"
          />
        </TresMesh>
        <TresMesh
          v-if="node.constraintBadge"
          :key="'cb-' + node.id"
          :position="node.constraintBadge.pos"
          @pointer-over="on('c' + constraintKey(node), () => hoverBadge(constraintKey(node)))"
          @pointer-out="on('bOut', () => hoverBadge(null))"
          @click.stop="on('p' + node.id, () => pick(node.id))"
        >
          <TresTetrahedronGeometry :args="[0.52, 0]" />
          <TresMeshStandardMaterial
            :color="node.constraintBadge.color"
            :roughness="0.4"
            :metalness="0.1"
            :emissive="node.constraintBadge.color"
            :emissive-intensity="hoveredBadgeId === constraintKey(node) ? 0.75 : 0.3"
            :transparent="true"
            :opacity="badgeOpacity(node)"
          />
        </TresMesh>

        <Html
          v-for="tip in badgeTips(node)"
          :key="'tip-' + tip.id"
          :position="tip.pos"
          center
          :distance-factor="24"
          :z-index-range="[38, 24]"
        >
          <div class="os-rule-chip" :style="{ borderLeftColor: tip.accent }">
            <b>{{ tip.title }}</b>
            <span v-for="(line, li) in tip.lines" :key="li">{{ line }}</span>
          </div>
        </Html>
      </template>

      <!-- 推演连线：槽位常驻，管体按需重建、按进度 setDrawRange，回放不让画布重渲染 -->
      <TresMesh
        v-for="slot in LINK_SLOTS"
        :key="'link-' + slot"
        :visible="false"
        :render-order="4"
        :ref="el => setLinkSlot(galaxy.key, slot - 1, el)"
      >
        <TresMeshBasicMaterial :transparent="true" :opacity="0" :depth-write="false" />
      </TresMesh>
    </TresGroup>
  </template>

  <OrbitControls
    ref="controlsRef"
    :make-default="true"
    :enable-damping="true"
    :damping-factor="0.09"
    :min-distance="12"
    :max-distance="150"
    :max-polar-angle="1.42"
  />
</template>

<script setup lang="ts">
import { computed, ref, shallowRef, watch } from 'vue'
import * as THREE from 'three'
import { Html, OrbitControls } from '@tresjs/cientos'
import { useLoop, useTres } from '@tresjs/core'
import { useThemeStore } from '../../../../store/theme'
import type { SceneEvent } from '../../../../api/ontologyScene'
import {
  EVENT_LEVEL_COLOR,
  haloTexture,
  shadowTexture,
  toWorld,
  TIER_LABEL,
  type ConstraintBadge,
  type LayoutEdge,
  type LayoutNode,
  type SceneLayout,
} from './layout'

const props = defineProps<{
  layout: SceneLayout
  selectedId: string | null
  hoveredId: string | null
  spinning: boolean
}>()

const emit = defineEmits<{
  (e: 'select', id: string | null): void
  (e: 'hover', id: string | null): void
}>()

const SPIN_SPEED = 0.052 // ≈ 0.05°/帧（60fps）

/**
 * 三维环境色随主题翻转：基面/网格/雾/半球光在明快模式下是浅蓝天空系，
 * 暗黑模式下压成深空灰，避免黑色外壳里漂浮一片亮蓝底盘。
 */
const theme = useThemeStore()
const sceneEnv = computed(() => theme.isDark
  ? { fog: '#141519', hemiSky: '#41495a', hemiGround: '#141519', grid1: '#333c4b', grid2: '#22262e', floor: '#1c1f26', ring: '#3d4757', edgeIdle: '#4b5566' }
  : { fog: '#e9f1fb', hemiSky: '#ffffff', hemiGround: '#cfdcec', grid1: '#b9cfe9', grid2: '#dfeaf8', floor: '#f2f7fd', ring: '#a9c4e6', edgeIdle: '#8aa7cf' })

/**
 * 星系自转与卫星环角度直接写在 three 实例上，不进响应式：
 * 逐帧改 ref 会让 Vue 在同一个 flush 里反复重排 SceneRoot，报 recursive updates 并整场景重渲染。
 */
let orbitAngle = 0
const galaxyGroups: Record<string, THREE.Object3D | null> = {}
let satGroup: THREE.Object3D | null = null
function setGalaxyGroup(key: string, el: unknown) {
  galaxyGroups[key] = (el as THREE.Object3D | null) ?? null
}
function setSatGroup(el: unknown) {
  satGroup = (el as THREE.Object3D | null) ?? null
}

const hoveredBadgeId = ref<string | null>(null)
const controlsRef = shallowRef<any>(null)
const floorTexture = shadowTexture()
const { camera, controls, sizes } = useTres()

/** 相机接管与交还直接写在控制器实例上：绑成 prop 会让每次选中都重排整棵 Tres 子树 */
function setControlsEnabled(on: boolean) {
  const ctl = controls.value ?? controlsRef.value?.instance ?? controlsRef.value
  if (ctl) ctl.enabled = on
}

const selectedNode = computed<LayoutNode | null>(
  () => (props.selectedId ? props.layout.nodeMap[props.selectedId]?.node ?? null : null),
)
const satelliteAttrs = computed(() => selectedNode.value?.attributes.slice(0, 8) ?? [])

/* ── 边高亮 ─────────────────────────────────────────── */
function touches(edge: LayoutEdge, id: string | null) {
  return !!id && (edge.from === id || edge.to === id)
}
function edgeActive(edge: LayoutEdge) {
  return touches(edge, props.selectedId) || touches(edge, props.hoveredId)
}
function edgeColor(edge: LayoutEdge) {
  if (touches(edge, props.selectedId)) return '#3b5bdb'
  if (touches(edge, props.hoveredId)) return '#4c6ef5'
  return sceneEnv.value.edgeIdle
}
function edgeOpacity(edge: LayoutEdge) {
  if (edgeActive(edge)) return 0.95
  return props.selectedId || props.hoveredId ? 0.3 : 0.62
}

const arrowCache = new Map<string, { pos: [number, number, number]; quat: [number, number, number, number] }>()
function arrowOf(edgeId: string) {
  const hit = arrowCache.get(edgeId)
  if (hit) return hit
  const edge = props.layout.edgeMap[edgeId]
  const p = edge.curve.getPointAt(0.72)
  const tan = edge.curve.getTangentAt(0.72).normalize()
  const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), tan)
  const entry = {
    pos: [p.x, p.y, p.z] as [number, number, number],
    quat: [q.x, q.y, q.z, q.w] as [number, number, number, number],
  }
  arrowCache.set(edgeId, entry)
  return entry
}

/* ── 节点状态 ───────────────────────────────────────── */
function isActive(node: LayoutNode) {
  return node.id === props.selectedId || node.id === props.hoveredId
}
function isRelated(id: string) {
  const galaxy = props.layout.nodeMap[id]?.galaxy
  return !!galaxy?.edges.some(e => edgeActive(e) && (e.from === id || e.to === id))
}
function isDim(node: LayoutNode) {
  if (!props.selectedId && !props.hoveredId) return false
  return !isActive(node) && !isRelated(node.id)
}
function nodeOpacity(node: LayoutNode) {
  if (node.hollow) return isDim(node) ? 0.28 : 0.72
  return isDim(node) ? 0.34 : 1
}
function haloOpacity(node: LayoutNode) {
  const base = isActive(node) ? 0.85 : isDim(node) ? 0.12 : 0.42
  return Math.min(1, base * (node.hollow ? 0.45 : 1))
}
function nodeScale(node: LayoutNode) {
  return node.id === props.selectedId ? 1.22 : 1
}
function labelPos(node: LayoutNode) {
  return [node.pos[0], node.pos[1] - node.radius - 1.6, node.pos[2]] as [number, number, number]
}
/** 类名限量常驻，落选的那个类一旦被 hover/选中仍然立刻出全名 */
function showLabel(node: LayoutNode) {
  return node.labelVisible || isActive(node)
}
/** 标签元信息只补形态读不出来的两个事实：规模与是否已发布 */
function metaText(node: LayoutNode) {
  const parts = [TIER_LABEL[node.tier], `实例 ${node.instance_count}`]
  if (node.hollow) parts.push('空壳')
  else if (node.status !== 'published') parts.push(node.status)
  return parts.join(' · ')
}
/** 卫星环/锁环半径跟着选中对象的实际尺寸走，大对象不会被环压在壳里 */
function orbitR(gap: number) {
  return (selectedNode.value?.radius ?? 1.5) + gap
}
function satPos(index: number, total: number): [number, number, number] {
  const a = (index / Math.max(1, total)) * Math.PI * 2
  const r = orbitR(2.9)
  return [Math.cos(a) * r, 2.6 + Math.sin(a * 2) * 0.35, Math.sin(a) * r]
}

/* ── 规则/约束角标 ───────────────────────────────────── */
function hoverBadge(id: string | null) {
  hoveredBadgeId.value = id
}
function constraintKey(node: LayoutNode) {
  return 'constraint:' + node.id
}
function badgeOpacity(node: LayoutNode) {
  return isDim(node) ? 0.32 : 1
}
function byStatusText(cb: ConstraintBadge) {
  const order: [string, string][] = [['failure', '失败'], ['warning', '警告'], ['healthy', '通过'], ['unknown', '未验证']]
  const parts = order
    .map(([k, cn]) => [cb.byStatus[k] ?? 0, cn] as [number, string])
    .filter(([n]) => n > 0)
    .map(([n, cn]) => `${cn} ${n}`)
  return parts.length ? `规则明细：${parts.join(' / ')}` : '规则明细：暂无评估记录'
}
interface BadgeTip {
  id: string
  pos: [number, number, number]
  /** 说明条左边框取角标本色，读者不用来回对照图例 */
  accent: string
  title: string
  lines: string[]
}
/** 角标常驻但文字克制：选中该类时展开全部，未选中时只在直接 hover 那一枚时出说明 */
function badgeTips(node: LayoutNode): BadgeTip[] {
  const expanded = selectedNode.value?.id === node.id
  const tips: BadgeTip[] = []
  const ruleById = new Map(node.rules.map(r => [r.id, r]))
  for (const b of node.ruleBadges) {
    if (!expanded && hoveredBadgeId.value !== b.id) continue
    const r = ruleById.get(b.id)
    const lines = [r?.condition_expr, r?.action_desc, r ? `状态 ${r.status} · 触发 ${r.trigger_count} 次` : '']
      .filter(Boolean) as string[]
    tips.push({
      id: 'r-' + b.id,
      accent: b.color,
      title: `规则 · ${b.name}`,
      lines,
      pos: [b.pos[0], b.pos[1] + 1.15, b.pos[2]],
    })
  }
  const cb = node.constraintBadge
  if (cb && (expanded || hoveredBadgeId.value === constraintKey(node))) {
    tips.push({
      id: constraintKey(node),
      accent: cb.color,
      title: `约束验证 · ${cb.label}`,
      lines: [`${cb.ruleCount} 条质量规则`, byStatusText(cb), '未评估 ≠ 已通过'],
      pos: [cb.pos[0], cb.pos[1] + 1.15, cb.pos[2]],
    })
  }
  return tips
}

function pick(id: string | null) {
  emit('select', id === props.selectedId ? null : id)
}
function hover(id: string | null) {
  emit('hover', id)
}

/**
 * Tres 对象上的事件处理器必须引用稳定。
 * 模板里写 `@pointer-over="hover(node.id)"` 每次渲染都换新函数，Tres 便重绑事件；
 * 重绑那一刻它会对当前命中的对象补发一轮 over/out，hover 回写父组件又触发整棵子树重渲染，
 * 一次点击能刷出上千次 emit，直接把 Vue 的 recursive updates 上限打爆（表现为一屏告警 + 掉帧）。
 */
const handlerMemo = new Map<string, () => void>()
function on(key: string, run: () => void) {
  let fn = handlerMemo.get(key)
  if (!fn) {
    fn = run
    handlerMemo.set(key, fn)
  }
  return fn
}

/* ── 相机聚焦补间（手动 lerp，不引第三方 tween） ───────── */
const goal = { active: false, target: new THREE.Vector3(), camPos: new THREE.Vector3() }

/**
 * 总览机位由布局算出，不写死坐标：星系数量、层级半径都会变。
 * 定距取"视平面包住的宽高"而不是包围球，让整张关系图（含底盘与铭牌）刚好占满画面。
 */
function overviewPose(): { pos: THREE.Vector3; target: THREE.Vector3 } {
  const gs = props.layout.galaxies
  const target = new THREE.Vector3()
  if (!gs.length) return { pos: new THREE.Vector3(0, 30, 58), target }
  const centers = gs.map(g => new THREE.Vector3(...g.center))
  centers.forEach(c => target.add(c))
  target.multiplyScalar(1 / centers.length)
  // 张角按画布真实宽高比算：竖长条（aspect<1）时横向比纵向紧，
  // 宽而扁的关系图必须按横向定距，否则左右两个星系各被切掉一块
  const cam = camera.value as THREE.PerspectiveCamera | null | undefined
  const w = sizes?.width?.value ?? 0
  const h = sizes?.height?.value ?? 0
  const aspect = w > 0 && h > 0 ? w / h : cam?.aspect ?? 1.7
  const vFov = THREE.MathUtils.degToRad(cam?.fov ?? 45)
  const hFov = 2 * Math.atan(Math.tan(vFov / 2) * aspect)

  // 机位俯角固定，所以视平面两轴能解析求出：水平=世界 X，竖直=(0, cosθ, -sinθ)。
  // 拿包围球定距会把"前后深度"也算进半径，对扁平图白留一圈空隙。
  const TILT_Y = 0.46
  const tiltLen = Math.hypot(1, TILT_Y)
  const sinT = TILT_Y / tiltLen
  const cosT = 1 / tiltLen
  // span = 最外环 + 该环上最大的类壳 + 底盘余量，且星系组会绕 Y 自转，
  // 所以它在水平方向就是绕自家中心扫出的圆；球外的类名标签与铭牌再留 2
  let extX = 10
  let extY = 10
  gs.forEach((g, i) => {
    const r = g.span + 2
    extX = Math.max(extX, Math.abs(centers[i].x - target.x) + r)
    // 竖直方向画到最低的东西是 -10.5 的极坐标底盘
    extY = Math.max(extY, Math.abs(centers[i].y - target.y) + 10.5 * cosT + r * sinT)
  })
  const dist = Math.min(150, Math.max(24,
    Math.max(extX / Math.tan(hFov / 2), extY / Math.tan(vFov / 2)) * 1.03))
  const dir = new THREE.Vector3(0, TILT_Y, 1).normalize().multiplyScalar(dist)
  return { pos: target.clone().add(dir), target }
}

/** 首屏与复位都用它：直接落位，不做自动运镜（镜头归用户） */
function applyOverview() {
  const cam = camera.value
  const ctl = controls.value ?? controlsRef.value?.instance ?? controlsRef.value
  if (!cam || !ctl?.target) return false
  const { pos, target } = overviewPose()
  cam.position.copy(pos)
  ctl.target.copy(target)
  ctl.update?.()
  goal.active = false
  setControlsEnabled(true)
  return true
}

function flyTo(id: string | null) {
  const cam = camera.value
  if (!cam) return
  if (!id) {
    const { pos, target } = overviewPose()
    goal.target.copy(target)
    goal.camPos.copy(pos)
    goal.active = true
    setControlsEnabled(false)
    return
  }
  const entry = props.layout.nodeMap[id]
  if (!entry) return
  const [wx, wy, wz] = toWorld(entry.node.pos, entry.galaxy.center, orbitAngle)
  const dist = (entry.node.tier === 1 ? 21 : 15) + entry.node.radius * 2
  const ctl = controls.value ?? controlsRef.value?.instance ?? controlsRef.value
  const pivot = ctl?.target ?? new THREE.Vector3(0, 0, 0)
  const dir = cam.position.clone().sub(pivot).normalize()
  goal.target.set(wx, wy, wz)
  goal.camPos.set(wx + dir.x * dist, wy + dir.y * dist * 0.7 + 3.5, wz + dir.z * dist)
  goal.active = true
  setControlsEnabled(false)
}

watch(() => props.selectedId, id => flyTo(id))
// 换场景后星系数量与跨度都变了，机位跟着重算；已选中某个类时保持用户当前视角不动
watch(() => props.layout, () => { if (!props.selectedId) applyOverview() })

/* ── 推演连线 ───────────────────────────────────────── */
interface LinkPulse {
  id: number
  galaxyKey: string
  curve: THREE.QuadraticBezierCurve3
  /** 秒：画出 / 停留 / 淡出三段，画完后整条线留在图上，再整体淡掉 */
  age: number
  draw: number
  hold: number
  fade: number
  /** 当前管体的索引总数，setDrawRange 用它按进度截取 */
  total: number
  color: string
}
/**
 * 连线走固定槽位池：槽位常驻在模板里，管体在换事件时重建，进度逐帧写 geometry.setDrawRange。
 * 事件回放不该让画布重渲染——Tres 子树每次 patch 都会把整棵场景重新排进 Vue 的 flush 队列，
 * 直接撑爆 recursive updates 上限（开发态刷一屏告警，实际是丢帧）。
 */
const links: LinkPulse[] = []
const LINK_SLOTS = 6
const linkSlots = new Map<string, (THREE.Mesh | null)[]>()
let lid = 0

function setLinkSlot(galaxyKey: string, slot: number, el: unknown) {
  const arr = linkSlots.get(galaxyKey) ?? new Array<THREE.Mesh | null>(LINK_SLOTS).fill(null)
  arr[slot] = (el as THREE.Mesh | null) ?? null
  linkSlots.set(galaxyKey, arr)
}

function spawn(ev: SceneEvent | null) {
  if (!ev) return
  const entry = props.layout.nodeMap[ev.entity_id]
  if (!entry) return
  const to = new THREE.Vector3(...entry.node.pos)
  const edge = ev.relation_id ? entry.galaxy.edges.find(e => e.id === ev.relation_id) : undefined
  let curve: THREE.QuadraticBezierCurve3
  if (edge) {
    // 事件目标若是关系起点，则沿同一曲线反向画出
    curve = edge.to === ev.entity_id
      ? edge.curve
      : new THREE.QuadraticBezierCurve3(
        edge.curve.v2.clone(), edge.curve.v1.clone(), edge.curve.v0.clone(),
      )
  } else {
    // 没有关系可走的事件只画一截外侧短引线：它是"外部数据落到这个类"，不冒充一条本体关系
    const ang = Math.random() * Math.PI * 2
    const from = to.clone().add(new THREE.Vector3(
      Math.cos(ang) * (entry.node.radius + 9), 5 + Math.random() * 2.5, Math.sin(ang) * (entry.node.radius + 9),
    ))
    curve = new THREE.QuadraticBezierCurve3(from, from.clone().lerp(to, 0.5).setY(to.y + 2.4), to)
  }
  links.push({
    id: ++lid,
    galaxyKey: entry.galaxy.key,
    curve,
    age: 0,
    draw: 1.1,
    hold: 0.45,
    fade: 0.75,
    total: 0,
    color: EVENT_LEVEL_COLOR[ev.level] || EVENT_LEVEL_COLOR.info,
  })
  while (links.length > LINK_SLOTS * 2) links.shift()
}

/** 时间轴每步命令式投递，不作为 prop 下传 */
defineExpose({ spawn })

function linkStep(dt: number) {
  if (!links.length && !linkSlots.size) return
  const byGalaxy: Record<string, LinkPulse[]> = {}
  for (let i = links.length - 1; i >= 0; i--) {
    const l = links[i]
    l.age += dt
    if (l.age >= l.draw + l.hold + l.fade) {
      links.splice(i, 1)
      continue
    }
    ;(byGalaxy[l.galaxyKey] ??= []).push(l)
  }
  linkSlots.forEach((els, key) => {
    const list = byGalaxy[key] ?? []
    for (let slot = 0; slot < els.length; slot++) {
      const mesh = els[slot]
      const l = list[slot]
      if (!mesh) continue
      if (!l) {
        mesh.visible = false
        continue
      }
      mesh.visible = true
      if (mesh.userData.lid !== l.id) {
        mesh.userData.lid = l.id
        mesh.geometry.dispose()
        mesh.geometry = new THREE.TubeGeometry(l.curve, 40, 0.19, 8, false)
        l.total = mesh.geometry.index ? mesh.geometry.index.count : 0
        ;(mesh.material as THREE.MeshBasicMaterial).color.set(l.color)
      }
      const p = Math.min(1, l.age / l.draw)
      mesh.geometry.setDrawRange(0, Math.max(3, Math.floor(l.total * p)))
      const rest = l.age - l.draw - l.hold
      ;(mesh.material as THREE.MeshBasicMaterial).opacity = rest > 0 ? 0.95 * (1 - rest / l.fade) : 0.95
    }
  })
}

/* ── 主循环 ─────────────────────────────────────────── */
const { onBeforeRender } = useLoop()
let last = performance.now()
let fitted = false

onBeforeRender(() => {
  const now = performance.now()
  const dt = Math.min(0.05, (now - last) / 1000)
  last = now

  if (props.spinning && !props.selectedId) {
    orbitAngle += SPIN_SPEED * dt
    Object.values(galaxyGroups).forEach(g => {
      if (g) g.rotation.y = orbitAngle
    })
  }
  if (satGroup) satGroup.rotation.y += 0.5 * dt

  if (goal.active) {
    const cam = camera.value
    const ctl = controls.value ?? controlsRef.value?.instance ?? controlsRef.value
    if (cam && ctl?.target) {
      const k = 1 - Math.exp(-dt * 5)
      cam.position.lerp(goal.camPos, k)
      ctl.target.lerp(goal.target, k)
      ctl.update?.()
      if (cam.position.distanceToSquared(goal.camPos) < 0.05) {
        goal.active = false
        setControlsEnabled(true)
      }
    } else {
      goal.active = false
      setControlsEnabled(true)
    }
  }

  linkStep(dt)

  // 相机与控制器由 TresCanvas 自己的挂载流程建立，SceneRoot 的 onMounted 跑在它前面，
  // 那时 camera.value 还是 null（旧代码在这里 set 位置其实是空操作），所以定距放到第一帧渲染后
  if (!fitted) fitted = applyOverview()
})
</script>

<style scoped>
.os-nameplate {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
  padding: 4px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(148, 178, 222, 0.45);
  font-family: var(--font-sans);
  white-space: nowrap;
  pointer-events: none;
}
.os-nameplate b { font-size: 12px; color: #33517d; letter-spacing: 0.08em; }
.os-nameplate span { font-size: 9.5px; color: #8aa3c8; }

.os-node-label {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
  padding: 5px 10px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.86);
  border: 1px solid rgba(148, 178, 222, 0.55);
  box-shadow: 0 6px 16px rgba(46, 87, 148, 0.12);
  backdrop-filter: blur(6px);
  font-family: var(--font-sans);
  white-space: nowrap;
  pointer-events: none;
  transition: opacity 0.2s, transform 0.2s;
}
.os-node-label.is-active {
  border-color: #4c6ef5;
  box-shadow: 0 8px 20px rgba(76, 110, 245, 0.22);
}
.os-node-label.is-dim { opacity: 0.45; }
.os-node-label__cn { font-size: 13px; font-weight: 700; color: #1e3a6b; letter-spacing: 0.02em; }
.os-node-label__en { font-size: 9.5px; color: #6b87b0; letter-spacing: 0.06em; }
.os-node-label__meta { font-size: 9px; color: #8aa3c8; }

.os-edge-tag {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 8px;
  border-radius: 999px;
  background: rgba(59, 91, 219, 0.92);
  color: #fff;
  font-family: var(--font-sans);
  font-size: 10.5px;
  white-space: nowrap;
  pointer-events: none;
  box-shadow: 0 4px 12px rgba(46, 87, 148, 0.24);
}
.os-edge-tag span { opacity: 0.78; font-size: 9.5px; }.os-edge-tag i {
  font-style: normal;
  opacity: 0.6;
  font-size: 9px;
  font-family: var(--font-mono, monospace);
}

.os-attr {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 2px 7px;
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(122, 165, 216, 0.6);
  color: #3c5f8f;
  font-family: var(--font-sans);
  font-size: 10px;
  white-space: nowrap;
  pointer-events: none;
}
.os-attr.is-required { border-color: #f08c00; color: #b3560b; font-weight: 600; }
.os-attr i { font-style: normal; color: #93aecf; font-size: 9px; }

.os-rule-chip {
  display: flex;
  flex-direction: column;
  gap: 1px;
  max-width: 190px;
  padding: 5px 9px;
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.92);
  border-left: 3px solid #4c6ef5;
  box-shadow: 0 6px 16px rgba(46, 87, 148, 0.14);
  font-family: var(--font-sans);
  white-space: normal;
  pointer-events: none;
}
.os-rule-chip b { font-size: 11px; color: #1e3a6b; }
.os-rule-chip span {
  font-size: 9.5px;
  color: #6b87b0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── 深色态覆盖：画布上的 HTML 浮层卡（铭牌/类名/属性/规则提示）由白底翻为玻璃化深底 ── */
html[data-theme="dark"] .os-nameplate { background: rgba(33, 34, 38, 0.72); border-color: rgba(255, 255, 255, 0.1); }
html[data-theme="dark"] .os-nameplate b { color: #c1c2c5; }
html[data-theme="dark"] .os-nameplate span { color: #868e96; }
html[data-theme="dark"] .os-node-label { background: rgba(33, 34, 38, 0.86); border-color: rgba(255, 255, 255, 0.12); box-shadow: 0 6px 16px rgba(0, 0, 0, 0.45); }
html[data-theme="dark"] .os-node-label.is-active { border-color: #5c7cfa; box-shadow: 0 8px 20px rgba(0, 0, 0, 0.5); }
html[data-theme="dark"] .os-node-label__cn { color: #f1f2f4; }
html[data-theme="dark"] .os-node-label__en { color: #9a9ba1; }
html[data-theme="dark"] .os-node-label__meta { color: #868e96; }
html[data-theme="dark"] .os-attr { background: rgba(33, 34, 38, 0.9); border-color: rgba(255, 255, 255, 0.14); color: #c1c2c5; }
html[data-theme="dark"] .os-attr.is-required { border-color: #f08c00; color: #ffd43b; }
html[data-theme="dark"] .os-attr i { color: #868e96; }
html[data-theme="dark"] .os-rule-chip { background: rgba(33, 34, 38, 0.92); border-left-color: #5c7cfa; box-shadow: 0 6px 16px rgba(0, 0, 0, 0.45); }
html[data-theme="dark"] .os-rule-chip b { color: #f1f2f4; }
html[data-theme="dark"] .os-rule-chip span { color: #9a9ba1; }
</style>
