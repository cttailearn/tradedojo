/**
 * Vue Router - Tradedojo Mobile
 *
 * 页面层级:
 *   - 登录: /
 *   - 已登录主壳 (Bottom Tab):
 *       /home       首页 + 训练记录列表
 *       /setup      发起训练 (从首页新训练 CTA 进入,这里作独立页)
 *       /stats      交割单统计
 *       /wallet     钱包 / 兑换码
 *       /me         我的(用户信息 + 退出)
 *   - 训练详情(无 tab 全屏)
 *       /trade/:id  交易训练
 *       /report/:id 诊断报告
 *
 * 路由策略:
 *   - hash 模式:在 file:// / tauri:// / webview 通用
 *   - keep-alive TrainHome / Trade
 */
import { createRouter, createWebHashHistory } from 'vue-router'
import { useTrainAuthStore } from '@/stores/trainAuth'

import AppShell from '@/layouts/AppShell.vue'

const routes = [
  {
    path: '/',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { public: true, transition: 'fade' },
  },
  {
    path: '/',
    component: AppShell,
    meta: { requiresAuth: true },
    children: [
      { path: 'home',  name: 'TrainHome', component: () => import('@/views/Home.vue'),     meta: { title: '首页', tab: 'home' } },
      { path: 'setup', name: 'TrainSetup', component: () => import('@/views/Setup.vue'),   meta: { title: '发起训练', tab: 'setup' } },
      { path: 'stats', name: 'TrainStats', component: () => import('@/views/Stats.vue'),   meta: { title: '统计', tab: 'stats' } },
      { path: 'wallet', name: 'TrainWallet', component: () => import('@/views/Wallet.vue'), meta: { title: '钱包', tab: 'wallet' } },
      { path: 'me',    name: 'TrainMe',    component: () => import('@/views/Me.vue'),      meta: { title: '我的', tab: 'me' } },
    ],
  },
  {
    path: '/trade/:id',
    name: 'TrainTrade',
    component: () => import('@/views/Trade.vue'),
    meta: { requiresAuth: true, hideTabbar: true, transition: 'slide' },
  },
  {
    path: '/report/:id',
    name: 'TrainReport',
    component: () => import('@/views/Report.vue'),
    meta: { requiresAuth: true, hideTabbar: true, transition: 'slide' },
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach((to) => {
  if (to.meta?.public) return true
  const auth = useTrainAuthStore()
  if (!auth.isLoggedIn) {
    return { path: '/', query: { redirect: to.fullPath } }
  }
  return true
})

export default router
