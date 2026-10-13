import * as THREE from 'three'
import type { OntologyScene, SceneEdge, SceneNode } from '../../../../api/ontologyScene'

export const TIER_LABEL: Record<number, string> = { 1: '核心对象', 2: '关联对象', 3: '事件对象' }
export const DOMAIN_LABEL: Record<string, string> = { military: '军事场景' }
/** 色相只承载发布状态，不再与层级重复编码 */
export const STATUS_COLOR: Record<string, string> = { published: '#3b5bdb', draft: '#8fa0b8' }
/** 推演连线的着色通道 = 事件等级（图例与画布共用一份，避免两处各写一套色值） */
export const EVENT_LEVEL_COLOR: Record<string, string> = {
  warning: '#e8590c', ok: '#12b886', info: '#4c6ef5',
}
export const EVENT_LEVEL_LABEL: Record<string, string> = {
  warning: '告警', ok: '正常', info: '信息',
}
/** 尺寸只承载实例规模 */
const SIZE_MIN = 0.9
const SIZE_MAX = 2.4

/** 规则优先级色（菱形徽章的着色通道） */
export const PRIORITY_COLOR: Record<string, string> = {
  high: '#e8590c', medium: '#4c6ef5', low: '#adb5bd',
}
const PRIORITY_RANK: Record<string, number> = { high: 0, medium: 1, low: 2 }

/**
 * 约束验证四态。`unknown` = 定义了质量规则但从未跑过评估，
 * 不能与 `healthy` 混同：约束存在不等于数据已满足约束。
 */
export type ConstraintStatus = 'healthy' | 'warning' | 'failure' | 'unknown'
export const CONSTRAINT_COLOR: Record<ConstraintStatus, string> = {
  healthy: '#20c997', warning: '#f08c00', failure: '#e03131', unknown: '#8fa0b8',
}
export const CONSTRAINT_LABEL: Record<ConstraintStatus, string> = {
  healthy: '验证通过', warning: '警告', failure: '验证失败', unknown: '已定义·未验证',
}

/** 关系线型只承载 rel_type：many_to_many 双股，其余单股按语义粗细 */
const TUBE_RADIUS: Record<string, number> = {
  has_many: 0.1, has_one: 0.09, belongs_to: 0.06, many_to_many: 0.06, subclass: 0.08,
}
const TWIN_SEP = 0.3

/**
 * 这四个行动执行器只回固定"成功"文案、不触碰任何数据（`action_executors/`）。
 * 态势舱里必须标成未实装，不能让绿色把"记了一条流水"读成"真的执行过"。
 */
export const STUB_ACTION_TYPES = new Set(['sql_exec', 'modify_attribute', 'notification', 'call_function'])

/** 徽章行悬在球顶上方——类名标签在球下方，两个通道不能抢同一个位置 */
const BADGE_LIFT = 1.05
const BADGE_GAP = 1.5
export const MAX_RULE_BADGES = 3
/** 同屏常驻类名上限 */
const LABEL_CAP = 8

const TIER_ORBIT: Record<number, number> = { 1: 7.5, 2: 13, 3: 18 }
const TIER_PHASE = { 1: 0, 2: 0.45, 3: 1.05 } as Record<number, number>
const TIER_HEIGHT = { 1: 0, 2: 1.8, 3: -1.4 } as Record<number, number>

export function domainLabel(key: string) {
  return DOMAIN_LABEL[key] || key || '未分组'
}

export interface RuleBadge {
  id: string
  name: string
  priority: string
  color: string
  /** 星系局部坐标（与 node.pos 同系，随星系组一起自转） */
  pos: [number, number, number]
}

export interface ConstraintBadge {
  status: ConstraintStatus
  color: string
  label: string
  ruleCount: number
  byStatus: Record<string, number>
  pos: [number, number, number]
}

