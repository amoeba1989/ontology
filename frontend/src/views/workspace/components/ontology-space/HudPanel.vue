<template>
  <aside class="hud">
    <div v-if="!node" class="hud__empty">
      <div class="hud__empty-title">本体态势总览</div>
      <div class="hud__empty-desc">
        左侧选择或直接在三维场景中点击任意本体，查看它的<b>关系描述</b>、<b>规则约束</b>与<b>相关事件</b>。
      </div>
      <div class="hud__stats">
        <div class="stat"><span>{{ summary.node_count }}</span>个本体</div>
        <div class="stat"><span>{{ summary.edge_count }}</span>条关系</div>
        <div class="stat"><span>{{ summary.rule_count }}</span>条规则</div>
        <div class="stat"><span>{{ summary.attribute_count }}</span>个属性</div>
        <div class="stat"><span>{{ summary.instance_count }}</span>条实例</div>
      </div>
      <ul class="hud__tips">
        <li>轨道分层：核心对象在中枢，关联对象走中轨，事件对象走外轨</li>
        <li>选中后展开属性卫星环，关系线与箭头点亮一跳邻居</li>
        <li>底部时间轴播放事件，推演连线沿真实关系逐段亮起</li>
      </ul>
    </div>

    <template v-else>
      <header class="hud__head">
        <div class="hud__head-main">
          <h3>{{ node.name_cn }}</h3>
          <code>{{ node.name }}</code>
        </div>
        <div class="hud__badges">
          <em class="badge">T{{ node.tier }} {{ tierLabel }}</em>
          <em class="badge badge--ghost">{{ domainLabel(node.domain) }}</em>
          <em v-if="node.status !== 'published'" class="badge badge--warn">{{ node.status }}</em>
        </div>
        <p v-if="node.description" class="hud__desc">{{ node.description }}</p>
        <div class="hud__meta">
          <span>实例 <b>{{ node.instance_count }}</b></span>
          <span>关系 <b>{{ relEdges.length }}</b></span>
          <span>规则 <b>{{ node.rules.length }}</b></span>
          <span>约束 <b>{{ node.constraint_rule_count }}</b></span>
          <span v-if="node.source_table">源表 <b>{{ node.source_table }}</b></span>
        </div>
      </header>

      <section class="hud__block">
        <h4>关系描述 <i>{{ relEdges.length }}</i></h4>
        <p v-if="!relEdges.length" class="hud__none">该本体暂无显式关系</p>
        <button
          v-for="e in relEdges"
          :key="e.id"
          class="rel"
          type="button"
          @click="emit('focus', e.other)"
        >
          <span class="rel__dir">{{ e.out ? '→' : '←' }}</span>
          <span class="rel__body">
            <span class="rel__line">
              <b>{{ e.out ? e.toName : e.fromName }}</b>
              <i class="rel__cn">{{ e.edge.name_cn || e.edge.label }}</i>
            </span>
            <code v-if="e.edge.name_cn">{{ e.edge.label }}</code>
            <em>{{ e.edge.description || '无描述' }}</em>
          </span>
          <span class="rel__card">{{ e.edge.cardinality }}<i>{{ e.edge.rel_type }}</i></span>
        </button>
      </section>

      <section class="hud__block">
        <h4>规则约束 <i>{{ node.rules.length }}</i></h4>
        <p v-if="!node.rules.length" class="hud__none">未绑定业务规则</p>
        <p v-else-if="node.rules.length > MAX_RULE_BADGES" class="hud__cap">
          三维球顶只挂优先级最高的 {{ MAX_RULE_BADGES }} 条，其余 {{ node.rules.length - MAX_RULE_BADGES }} 条在此列出
        </p>
        <div v-for="r in node.rules" :key="r.id" class="rule" :class="'p-' + r.priority">
          <div class="rule__top">
            <b>{{ r.name }}</b>
            <em>{{ priorityLabel(r.priority) }}</em>
          </div>
          <p class="rule__cond">
            <span class="rule__k">条件</span>
            <code>{{ r.condition_expr || '由条件组驱动' }}</code>
          </p>
          <p class="rule__cond">
            <span class="rule__k">动作</span>
            <span>{{ r.action_desc || '—' }}</span>
            <i v-if="r.action_name" class="rule__act">↳ {{ r.action_name }}</i>
          </p>
          <div class="rule__foot">
            <span>命中 {{ r.trigger_count }} 次</span>
            <span>{{ r.status === 'active' ? '生效中' : r.status }}</span>
            <span v-if="r.last_triggered">最近 {{ formatTime(r.last_triggered) }}</span>
          </div>
        </div>
      </section>

      <section class="hud__block">
        <h4>约束与验证 <i>{{ node.constraint_rule_count }}</i></h4>
        <div v-if="node.constraint_rule_count" class="cons" :style="{ borderLeftColor: constraintColor }">
          <div class="cons__top">
            <b>{{ constraintStatusLabel }}</b>
            <em>{{ node.constraint_rule_count }} 条质量规则</em>
          </div>
          <ul class="cons__by">
            <li v-for="row in constraintRows" :key="row.key">
              <i :style="{ background: row.color }" />{{ row.label }} <b>{{ row.count }}</b>
            </li>
          </ul>
          <p class="cons__src">
            口径与数据质量页一致：取该本体绑定资产（{{ node.source_table || node.asset_id }}）已启用质量规则的
            最新一次评估结果，按 失败 &gt; 警告 &gt; 未验证 &gt; 通过 取最严重项；「未验证」表示规则已定义但从未执行过评估。
            <b>约束被定义不等于数据已通过验证。</b>
          </p>
        </div>
        <p v-else class="hud__none">该本体绑定的资产未配置质量规则，三维场景不画约束三角</p>
      </section>

      <section class="hud__block">
        <h4>属性约束 <i>{{ node.attributes.length }}</i></h4>
        <div class="attrs">
          <div v-for="a in node.attributes" :key="a.id" class="attr">
            <div class="attr__top">
              <b>{{ a.name }}</b>
              <em>{{ a.type }}</em>
              <span v-if="a.required" class="attr__req">必填</span>
            </div>
            <p v-if="a.description || a.constraint_text" class="attr__desc">
              {{ [a.description, a.constraint_text].filter(Boolean).join(' · ') }}
            </p>
          </div>
        </div>
      </section>

      <section v-if="node.actions.length" class="hud__block">
        <h4>可执行行动 <i>{{ node.actions.length }}</i></h4>
        <div v-for="a in node.actions" :key="a.id" class="action" :class="{ 'is-stub': isStubAction(a.action_type) }">
          <b>{{ a.name }}</b>
          <em>{{ actionTypeLabel(a.action_type) }}</em>
          <em v-if="isStubAction(a.action_type)" class="action__stub">未实装·仅记流水</em>
          <p v-if="a.description">{{ a.description }}</p>
        </div>
      </section>

      <section class="hud__block">
        <h4>相关事件 <i>{{ nodeEvents.length }}</i></h4>
        <p v-if="!nodeEvents.length" class="hud__none">事件流中暂无该本体的记录</p>
        <div
          v-for="ev in nodeEvents.slice(-7).reverse()"
          :key="ev.id"
          class="ev"
          :class="['lv-' + ev.level, { 'is-live': ev.id === activeEventId }]"
        >
          <span class="ev__t">{{ formatTime(ev.timestamp) }}</span>
          <span class="ev__b">
            <b>{{ ev.summary }}</b>
            <em v-if="ev.source_entity_name_cn">
              来自 {{ ev.source_entity_name_cn }}
              <code v-if="ev.relation_label">{{ ev.relation_label }}</code>
            </em>
            <em v-else>{{ kindLabel(ev.kind) }}</em>
          </span>
        </div>
      </section>
    </template>

    <!-- 通道说明折叠在这里：常驻图例只讲本体定义，颜色/尺寸的含义想深究再展开 -->
    <details class="hud__how">
      <summary>怎么看这张图 · 视觉通道</summary>
      <ul>
        <li><i class="chip chip--round" />球体尺寸 = 实例数（少 → 多）</li>
        <li>
          球体颜色 = 发布状态：
          <i class="chip" :style="{ background: STATUS_COLOR.published }" />已发布
          <i class="chip" :style="{ background: STATUS_COLOR.draft }" />草稿
          <i class="chip chip--hollow" :style="{ borderColor: STATUS_COLOR.published }" />无实例/未接源
        </li>
        <li>
          菱形颜色 = 规则优先级：
          <i v-for="p in (['high', 'medium', 'low'] as const)" :key="p" class="chip chip--diamond" :style="{ background: PRIORITY_COLOR[p] }" />高 / 中 / 低
        </li>
        <li>
          三角颜色 = 约束结论：
          <span v-for="s in CON_ORDER" :key="s" class="lgc">
            <i class="chip chip--tri" :style="{ borderBottomColor: CONSTRAINT_COLOR[s] }" />{{ CONSTRAINT_LABEL[s] }}
          </span>
          ；不画三角 = 未挂质量规则
        </li>
        <li>
          推演连线颜色 = 事件等级：
          <span v-for="(lv, k) in EVENT_LEVEL_LABEL" :key="k" class="lgc">
            <i class="chip chip--line" :style="{ background: EVENT_LEVEL_COLOR[k] }" />{{ lv }}
          </span>
        </li>
      </ul>
    </details>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { OntologyScene, SceneEdge, SceneEvent, SceneNode } from '../../../../api/ontologyScene'
