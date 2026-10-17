import { createApp } from 'vue'
import { createPinia } from 'pinia'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import App from './App.vue'
import router from './router'
import i18n from './i18n'
import './styles/global.css'
import './styles/builder-replica.css'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
// Controls / MiniMap 基础样式全局引入：否则各 VueFlow 页面（数据血缘 / VOWL 编辑器 / 实体血缘 / 数据流）
// 的缩放控件按钮会因缺少样式而塌陷成不可见的窄条（图标显示为 |||）。
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(i18n)
app.use(Antd)
app.mount('#app')
