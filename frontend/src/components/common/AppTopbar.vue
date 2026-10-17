<template>
  <header class="topbar">
    <div class="topbar__left">
      <OntologyBreadcrumb :items="breadcrumbs" />
    </div>
    <div class="topbar__right">
      <label class="topbar__scene">本体场景
        <select :value="sceneScope.selectedId" :disabled="!sceneScope.ready" @change="sceneScope.select(($event.target as HTMLSelectElement).value)">
          <option value="">全部场景</option>
          <option v-for="scene in sceneScope.scenes" :key="scene.id" :value="scene.id">{{ scene.name }}</option>
        </select>
      </label>
      <button v-if="sceneScope.error" @click="sceneScope.load()">{{ sceneScope.error }}</button>
      <span class="topbar__version" :title="buildInfo">{{ buildInfo }}</span>
      <button class="topbar__theme" type="button" @click="themeStore.toggle()">
        {{ themeStore.isDark ? '☀ 明快' : '☾ 暗黑' }}
      </button>
      <button class="topbar__icon-btn" title="我的待办" @click="router.push('/todo')">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
          <path d="M8 2a4 4 0 00-4 4v3l-1 1.5h10L12 9V6a4 4 0 00-4-4z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
          <path d="M6.5 13a1.5 1.5 0 003 0" stroke="currentColor" stroke-width="1.5"/>
        </svg>
        <span class="topbar__badge"></span>
      </button>
      <div class="topbar__divider"></div>
      <div class="topbar__user" @click="showSettings = true">
        <div class="topbar__user-avatar">{{ initial }}</div>
        <span class="topbar__user-name">{{ userName }}</span>
      </div>
    </div>

    <SettingsDialog :visible="showSettings" @close="showSettings = false" />
  </header>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useSceneScope } from '../../store/sceneScope'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../../store/auth'
import { useThemeStore } from '../../store/theme'
import OntologyBreadcrumb from './OntologyBreadcrumb.vue'
import SettingsDialog from './SettingsDialog.vue'


const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const themeStore = useThemeStore()
const sceneScope = useSceneScope()
onMounted(() => sceneScope.load())
const buildInfo = __APP_BUILD_INFO__
const showSettings = ref(false)

const userName = computed(() => authStore.user?.name || '用户')
const initial = computed(() => userName.value.charAt(0).toUpperCase())

const breadcrumbs = computed(() => {
  const title = route.meta.title as string | undefined
  if (title) return [{ label: title }]
  return [{ label: '首页' }]
})
</script>

<style scoped>
.topbar {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: var(--neutral-0);
  border-bottom: 1px solid var(--neutral-200);
  flex-shrink: 0;
  gap: 16px;
}
.topbar__left { display: flex; align-items: center; flex-shrink: 0; }
.topbar__scene { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.topbar__scene select { max-width: 200px; padding: 6px; border: 1px solid var(--neutral-200); border-radius: 6px; background: var(--neutral-0); color: var(--neutral-800); }
.topbar__right { display: flex; align-items: center; gap: 4px; flex-shrink: 0; }
.topbar__version { color: var(--neutral-500); font-size: 11px; white-space: nowrap; }
.topbar__theme { border: 1px solid var(--neutral-200); border-radius: 7px; background: var(--neutral-0); color: var(--neutral-700); padding: 6px 9px; cursor: pointer; }
@media (max-width: 880px) { .topbar__version { display: none; } .topbar { padding: 0 12px; } }
.topbar__icon-btn {
  position: relative;
  width: 34px; height: 34px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 8px;
  border: none; background: transparent;
  color: var(--neutral-500); cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast);
}
.topbar__icon-btn:hover { background: var(--neutral-100); color: var(--neutral-700); }
.topbar__badge {
  position: absolute; top: 7px; right: 7px;
  width: 6px; height: 6px; border-radius: var(--radius-full);
  background: var(--status-error); border: 1.5px solid #fff;
}
.topbar__divider {
  width: 1px; height: 24px;
  background: var(--neutral-200);
  margin: 0 8px;
}
.topbar__user {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border-radius: 8px;
  cursor: pointer;
  transition: background var(--transition-fast);
}
.topbar__user:hover { background: var(--neutral-100); }
.topbar__user-avatar {
  width: 28px; height: 28px; border-radius: var(--radius-full);
  background: linear-gradient(135deg, var(--semantic-500), var(--semantic-700));
  color: #fff;
  font-size: 11px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
}
.topbar__user-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--neutral-700);
}
</style>
