<template>
  <footer class="tl">
    <div class="tl__ctrl">
      <button class="btn btn--main" type="button" :disabled="!events.length" @click="emit('toggle')">
        {{ playing ? '⏸ 暂停' : '▶ 播放' }}
      </button>
      <button class="btn" type="button" :disabled="index <= 0" @click="emit('step', -1)">上一条</button>
      <button class="btn" type="button" :disabled="index >= events.length - 1" @click="emit('step', 1)">下一条</button>
      <div class="tl__speed">
        <button
          v-for="s in SPEEDS"
          :key="s"
          type="button"
          class="chip"
          :class="{ 'is-on': speed === s }"
          @click="emit('speed', s)"
        >{{ s }}×</button>
      </div>
    </div>

    <div class="tl__now">
      <template v-if="current">
        <span class="tl__time">{{ formatTime(current.timestamp) }}</span>
        <span class="tl__lv" :class="'lv-' + current.level">{{ kindLabel(current.kind) }}</span>
        <b class="tl__sum">{{ current.summary }}</b>
        <span class="tl__tags">
          <em v-if="stubAction" class="tl__stub">执行器未实装 · 仅记流水</em>
          <em v-for="t in current.tags" :key="t.key" :class="'lv-' + t.level">{{ t.key }}: {{ t.value }}</em>
          <em v-if="current.relation_label" class="tl__rel">
            {{ current.source_entity_name_cn }} —{{ current.relation_label }}→ {{ current.entity_name_cn }}
          </em>
        </span>
      </template>
      <span v-else class="tl__idle">
        {{ events.length ? '拖动时间轴或点击播放，查看本体上的事件流' : '当前场景没有可回放的事件' }}
      </span>
    </div>

    <div class="tl__track" ref="trackRef" @pointerdown="onScrub">
      <div class="tl__rail" />
      <div class="tl__fill" :style="{ width: progress + '%' }" />
      <button
        v-for="(ev, i) in events"
        :key="ev.id"
        class="tl__tick"
        :class="['lv-' + ev.level, { 'is-on': i === index }]"
        type="button"
        :style="{ left: posOf(i) + '%' }"
        :title="formatTime(ev.timestamp) + ' ' + ev.summary"
        @click.stop="emit('jump', i)"
      />
      <div class="tl__head" :style="{ left: progress + '%' }" />
    </div>

    <div class="tl__count">{{ index + 1 }} / {{ events.length }}</div>
  </footer>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { SceneEvent } from '../../../../api/ontologyScene'
import { STUB_ACTION_TYPES, formatTime } from './layout'

const props = defineProps<{
  events: SceneEvent[]
  index: number
  playing: boolean
  speed: number
}>()

const emit = defineEmits<{
  (e: 'toggle'): void
  (e: 'step', delta: number): void
  (e: 'jump', index: number): void
  (e: 'speed', value: number): void
}>()

const SPEEDS = [0.5, 1, 2, 4]
const trackRef = ref<HTMLElement | null>(null)

const current = computed(() => props.events[props.index] ?? null)

/** 行动类型落在桩执行器上时，"执行成功"只等于记了一条审计流水 */
const stubAction = computed(() => {
  const ev = current.value
  if (ev?.kind !== 'action_exec') return false
  return STUB_ACTION_TYPES.has(ev.tags.find(t => t.key === '行动类型')?.value ?? '')
})

/** 按时间等比铺开；缺时间戳的事件按序号兜底，避免全部挤在起点 */
const span = computed(() => {
  let min = Infinity
  let max = -Infinity
  for (const e of props.events) {
    const v = timeOf(e)
    if (v == null) continue
    if (v < min) min = v
    if (v > max) max = v
  }
  return { min, max }
})

function posOf(i: number) {
  const fallback = (i / Math.max(1, props.events.length - 1)) * 100
  const t = timeOf(props.events[i])
  const { min, max } = span.value
  if (t == null || !isFinite(min) || max === min) return fallback
  return ((t - min) / (max - min)) * 100
}

function timeOf(ev: SceneEvent | undefined): number | null {
  if (!ev?.timestamp) return null
  const ms = Date.parse(ev.timestamp)
  return Number.isNaN(ms) ? null : ms
}

const progress = computed(() => {
  const total = props.events.length
  if (total <= 1) return total ? 50 : 0
  return (props.index / (total - 1)) * 100
})

function onScrub(e: PointerEvent) {
  const el = trackRef.value
  if (!el || !props.events.length) return
  const rect = el.getBoundingClientRect()
  const ratio = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width))
  emit('jump', Math.round(ratio * (props.events.length - 1)))
}

