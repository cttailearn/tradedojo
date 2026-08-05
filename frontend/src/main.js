/**
 * Vue 应用入口
 */
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import 'element-plus/dist/index.css'
// 2026-08-04: EP 官方暗色变量(html.dark 选择器),必须在项目样式前引入
import 'element-plus/theme-chalk/dark/css-vars.css'

import App from './App.vue'
import router from './router'
import './styles/variables.css'
import './styles/theme.css'
import './styles/main.css'

const app = createApp(App)

const pinia = createPinia()

// 2026-08-05: 启动时按 hash 判定所在端, 设置视觉作用域并应用该端主题
const initialApp = location.hash.startsWith('#/admin') ? 'admin' : 'train'
document.documentElement.dataset.app = initialApp

app.use(pinia)
// 应用 per-app 主题(依赖 pinia 已安装)
import('./stores/theme').then(({ useThemeStore }) => {
  useThemeStore(pinia).apply()
})

for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(router)
app.use(ElementPlus)
app.mount('#app')