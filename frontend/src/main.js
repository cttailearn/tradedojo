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

// 2026-07-31 P2-1: 暗色模式初始化
const savedTheme = localStorage.getItem('app_theme') || 'light'
if (savedTheme === 'dark') {
  document.documentElement.classList.add('dark')
}

for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(createPinia())
app.use(router)
app.use(ElementPlus)
app.mount('#app')