export interface LayoutNode extends SceneNode {
  color: string
  /** 无实例或未绑定数据源：画空心线框壳 */
  hollow: boolean
  /** 由 instance_count 开方映射出的世界半径 */
  radius: number
  /** 星系局部坐标（星系组绕 Y 自转，边曲线共用同一局部系） */
  pos: [number, number, number]
  angle: number
  orbit: number
  /** 规则=菱形，常驻，最多 3 枚，按优先级取最紧要的 */
  ruleBadges: RuleBadge[]
  /** 被截断的规则条数，HUD 用来交代"共 N 条，图上只挂 3 条" */
  ruleBadgeOverflow: number
  /** 约束=三角，仅当绑定资产挂了质量规则时出现（无规则=不画，不是"通过"） */
  constraintBadge: ConstraintBadge | null
  /** 类名是否常驻；未入选的类只在 hover/选中时出名字，避免同屏十几个标签互糊 */
  labelVisible: boolean
}

export interface EdgeTube {
  curve: THREE.QuadraticBezierCurve3
  args: [THREE.QuadraticBezierCurve3, number, number, number, boolean]
}

export interface LayoutEdge {
  id: string
  from: string
  to: string
  fromName: string
  toName: string
  label: string
  nameCn: string
  relType: string
  cardinality: string
  description: string
  /** 箭头、关系标签与事件推演连线都读这条主曲线 */
  curve: THREE.QuadraticBezierCurve3
  tubes: EdgeTube[]
  mid: [number, number, number]
  dirSign: 1 | -1
}

export interface Galaxy {
  key: string
  label: string
  center: [number, number, number]
  nodes: LayoutNode[]
  edges: LayoutEdge[]
  rings: { tier: number; radius: number; y: number }[]
  /** 基面圆盘半径：最外环 + 该环上最大的类壳，网格不会裁掉节点 */
  span: number
}

export interface SceneLayout {
  galaxies: Galaxy[]
  nodeMap: Record<string, { galaxy: Galaxy; node: LayoutNode }>
  edgeMap: Record<string, LayoutEdge>
}

/**
 * 尺寸 = 实例规模。用开方压缩长尾，再按本场景的最小/最大实例数拉伸到满刻度，
 * 否则演示数据里 2~9 的差距会被压成"看起来一样大"，尺寸通道等于白占。
 */
function sizeOf(instanceCount: number, sqrtMin: number, sqrtMax: number): number {
  const v = Math.sqrt(Math.max(0, instanceCount))
  if (sqrtMax - sqrtMin < 1e-6) return (SIZE_MIN + SIZE_MAX) / 2
  const ratio = Math.min(1, Math.max(0, (v - sqrtMin) / (sqrtMax - sqrtMin)))
  return SIZE_MIN + (SIZE_MAX - SIZE_MIN) * ratio
}

/**
 * 徽章行沿环的切向铺开，而不是沿半径向外：向外会伸进相邻环带，
 * 菱形/三角就被读成邻座类的属性了。中枢（orbit 0）没有切向，退回 X 轴。
 */
function badgeRow(node: LayoutNode, count: number): [number, number, number][] {
  const t = node.orbit === 0
    ? new THREE.Vector3(1, 0, 0)
    : new THREE.Vector3(-Math.sin(node.angle), 0, Math.cos(node.angle))
  const base = new THREE.Vector3(...node.pos)
    .add(new THREE.Vector3(0, node.radius + BADGE_LIFT, 0))
  const row: [number, number, number][] = []
  for (let i = 0; i < count; i++) {
    const p = base.clone().addScaledVector(t, (i - (count - 1) / 2) * BADGE_GAP)
    row.push([p.x, p.y, p.z])
  }
  return row
}

/**
 * 规则/约束角标：图形表里菱形=规则、三角=约束。
 * 约束只在绑定资产真的挂了质量规则时出现；`constraint_status` 为空 = 无约束 = 不画。
 */
