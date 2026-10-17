<template>
  <BaseEdge :path="path" :marker-end="markerEnd" :style="edgeStyle" />
  <EdgeLabelRenderer>
    <div :style="labelStyle" class="edge-label" v-if="data.label">
      {{ data.label }}<span class="edge-label__card" v-if="data.cardinality"> · {{ data.cardinality }}</span>
    </div>
  </EdgeLabelRenderer>
</template>

<script setup lang="ts">
import { computed, type CSSProperties } from 'vue'
import { BaseEdge, EdgeLabelRenderer, getBezierPath } from '@vue-flow/core'

const props = defineProps<{
  id: string
  sourceX: number; sourceY: number
  targetX: number; targetY: number
  sourcePosition: any; targetPosition: any
  data: { label: string; cardinality: string }
  markerEnd?: string
}>()

const path = computed(() => {
  const [p] = getBezierPath({
    sourceX: props.sourceX, sourceY: props.sourceY,
    sourcePosition: props.sourcePosition,
    targetX: props.targetX, targetY: props.targetY,
    targetPosition: props.targetPosition,
  })
  return p
})

const edgeStyle = { stroke: '#cbd5e1', strokeWidth: 1.5, opacity: 0.8 }

const labelStyle = computed<CSSProperties>(() => ({
  position: 'absolute',
  transform: 'translate(-50%, -50%)',
  left: `${(props.sourceX + props.targetX) / 2}px`,
  top: `${(props.sourceY + props.targetY) / 2}px`,
  pointerEvents: 'none',
}))
</script>

<style scoped>
.edge-label {
  background: #fff;
  padding: 2px 8px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  font-size: 10px;
  font-weight: 500;
  color: #64748b;
  white-space: nowrap;
  box-shadow: 0 1px 4px rgba(0,0,0,0.05);
}
.edge-label__card { color: #94a3b8; font-size: 9px; }

/* ── 深色态覆盖：连线标签白底随主题翻转 ── */
html[data-theme="dark"] .edge-label { background: rgba(33, 34, 38, 0.9); border-color: var(--neutral-200); color: var(--neutral-600); }
</style>