import {
  CONSTRAINT_COLOR,
  CONSTRAINT_LABEL,
  EVENT_LEVEL_COLOR,
  EVENT_LEVEL_LABEL,
  MAX_RULE_BADGES,
  PRIORITY_COLOR,
  STATUS_COLOR,
  STUB_ACTION_TYPES,
  domainLabel,
  formatTime,
  type ConstraintStatus,
} from './layout'

const props = defineProps<{
  node: SceneNode | null
  scene: OntologyScene | null
  events: SceneEvent[]
  activeEventId: string | null
}>()

const emit = defineEmits<{ (e: 'focus', id: string): void }>()

const summary = computed(() => props.scene?.summary ?? {
  node_count: 0, edge_count: 0, domain_count: 0, attribute_count: 0, rule_count: 0, instance_count: 0,
})

const tierLabel = computed(() => {
  const t = props.node?.tier
  return t === 1 ? '核心对象' : t === 2 ? '关联对象' : t === 3 ? '事件对象' : '对象'
})

const nameOf = computed(() => {
  const map: Record<string, string> = {}
  props.scene?.nodes.forEach(n => { map[n.id] = n.name_cn })
  return map
})

interface RelRow { id: string; other: string; out: boolean; fromName: string; toName: string; edge: SceneEdge }
const relEdges = computed<RelRow[]>(() => {
  const node = props.node
  if (!node) return []
  return (props.scene?.edges ?? [])
    .filter(e => e.from_id === node.id || e.to_id === node.id)
    .map(e => ({
      id: e.id,
      other: e.from_id === node.id ? e.to_id : e.from_id,
      out: e.from_id === node.id,
      fromName: nameOf.value[e.from_id] ?? e.from_name,
      toName: nameOf.value[e.to_id] ?? e.to_name,
      edge: e,
    }))
})

