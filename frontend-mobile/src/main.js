/**
 * Vue 应用入口 - Tradedojo Mobile
 *
 * 与 web 版差异:
 *   - 用 Vant 4 移动组件库(替代 Element Plus)
 *   - hash 路由(直接打 APK 后 file:// 协议加载仍可工作)
 *   - Tauri 2 环境检测:有 __TAURI_INTERNALS__ 时挂全局
 */
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import Vant from 'vant'
import 'vant/lib/index.css'

import App from './App.vue'
import router from './router'
// 按需注册 echarts(必须在 App 之前)
import './plugins/echarts'
import './styles/variables.css'
import './styles/main.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(Vant)
app.mount('#app')

// Tauri 2 环境标记:window.__TAURI__ 在 webview 启动后由 @tauri-apps/api 注入
export const isTauri = () =>
  typeof window !== 'undefined' && !!window.__TAURI_INTERNALS__