function attachBadges(node: LayoutNode) {
  const sorted = [...node.rules].sort((a, b) =>
    (PRIORITY_RANK[a.priority] ?? 9) - (PRIORITY_RANK[b.priority] ?? 9) ||
    (b.trigger_count || 0) - (a.trigger_count || 0) ||
    a.name.localeCompare(b.name))
  const shown = sorted.slice(0, MAX_RULE_BADGES)
  node.ruleBadgeOverflow = sorted.length - shown.length

  const status = node.constraint_status as ConstraintStatus | null | undefined
  const hasConstraint = !!status && status in CONSTRAINT_COLOR && (node.constraint_rule_count || 0) > 0
  const row = badgeRow(node, shown.length + (hasConstraint ? 1 : 0))
  shown.forEach((r, i) => {
    node.ruleBadges.push({
      id: r.id,
      name: r.name,
      priority: r.priority,
      color: PRIORITY_COLOR[r.priority] ?? PRIORITY_COLOR.low,
      pos: row[i],
    })
  })
  if (hasConstraint && status) {
    node.constraintBadge = {
      status,
      color: CONSTRAINT_COLOR[status],
      label: CONSTRAINT_LABEL[status],
      ruleCount: node.constraint_rule_count,
      byStatus: node.constraint_by_status ?? {},
      pos: row[row.length - 1],
    }
  }
}

/**
 * 环内排序：有已放置邻居的按邻居角度圆均值排（子对象跟着父对象走，弦少穿第三方），
 * 其余按连接度降序兜底。只改变索引顺序，角度仍均匀分布，因此不会坍缩到同一位置。
 */
function orderGroup(
  group: SceneNode[],
  placed: LayoutNode[],
  neighbors: Map<string, string[]>,
): SceneNode[] {
  const deg = (n: SceneNode) => n.relation_count || 0
  if (!placed.length) return [...group].sort((a, b) => deg(b) - deg(a))
  const keyOf = (n: SceneNode): number | null => {
    let sx = 0
    let sz = 0
    let hit = 0
    ;(neighbors.get(n.id) ?? []).forEach(id => {
      const p = placed.find(pp => pp.id === id)
      if (!p || p.orbit === 0) return
      sx += Math.cos(p.angle)
      sz += Math.sin(p.angle)
      hit += 1
    })
    return hit ? Math.atan2(sz, sx) : null
  }
  const keys = group.map(keyOf)
  const idx = group.map((_, i) => i)
  idx.sort((a, b) => {
    const ka = keys[a]
    const kb = keys[b]
    if (ka === null && kb === null) return deg(group[b]) - deg(group[a])
    if (ka === null) return 1
    if (kb === null) return -1
    return ka - kb
  })
  return idx.map(i => group[i])
}

/** 星系数量的横向排布：单星系居中，多星系左右并列 */
function galaxyCenter(index: number, total: number): [number, number, number] {
  if (total <= 1) return [0, 0, 0]
  const spacing = total <= 2 ? 23 : 100 / total
  return [(index - (total - 1) / 2) * spacing, 0, 0]
}

function tierOf(tier: number): 1 | 2 | 3 {
  return tier === 1 || tier === 2 || tier === 3 ? (tier as 1 | 2 | 3) : 3
}

/** 全场景统一的尺寸刻度（已开方），保证两个星系的大小可比 */
export interface SizeScale { min: number; max: number }