const nodeEvents = computed(() => props.events.filter(ev => ev.entity_id === props.node?.id))

/* ── 约束与验证：读 scene 内联的资产健康度聚合，不再另发请求 ─────── */
const CON_ORDER: ConstraintStatus[] = ['failure', 'warning', 'unknown', 'healthy']
const constraintState = computed<ConstraintStatus>(() => {
  const s = props.node?.constraint_status
  return s && s in CONSTRAINT_COLOR ? (s as ConstraintStatus) : 'unknown'
})
const constraintColor = computed(() => CONSTRAINT_COLOR[constraintState.value])
const constraintStatusLabel = computed(() => CONSTRAINT_LABEL[constraintState.value])
const constraintRows = computed(() => CON_ORDER
  .map(key => ({
    key,
    label: CONSTRAINT_LABEL[key],
    color: CONSTRAINT_COLOR[key],
    count: props.node?.constraint_by_status?.[key] ?? 0,
  }))
  .filter(r => r.count > 0))

function priorityLabel(p: string) {
  return p === 'high' ? '高优先级' : p === 'low' ? '低优先级' : '中优先级'
}
function actionTypeLabel(t: string) {
  const map: Record<string, string> = {
    notification: '通知', modify_attribute: '改属性', automation: '自动化',
    compute: '计算', campaign: '营销活动', lifecycle: '生命周期', navigation: '页面跳转',
  }
  return map[t] ?? t
}
function kindLabel(k: string) {
  // 规则事件来自人工点击"评估/执行"的审计流水，不是推理引擎自动命中
  return k === 'rule_hit' ? '人工评估' : k === 'action_exec' ? '行动执行' : '实例事件'
}
function isStubAction(t: string) {
  return STUB_ACTION_TYPES.has(t)
}
</script>

