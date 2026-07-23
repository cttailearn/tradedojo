/**
 * Vue Router 配置
 *
 * 注意:训练端路由以 /train 开头,与管理端的 hash 路由完全独立
 * 同一份浏览器可登录两边(token 各自隔离)
 */
import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useTrainAuthStore } from '@/stores/trainAuth'

const routes = [
  // ---------- 管理端 ----------
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { public: true, app: 'admin' },
  },
  {
    path: '/',
    component: () => import('@/layouts/AdminLayout.vue'),
    redirect: '/dashboard',
    meta: { app: 'admin' },
    children: [
      { path: 'dashboard', name: 'Dashboard', component: () => import('@/views/Dashboard.vue'), meta: { title: '仪表盘' } },
      { path: 'stocks',    name: 'Stocks',    component: () => import('@/views/Stocks.vue'),    meta: { title: '股票管理' } },
      { path: 'kline',     name: 'Kline',     component: () => import('@/views/Kline.vue'),     meta: { title: 'K线查询' } },
      { path: 'tasks',     name: 'Tasks',     component: () => import('@/views/Tasks.vue'),     meta: { title: '数据更新' } },
      { path: 'scheduler', name: 'Scheduler', component: () => import('@/views/Scheduler.vue'), meta: { title: '定时调度' } },
      { path: 'backtest',  name: 'Backtest',  component: () => import('@/views/Backtest.vue'),  meta: { title: '回测中心' } },
      { path: 'sources',   name: 'Sources',   component: () => import('@/views/Sources.vue'),   meta: { title: '数据源' } },
      { path: 'kronos',    name: 'Kronos',    component: () => import('@/views/Kronos.vue'),    meta: { title: 'AI 预测' } },
      { path: 'system',    name: 'System',    component: () => import('@/views/System.vue'),    meta: { title: '系统状态' } },
    ],
  },

  // ---------- 训练端(用户端 K 线交易训练)----------
  {
    path: '/train/login',
    name: 'TrainLogin',
    component: () => import('@/views/train/Login.vue'),
    meta: { public: true, app: 'train' },
  },
  {
    path: '/train',
    component: () => import('@/layouts/TrainLayout.vue'),
    meta: { app: 'train' },
    redirect: '/train/home',
    children: [
      { path: 'home',     name: 'TrainHome',    component: () => import('@/views/train/Home.vue'),    meta: { title: '训练首页' } },
      { path: 'setup',    name: 'TrainSetup',   component: () => import('@/views/train/Setup.vue'),   meta: { title: '发起训练' } },
      { path: 'trade/:id', name: 'TrainTrade',  component: () => import('@/views/train/Trade.vue'),   meta: { title: '交易训练' } },
      { path: 'wallet',   name: 'TrainWallet',  component: () => import('@/views/train/Wallet.vue'),  meta: { title: '钱包 / 兑换' } },
      { path: 'redeem-admin', name: 'TrainRedeemAdmin', component: () => import('@/views/train/RedeemAdmin.vue'), meta: { title: '兑换码生成' } },
      { path: 'admin', name: 'TrainUsersAdmin', component: () => import('@/views/train/UsersAdmin.vue'), meta: { title: '训练用户管理' } },
    ],
  },

  // 兜底:训练端访问根路径 /train 会被重定向到这里
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

// 路由守卫
router.beforeEach((to) => {
  const app = to.meta?.app
  if (to.meta?.public) return true
  if (app === 'train') {
    const t = useTrainAuthStore()
    if (!t.isLoggedIn) return { path: '/train/login', query: { redirect: to.fullPath } }
  } else {
    const a = useAuthStore()
    if (!a.isLoggedIn) return { path: '/login', query: { redirect: to.fullPath } }
  }
  return true
})

export default router
