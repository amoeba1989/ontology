<template>
  <a-config-provider :theme="antdTheme">
    <div v-if="isLoginPage" class="app-shell--login">
      <RouterView />
    </div>
    <div v-else class="app-shell">
      <AppSidebar />
      <div class="app-main">
        <AppTopbar />
        <main class="app-content">
          <RouterView v-if="sceneScope.ready" v-slot="{ Component }">
            <Transition name="page" mode="out-in">
              <component :is="Component" :key="`${route.path}:${sceneScope.selectedId}`" />
            </Transition>
          </RouterView>
        </main>
      </div>
    </div>
    <ToastContainer />
  </a-config-provider>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { theme as antdThemeApi } from 'ant-design-vue'
import { useThemeStore } from './store/theme'
import { useSceneScope } from './store/sceneScope'
import AppSidebar from './components/common/AppSidebar.vue'
import AppTopbar from './components/common/AppTopbar.vue'
import ToastContainer from './components/common/ToastContainer.vue'

const route = useRoute()
const themeStore = useThemeStore()
const sceneScope = useSceneScope()

const isLoginPage = computed(() => route.path === '/login')

// 全局 Ant Design 主题：随 data-theme 切换明/暗算法，并把关键 token 对齐项目中性板，
// 使 a-table / a-modal / a-input / a-tabs / a-select / a-card 等内置组件整体随主题翻色。
const antdTheme = computed(() => themeStore.isDark ? {
  algorithm: antdThemeApi.darkAlgorithm,
  token: {
    colorPrimary: '#5c7cfa',
    colorInfo: '#5c7cfa',
    colorBgBase: '#1a1b1e',
    colorBgContainer: '#1a1b1e',
    colorBgElevated: '#26272b',
    colorBgLayout: '#212226',
    colorBorder: '#37383d',
    colorBorderSecondary: '#2c2d31',
    colorText: '#f1f2f4',
    colorTextSecondary: '#c1c2c5',
    colorTextTertiary: '#9a9ba1',
    colorTextQuaternary: '#7a7b82',
    borderRadius: 8,
  },
} : {
  algorithm: antdThemeApi.defaultAlgorithm,
  token: { colorPrimary: '#4c6ef5', borderRadius: 8 },
})

onMounted(() => {
  themeStore.init()
})
</script>

<style scoped>
.app-shell--login { height: 100vh; }
.app-shell {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: var(--neutral-0);
}
.app-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.app-content {
  flex: 1;
  overflow-y: auto;
  background: var(--neutral-50);
  padding: 24px 32px;
}
@media (max-width: 1100px) { .app-content { padding: 12px; } }
@media (max-width: 700px) { .app-content { padding: 6px; } }
</style>