function kindLabel(k: string) {
  // rule_hit 来自人工点击"评估/执行"写下的审计流水，不是推理引擎自动命中
  return k === 'rule_hit' ? '人工评估' : k === 'action_exec' ? '行动执行' : '实例事件'
}
</script>

<style scoped>
.tl {
  /* 定位交给父级 .os-dock，本行不再声明 left/right/bottom，避免与图例争底部空间 */
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 14px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.85);
  border: 1px solid rgba(160, 187, 226, 0.5);
  box-shadow: 0 12px 28px rgba(46, 87, 148, 0.12);
  backdrop-filter: blur(12px);
  font-family: var(--font-sans);
  pointer-events: auto;
}

.tl__ctrl { display: flex; align-items: center; gap: 6px; flex: 0 0 auto; }
.btn {
  padding: 5px 10px;
  border-radius: 8px;
  border: 1px solid rgba(186, 205, 235, 0.8);
  background: #fff;
  color: #46628c;
  font-size: 11.5px;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s;
}
.btn:hover:not(:disabled) { border-color: #4c6ef5; color: #3b5bdb; }
.btn:disabled { opacity: 0.45; cursor: not-allowed; }
.btn--main { background: #4c6ef5; border-color: #4c6ef5; color: #fff; font-weight: 600; }
.btn--main:hover:not(:disabled) { background: #4263eb; color: #fff; }
.tl__speed { display: flex; gap: 3px; margin-left: 4px; }
.chip {
  padding: 3px 7px;
  border-radius: 6px;
  border: 1px solid transparent;
  background: transparent;
  color: #8aa3c8;
  font-size: 10.5px;
  cursor: pointer;
}
.chip.is-on { background: #eef2ff; border-color: #bac8ff; color: #364fc7; font-weight: 600; }

.tl__now { flex: 1 1 auto; min-width: 0; display: flex; align-items: center; gap: 8px; overflow: hidden; }
/* 0 宽容器里中文会逐字换行，把整条时间轴顶到 200 多 px 高并盖住图例：文案一律单行、超出省略 */
.tl__idle { font-size: 11.5px; color: #a7bcd9; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tl__time { font-size: 10.5px; color: #93aecf; flex: 0 0 auto; }
.tl__lv { font-size: 10px; padding: 1px 7px; border-radius: 999px; background: #eef2ff; color: #364fc7; flex: 0 0 auto; }
.tl__lv.lv-warning { background: #fff4e6; color: #d9480f; }
.tl__lv.lv-ok { background: #e6fcf5; color: #087f5b; }
.tl__sum { font-size: 12.5px; color: #1e3a6b; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tl__tags { display: flex; gap: 5px; overflow: hidden; }
.tl__tags em {
  font-style: normal;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 5px;
  background: #f1f3f5;
  color: #64748b;
  white-space: nowrap;
}
.tl__tags em.lv-warning { background: #fff4e6; color: #d9480f; }
.tl__tags em.lv-ok { background: #e6fcf5; color: #087f5b; }
.tl__rel { color: #4263eb !important; background: #edf2ff !important; }
.tl__stub { color: #d9480f !important; background: #fff4e6 !important; }

.tl__track { position: relative; flex: 0 1 260px; min-width: 120px; height: 26px; cursor: pointer; }
.tl__rail { position: absolute; left: 0; right: 0; top: 12px; height: 3px; border-radius: 2px; background: #dce7f5; }
.tl__fill { position: absolute; left: 0; top: 12px; height: 3px; border-radius: 2px; background: linear-gradient(90deg, #748ffc, #4c6ef5); }
.tl__tick {
  position: absolute;
  top: 9px;
  width: 9px;
  height: 9px;
  padding: 0;
  border-radius: 50%;
  border: 2px solid #fff;
  background: #91a7ff;
  transform: translateX(-50%);
  cursor: pointer;
  transition: transform 0.15s;
}
.tl__tick.lv-warning { background: #f08c00; }
.tl__tick.lv-ok { background: #20c997; }
.tl__tick.is-on { transform: translateX(-50%) scale(1.5); box-shadow: 0 0 0 3px rgba(76, 110, 245, 0.2); }
.tl__head { position: absolute; top: 4px; width: 2px; height: 18px; background: #3b5bdb; transform: translateX(-50%); border-radius: 1px; }

.tl__count { font-size: 11px; color: #8aa3c8; flex: 0 0 auto; font-variant-numeric: tabular-nums; }
</style>