<style scoped>
.hud {
  position: absolute;
  right: 16px;
  top: 74px;
  bottom: 96px;
  z-index: 8;
  width: 322px;
  overflow-y: auto;
  padding: 14px 14px 20px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.84);
  border: 1px solid rgba(160, 187, 226, 0.5);
  box-shadow: 0 14px 34px rgba(46, 87, 148, 0.14);
  backdrop-filter: blur(12px);
  font-family: var(--font-sans);
  color: #2f4670;
}
.hud::-webkit-scrollbar { width: 6px; }
.hud::-webkit-scrollbar-thumb { background: rgba(122, 165, 216, 0.5); border-radius: 3px; }

.hud__empty-title { font-size: 15px; font-weight: 700; color: #1e3a6b; margin-bottom: 8px; }
.hud__empty-desc { font-size: 12px; line-height: 1.7; color: #56719c; }
.hud__empty-desc b { color: #3b5bdb; }
.hud__stats { display: flex; flex-wrap: wrap; gap: 8px; margin: 14px 0 12px; }
.stat {
  flex: 1 0 40%;
  padding: 8px 10px;
  border-radius: 10px;
  background: linear-gradient(135deg, rgba(238, 242, 255, 0.9), rgba(255, 255, 255, 0.7));
  border: 1px solid rgba(186, 200, 255, 0.7);
  font-size: 11px;
  color: #64748b;
}
.stat span { display: block; font-size: 18px; font-weight: 700; color: #3b5bdb; }
.hud__tips { margin: 0; padding-left: 16px; font-size: 11.5px; line-height: 1.9; color: #6b87b0; }

.hud__how { margin-top: 16px; padding-top: 10px; border-top: 1px dashed rgba(186, 205, 235, 0.7); }
.hud__how summary { cursor: pointer; font-size: 11.5px; color: #56719c; user-select: none; }
.hud__how summary:hover { color: #3b5bdb; }
.hud__how ul { margin: 8px 0 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 7px; }
.hud__how li { display: flex; align-items: center; flex-wrap: wrap; gap: 4px 6px; font-size: 10.5px; line-height: 1.7; color: #64748b; }
.lgc { display: inline-flex; align-items: center; gap: 4px; }
.chip {
  width: 9px;
  height: 9px;
  border-radius: 2px;
  display: inline-block;
  flex: none;
  background: #8fa0b8;
}
.chip--round { border-radius: 50%; background: #3b5bdb; }
.chip--diamond { transform: rotate(45deg); }
.chip--hollow { background: transparent; border: 1.4px solid; }
.chip--tri {
  width: 0;
  height: 0;
  background: transparent;
  border-left: 5px solid transparent;
  border-right: 5px solid transparent;
  border-bottom: 9px solid #8fa0b8;
}
.chip--line { width: 16px; height: 3px; border-radius: 2px; }

.hud__head { padding-bottom: 12px; border-bottom: 1px solid rgba(186, 205, 235, 0.6); }
.hud__head-main { display: flex; align-items: baseline; gap: 8px; }
.hud__head h3 { margin: 0; font-size: 17px; color: #14284a; }
.hud__head code { font-size: 11px; color: #8aa3c8; font-family: var(--font-mono, monospace); }
.hud__badges { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.badge {
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 10.5px;
  font-style: normal;
  background: #eef2ff;
  color: #364fc7;
  border: 1px solid #bac8ff;
}
.badge--ghost { background: #f1f3f5; color: #64748b; border-color: #dee2e6; }
.badge--warn { background: #fff4e6; color: #d9480f; border-color: #ffd8a8; }
.hud__desc { margin: 9px 0 0; font-size: 11.5px; line-height: 1.65; color: #56719c; }
.hud__meta { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 9px; font-size: 11px; color: #8aa3c8; }
.hud__meta b { color: #3b5bdb; font-size: 12.5px; }

.hud__block { margin-top: 16px; }
.hud__block h4 {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 8px;
  font-size: 12px;
  letter-spacing: 0.04em;
  color: #1e3a6b;
}
.hud__block h4 i {
  font-style: normal;
  padding: 0 6px;
  border-radius: 999px;
  background: rgba(76, 110, 245, 0.12);
  color: #4263eb;
  font-size: 10px;
}
.hud__none { margin: 0; font-size: 11px; color: #a7bcd9; }

.rel {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  width: 100%;
  margin-bottom: 6px;
  padding: 8px 9px;
  text-align: left;
  border: 1px solid rgba(186, 205, 235, 0.65);
  border-radius: 10px;
  background: rgba(248, 251, 255, 0.85);
  cursor: pointer;
  transition: border-color 0.16s, box-shadow 0.16s;
}
.rel:hover { border-color: #4c6ef5; box-shadow: 0 4px 12px rgba(76, 110, 245, 0.14); }
.rel__dir { font-size: 13px; color: #4c6ef5; line-height: 1.4; }
.rel__body { flex: 1; display: flex; flex-direction: column; gap: 2px; }
.rel__line { display: flex; align-items: baseline; gap: 6px; }
.rel__cn { font-style: normal; font-size: 11px; color: #4c6ef5; line-height: 1.4; }
.rel__body b { font-size: 12px; color: #1e3a6b; }
.rel__body code { font-size: 10px; color: #748ffc; font-family: var(--font-mono, monospace); }
.rel__body em { font-size: 10.5px; font-style: normal; color: #8aa3c8; line-height: 1.5; }
.rel__card { font-size: 10px; color: #64748b; padding: 1px 6px; border-radius: 6px; background: #e9f1fb; display: flex; flex-direction: column; align-items: flex-end; gap: 1px; }
.rel__card i { font-style: normal; font-size: 9px; color: #93aecf; font-family: var(--font-mono, monospace); }
.hud__cap { margin: 0 0 7px; font-size: 10.5px; line-height: 1.5; color: #8aa3c8; }

.rule {
  margin-bottom: 8px;
  padding: 9px 10px;
  border-radius: 10px;
  border: 1px solid rgba(186, 205, 235, 0.6);
  border-left: 3px solid #4c6ef5;
  background: rgba(248, 251, 255, 0.9);
}
.rule.p-high { border-left-color: #e8590c; }
.rule.p-low { border-left-color: #adb5bd; }
.rule__top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.rule__top b { font-size: 12.5px; color: #1e3a6b; }
.rule__top em { font-style: normal; font-size: 10px; color: #e8590c; }
.rule.p-medium .rule__top em, .rule:not(.p-high):not(.p-low) .rule__top em { color: #4263eb; }
.rule__cond { margin: 6px 0 0; font-size: 11px; color: #46628c; line-height: 1.6; }
.rule__k { color: #93aecf; margin-right: 4px; }
.rule__cond code { color: #3b5bdb; font-family: var(--font-mono, monospace); font-size: 10.5px; }
.rule__act { display: block; font-style: normal; color: #0ca678; font-size: 10.5px; }
.rule__foot { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 7px; font-size: 10px; color: #8aa3c8; }

.cons {
  padding: 9px 10px;
  border-radius: 10px;
  border: 1px solid rgba(186, 205, 235, 0.6);
  border-left: 3px solid #8fa0b8;
  background: rgba(248, 251, 255, 0.9);
}
.cons__top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.cons__top b { font-size: 12.5px; color: #1e3a6b; }
.cons__top em { font-style: normal; font-size: 10px; color: #64748b; }
.cons__by { display: flex; flex-wrap: wrap; gap: 12px; margin: 8px 0 0; padding: 0; list-style: none; }
.cons__by li { display: inline-flex; align-items: center; gap: 5px; font-size: 10.5px; color: #56719c; }
.cons__by i { width: 8px; height: 8px; border-radius: 2px; transform: rotate(45deg); display: inline-block; }
.cons__by b { color: #1e3a6b; }
.cons__src { margin: 8px 0 0; font-size: 10px; line-height: 1.6; color: #8aa3c8; }
.cons__src b { color: #d9480f; }

.attrs { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.attr { padding: 7px 8px; border-radius: 9px; background: rgba(240, 246, 253, 0.9); border: 1px solid rgba(198, 215, 238, 0.7); }
.attr__top { display: flex; align-items: center; gap: 5px; }
.attr__top b { font-size: 11px; color: #22406e; }
.attr__top em { font-style: normal; font-size: 9.5px; color: #93aecf; }
.attr__req { font-size: 9px; color: #b3560b; padding: 0 4px; border-radius: 4px; background: #fff4e6; }
.attr__desc { margin: 4px 0 0; font-size: 10px; line-height: 1.5; color: #7b93b8; }

.action { margin-bottom: 7px; padding: 8px 9px; border-radius: 9px; background: rgba(230, 252, 245, 0.7); border: 1px solid rgba(150, 242, 215, 0.8); }
.action b { font-size: 12px; color: #087f5b; }
.action em { font-style: normal; font-size: 10px; color: #20c997; margin-left: 6px; }
.action p { margin: 3px 0 0; font-size: 10.5px; color: #5c8f80; }
/* 桩执行器不配绿色"已生效"底色：状态色只能表达真实发生过的事 */
.action.is-stub { background: rgba(248, 249, 250, 0.85); border-color: rgba(206, 212, 218, 0.9); }
.action.is-stub b { color: #495057; }
.action.is-stub p { color: #868e96; }
.action__stub { color: #d9480f !important; }

.ev { display: flex; gap: 8px; padding: 6px 0; border-bottom: 1px dashed rgba(198, 215, 238, 0.7); }
.ev:last-child { border-bottom: none; }
.ev__t { flex: 0 0 74px; font-size: 10px; color: #93aecf; }
.ev__b { flex: 1; display: flex; flex-direction: column; gap: 2px; }
.ev__b b { font-size: 11.5px; color: #2f4670; font-weight: 600; }
.ev__b em { font-style: normal; font-size: 10px; color: #8aa3c8; }
.ev__b code { margin-left: 4px; font-size: 9.5px; color: #748ffc; }
.ev.lv-warning .ev__b b { color: #d9480f; }
.ev.lv-ok .ev__b b { color: #087f5b; }
.ev.is-live { background: rgba(76, 110, 245, 0.08); border-radius: 8px; }
</style>
