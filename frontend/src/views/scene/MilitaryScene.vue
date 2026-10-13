<template>
  <SceneWorkbench :config="config" />
</template>

<script setup lang="ts">
import SceneWorkbench, { type SceneWorkbenchConfig } from './SceneWorkbench.vue'

const config: SceneWorkbenchConfig = {
  apiPrefix: '/scenes/military',
  title: '边海空情目标研判',
  desc: '基于军事本体（目标 / 传感器 / 行为事件 / 研判结论）的 OODA 席位协同工作台',
  agentName: '目标行为研判智能体',
  speedUnit: '节',
}
</script>
