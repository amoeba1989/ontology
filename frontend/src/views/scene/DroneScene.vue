<template>
  <SceneWorkbench :config="config" />
</template>

<script setup lang="ts">
import SceneWorkbench, { type SceneWorkbenchConfig } from './SceneWorkbench.vue'

const config: SceneWorkbenchConfig = {
  apiPrefix: '/scenes/drone',
  title: '无人机反制处置',
  desc: '基于侦测装备 / 飞行事件 / 威胁研判本体的低慢小目标 OODA 反制工作台',
  agentName: '无人机反制研判智能体',
  speedUnit: 'km/h',
}
</script>