function buildGalaxy(key: string, label: string, center: [number, number, number],
                     nodes: SceneNode[], edges: SceneEdge[], scale: SizeScale): Galaxy {
  const byTier: Record<number, SceneNode[]> = { 1: [], 2: [], 3: [] }
  nodes.forEach(n => byTier[tierOf(n.tier)].push(n))

  const member = new Set(nodes.map(n => n.id))
  const neighbors = new Map<string, string[]>()
  const link = (from: string, to: string) => {
    if (!member.has(from) || !member.has(to)) return
    if (!neighbors.has(from)) neighbors.set(from, [])
    neighbors.get(from)!.push(to)
  }
  edges.forEach(e => { link(e.from_id, e.to_id); link(e.to_id, e.from_id) })

  const placed: LayoutNode[] = []
  ;([1, 2, 3] as const).forEach(tier => {
    const group = orderGroup(byTier[tier], placed, neighbors)
    group.forEach((n, i) => {
      // 只有核心层的独苗才当星系中枢，其余层必须回到自己的轨道，
      // 否则多个独苗层会同时坍缩到原点，关系曲线退化且标签叠在别的本体上
      const hub = tier === 1 && group.length === 1
      const orbit = hub ? 0 : TIER_ORBIT[tier]
      const angle = hub ? 0 : (i / group.length) * Math.PI * 2 + TIER_PHASE[tier]
      const x = Math.cos(angle) * orbit
      const z = Math.sin(angle) * orbit
      const y = hub ? 0 : TIER_HEIGHT[tier] + (i % 2 ? 0.9 : -0.9)
      const node: LayoutNode = {
        ...n,
        color: STATUS_COLOR[n.status] ?? STATUS_COLOR.draft,
        hollow: !(n.instance_count > 0) || !n.source_table,
        radius: sizeOf(n.instance_count, scale.min, scale.max),
        pos: [x, y, z],
        angle,
        orbit,
        ruleBadges: [],
        ruleBadgeOverflow: 0,
        constraintBadge: null,
        labelVisible: true,
      }
      attachBadges(node)
      placed.push(node)
    })
  })

  const local = new Set(placed.map(p => p.id))
  const idOf = (nodeId: string) => placed.find(p => p.id === nodeId)
  const layoutEdges: LayoutEdge[] = []
  edges.forEach(e => {
    if (!local.has(e.from_id) || !local.has(e.to_id)) return
    const a = idOf(e.from_id)!.pos
    const b = idOf(e.to_id)!.pos
    const av = new THREE.Vector3(...a)
    const bv = new THREE.Vector3(...b)
    const dist = av.distanceTo(bv)
    const mid = av.clone().add(bv).multiplyScalar(0.5)
    const aRadius = idOf(e.from_id)!.radius
    const bRadius = idOf(e.to_id)!.radius
    const foreignPts = placed
      .filter(p => p.id !== e.from_id && p.id !== e.to_id)
      .map(p => ({ v: new THREE.Vector3(...p.pos), r: p.radius }))
    const bump = Math.max(3, Math.min(6.5, dist * 0.28))
    const radial = new THREE.Vector3(mid.x, 0, mid.z)
    if (radial.lengthSq() < 0.01) radial.set(0, 0, 1)
    radial.normalize()
    const tangent = new THREE.Vector3(-radial.z, 0, radial.x)

    // 稠密星系里两个相邻对象的直线弦会擦过第三方对象，基数标签就被读成别的对象的关系。
    // 因此对同一条关系试多个绕行方向（外鼓/两侧切向/内鼓），选"标签离第三方最远、
    // 又贴着自身两端"的那条管线，管子本身也跟着躲开第三方节点。
    const dirs = [
      radial.clone().multiplyScalar(bump),
      radial.clone().multiplyScalar(bump * 0.35).add(tangent.clone().multiplyScalar(bump)),
      radial.clone().multiplyScalar(bump * 0.35).add(tangent.clone().multiplyScalar(-bump)),
      radial.clone().multiplyScalar(-bump * 0.6),
    ]
    // 环带拥挤时横向绕行仍贴不到第三方之外，就把关系拱得更高，让标签离开轨道平面
    const lifts = [2.2 + dist * 0.1, 5.5 + dist * 0.16, 9 + dist * 0.2, 14 + dist * 0.3]
    const bumpScales = [1, 1.9, 2.8]
    const ts = [0.5, 0.38, 0.62, 0.26, 0.74, 0.18, 0.82]
    let curve: THREE.QuadraticBezierCurve3 | null = null
    let labelPoint = mid.clone()
    // 字典序打分：先要求"标签不属于任何第三方"，达标后要求"贴着自己的两端"，
    // 都不可得的长弦则取余量最大、再最贴端点的那个（宁可拱高也不要读到别的对象上）
    const rank = (own: number, foreign: number): [number, number, number, number] => [
      foreign - own >= 2 && own >= 0.6 ? 1 : 0,
      foreign - own,
      own <= 5.5 ? 1 : 0,
      -own,
    ]
    let best: [number, number, number, number] = [-1, -Infinity, -1, Infinity]
    for (const scale of bumpScales) {
      for (const base of dirs) {
        const dir = base.clone().multiplyScalar(scale)
        for (const lift of lifts) {
          const cand = new THREE.QuadraticBezierCurve3(
            av, mid.clone().add(dir).setY(mid.y + lift), bv,
          )
          for (const t of ts) {
            const pt = cand.getPointAt(t)
            // 一律按"到壳面的净距"算，尺寸通道生效后 2.4 半径的大对象不能再被标签压住
            const own = Math.min(
              av.distanceTo(pt) - aRadius,
              bv.distanceTo(pt) - bRadius,
            )
            const foreign = foreignPts.length
              ? Math.min(...foreignPts.map(f => f.v.distanceTo(pt) - f.r))
              : 999
            const key = rank(own, foreign)
            let better = false
            for (let i = 0; i < 4; i++) {
              if (key[i] !== best[i]) { better = key[i] > best[i]; break }
            }
            if (better) { best = key; curve = cand; labelPoint = pt }
          }
        }
      }
      // 已经"隔离且贴身"就收手，避免不必要的夸张绕行
      if (best[0] === 1 && best[2] === 1) break
    }
    const finalCurve = curve ?? new THREE.QuadraticBezierCurve3(
      av, mid.clone().add(dirs[0]).setY(mid.y + lifts[0]), bv,
    )
    const tubeRadius = TUBE_RADIUS[e.rel_type] ?? 0.08
    // 双股：两端仍落在自身壳面（标签归属判定的前提不变），只把控制点沿弧线所在
    // 平面的法向左右错开，中段张开成 N:N 的两股，不会被读成两条独立关系
    const tubes: EdgeTube[] = []
    if (e.rel_type === 'many_to_many') {
      const normal = bv.clone().sub(av).cross(finalCurve.v1.clone().sub(av))
      if (normal.lengthSq() < 1e-6) normal.set(0, 0, 1)
      normal.normalize()
      for (const sign of [1, -1]) {
        const c = new THREE.QuadraticBezierCurve3(
          finalCurve.v0.clone(),
          finalCurve.v1.clone().addScaledVector(normal, sign * TWIN_SEP),
          finalCurve.v2.clone(),
        )
        tubes.push({ curve: c, args: [c, 40, tubeRadius, 8, false] })
      }
    } else {
      tubes.push({
        curve: finalCurve,
        args: [finalCurve, 40, tubeRadius, 8, false],
      })
    }
    layoutEdges.push({
      id: e.id,
      from: e.from_id,
      to: e.to_id,
      fromName: e.from_name,
      toName: e.to_name,
      label: e.label,
      nameCn: e.name_cn || '',
      relType: e.rel_type,
      cardinality: e.cardinality,
      description: e.description,
      curve: finalCurve,
      // args 引用保持稳定，避免逐帧重建 TubeGeometry
      tubes,
      mid: [labelPoint.x, labelPoint.y, labelPoint.z],
      dirSign: 1,
    })
  })

  const rings = placed
    .filter(p => p.orbit > 0)
    .map(p => ({ tier: tierOf(p.tier), radius: p.orbit, y: TIER_HEIGHT[tierOf(p.tier)] }))
  const uniqRings = Array.from(new Map(rings.map(r => [`${r.tier}-${r.radius}-${r.y}`, r])).values())
  const span = Math.max(10, ...placed.map(p => p.orbit + p.radius)) + 3.5

  return { key, label, center, nodes: placed, edges: layoutEdges, rings: uniqRings, span }
}

