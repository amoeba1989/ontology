<template>
  <div class="ln-node ln-node--app" :title="data.label">
    <Handle type="target" :position="Position.Left" class="ln-node__handle" />
    <span class="ln-node__icon">📊</span>
    <span class="ln-node__label">{{ data.label }}</span>
    <Handle type="source" :position="Position.Right" class="ln-node__handle ln-node__handle--hidden" />
  </div>
</template>

<script setup lang="ts">
import { Handle, Position } from '@vue-flow/core'
defineProps<{ data: { label: string } }>()
</script>

<style scoped>
.ln-node--app {
  width: 118px;
  min-height: 34px;
  background: #FFF7ED;
  border: 2px solid #f59e0b;
  border-radius: 8px;
  padding: 7px 12px;
  font-size: 11px;
  font-weight: 600;
  color: #92400e;
  text-align: center;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1.2;
  box-sizing: border-box;
}
.ln-node__icon { margin-right: 4px; flex: 0 0 auto; }
.ln-node__label { white-space: pre-line; }
.ln-node__handle {
  background: #f59e0b;
  width: 7px;
  height: 7px;
  border: none;
}
.ln-node__handle--hidden { visibility: hidden; }

/* ── 深色态覆盖：行动/规则节点浅底→橙色半透（彩色描边保留）── */
html[data-theme="dark"] .ln-node--app { background: rgba(245,158,11,.15); color: #ffa94d; }
</style>
