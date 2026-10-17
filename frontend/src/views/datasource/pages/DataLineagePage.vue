<template>
  <div class="di-page">
    <div class="di-page__header">
      <h1 class="di-page__title">数据血缘</h1>
      <p class="di-page__subtitle">追踪已登记的数据资产如何映射到本体对象，并被业务动作读取</p>
    </div>
    <DataLineageTab />
  </div>
</template>

<script setup lang="ts">
import DataLineageTab from '../tabs/DataLineageTab.vue'
</script>

<style scoped>
.di-page { padding: var(--space-8) var(--space-8); min-height: 100%; box-sizing: border-box; display: flex; flex-direction: column; }
.di-page__header { margin-bottom: var(--space-5); }
.di-page__title {
  font-size: var(--text-display-size); font-weight: var(--text-display-weight);
  line-height: var(--text-display-leading); letter-spacing: var(--text-display-tracking);
  color: var(--neutral-900); margin: 0;
}
.di-page__subtitle {
  font-size: var(--text-caption-size); color: var(--neutral-500); margin-top: 4px;
}
</style>