export function buildLayout(scene: OntologyScene, scenario: string): SceneLayout {
  const groups: { key: string; label: string }[] = scenario && scenario !== 'all'
    ? [{ key: scenario, label: domainLabel(scenario) }]
    : scene.domains.map(d => ({ key: d.key, label: domainLabel(d.key) }))

  const galaxies: Galaxy[] = []
  const counts = scene.nodes.map(n => Math.max(0, n.instance_count || 0))
  const scale: SizeScale = {
    min: Math.sqrt(counts.length ? Math.min(...counts) : 0),
    max: Math.sqrt(counts.length ? Math.max(...counts) : 1),
  }
  groups.forEach((g, i) => {
    const nodes = scene.nodes.filter(n => (n.domain || '') === g.key)
    if (!nodes.length) return
    galaxies.push(buildGalaxy(g.key, g.label, galaxyCenter(i, groups.length), nodes, scene.edges, scale))
  })

  const nodeMap: SceneLayout['nodeMap'] = {}
  const edgeMap: SceneLayout['edgeMap'] = {}
  galaxies.forEach(gal => {
    gal.nodes.forEach(n => { nodeMap[n.id] = { galaxy: gal, node: n } })
    gal.edges.forEach(e => { edgeMap[e.id] = e })
  })

  // 常驻类名限量：预算按星系均分，星系内按实例规模→连接度取前 N，
  // 落选的类只在 hover/选中时出名字（同屏十几个标签会互相糊掉）
  const budget = Math.max(2, Math.floor(LABEL_CAP / Math.max(1, galaxies.length)))
  galaxies.forEach(gal => {
    const ranked = [...gal.nodes].sort((a, b) =>
      (b.instance_count - a.instance_count) || (b.relation_count - a.relation_count))
    ranked.forEach((n, i) => { n.labelVisible = i < budget })
  })

  return { galaxies, nodeMap, edgeMap }
}

