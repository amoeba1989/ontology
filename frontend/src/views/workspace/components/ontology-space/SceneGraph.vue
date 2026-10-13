<template>
  <div class="scene-graph" :class="{ 'is-pointing': !!hoveredId }" @click="onSurfaceClick">
    <TresCanvas clear-color="#eef4fb" antialias>
      <SceneRoot
        ref="rootRef"
        :layout="layout"
        :selected-id="selectedId"
        :hovered-id="hoveredId"
        :spinning="spinning"
        @select="emit('select', $event)"
        @hover="emit('hover', $event)"
      />
    </TresCanvas>

    <div class="scene-graph__tip">
      拖拽旋转 · 滚轮缩放 · 点击类看详情 · 悬停菱形看规则 · 悬停三角看约束 · 点击空白复位
    </div>
  </div>
</template>

<script setup lang="ts">
import { shallowRef } from 'vue'
import { TresCanvas } from '@tresjs/core'
import type { SceneEvent } from '../../../../api/ontologyScene'
import type { SceneLayout } from './layout'
import SceneRoot from './SceneRoot.vue'

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

const rootRef = shallowRef<{ spawn: (ev: SceneEvent | null) => void } | null>(null)

/** 时间轴每步只命令式投递一条推演连线进画布，不作为 prop 下传（见 SceneRoot.spawn 注释） */
defineExpose({
  spawn(ev: SceneEvent | null) {
    rootRef.value?.spawn(ev)
  },
})

// 节点点击由 Tres 射线派发并同步 hover 状态；空白处（未悬停任何本体）点击才复位选中
function onSurfaceClick() {
  if (!props.hoveredId) emit('select', null)
}
</script>

<style scoped>
.scene-graph {
  position: absolute;
  inset: 0;
  overflow: hidden;
  background:
    radial-gradient(circle at 50% 12%, rgba(255, 255, 255, 0.95), rgba(232, 240, 251, 0) 55%),
    linear-gradient(180deg, #f4f8fd 0%, #e6eefb 62%, #dbe7f7 100%);
}
.scene-graph canvas { display: block; outline: none; }
.scene-graph.is-pointing :deep(canvas) { cursor: pointer; }

.scene-graph__tip {
  position: absolute;
  right: 18px;
  top: 16px;
  z-index: 6;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.7);
  border: 1px solid rgba(160, 187, 226, 0.45);
  font-family: var(--font-sans);
  font-size: 11px;
  color: #6b87b0;
  pointer-events: none;
}
</style>