/** 星系组绕 Y 自转角度 a 后，局部坐标的世界位置（相机聚焦用，避免依赖 object 引用） */
export function toWorld(local: [number, number, number], center: [number, number, number], a: number): [number, number, number] {
  const [x, y, z] = local
  const [cx, cy, cz] = center
  const cos = Math.cos(a)
  const sin = Math.sin(a)
  return [cx + x * cos + z * sin, cy + y, cz - x * sin + z * cos]
}

let haloTex: THREE.Texture | null = null
/** 浅色主题的柔光晕：canvas 径向渐变贴图，替代 EffectComposer 辉光 */
export function haloTexture(): THREE.Texture {
  if (haloTex) return haloTex
  const c = document.createElement('canvas')
  c.width = c.height = 128
  const ctx = c.getContext('2d')!
  const g = ctx.createRadialGradient(64, 64, 0, 64, 64, 64)
  g.addColorStop(0, 'rgba(255,255,255,0.95)')
  g.addColorStop(0.35, 'rgba(190,215,250,0.55)')
  g.addColorStop(0.7, 'rgba(150,190,240,0.16)')
  g.addColorStop(1, 'rgba(150,190,240,0)')
  ctx.fillStyle = g
  ctx.fillRect(0, 0, 128, 128)
  haloTex = new THREE.CanvasTexture(c)
  return haloTex
}

let shadowTex: THREE.Texture | null = null
/** 节点落地的软阴影贴片 */
export function shadowTexture(): THREE.Texture {
  if (shadowTex) return shadowTex
  const c = document.createElement('canvas')
  c.width = c.height = 128
  const ctx = c.getContext('2d')!
  const g = ctx.createRadialGradient(64, 64, 0, 64, 64, 64)
  g.addColorStop(0, 'rgba(70,100,150,0.32)')
  g.addColorStop(0.6, 'rgba(70,100,150,0.12)')
  g.addColorStop(1, 'rgba(70,100,150,0)')
  ctx.fillStyle = g
  ctx.fillRect(0, 0, 128, 128)
  shadowTex = new THREE.CanvasTexture(c)
  return shadowTex
}

export function formatTime(ts: string | null): string {
  if (!ts) return '—'
  const m = ts.match(/(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/)
  return m ? `${m[1]}-${m[2]} ${m[3]}:${m[4]}` : ts
}
