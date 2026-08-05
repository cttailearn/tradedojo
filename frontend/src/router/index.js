/**
 * Vue Router 配置
 *
 * 路由分区:
 *  - 训练端(用户端):根路径 / 默认进入登录/注册,登录后进入 /train/*
 *  - 管理端:通过特定后缀 #/admin 进入,/admin/* 全部需要 admin token
 *  两者 token 各自隔离(Pinia store + localStorage key 不同)
 */
import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useTrainAuthStore } from '@/stores/trainAuth'

const routes = [
  // ---------- 训练端(用户端,默认入口)----------
  {
    path: '/',
    name: 'TrainLogin',
    component: () => import('@/views/train/Login.vue'),
    meta: { public: true, app: 'train' },
  },

  // ---------- 训练端已登录区域 ----------
  {
    path: '/train',
    component: () => import('@/layouts/TrainLayout.vue'),
    meta: { app: 'train' },
    redirect: '/train/home',
    children: [
      { path: 'home',     name: 'TrainHome',    component: () => import('@/views/train/Home.vue'),    meta: { title: '训练首页', app: 'train' } },
      { path: 'setup',    name: 'TrainSetup',   component: () => import('@/views/train/Setup.vue'),   meta: { title: '发起训练', app: 'train' } },
      { path: 'trade/:id', name: 'TrainTrade',  component: () => import('@/views/train/Trade.vue'),   meta: { title: '交易训练', app: 'train' } },
      { path: 'report/:id', name: 'TrainReport', component: () => import('@/views/train/Report.vue'), meta: { title: '诊断报告', app: 'train' } },
      { path: 'stats',    name: 'TrainStats',   component: () => import('@/views/train/Stats.vue'),   meta: { title: '交割单统计', app: 'train' } },
      { path: 'wallet',   name: 'TrainWallet',  component: () => import('@/views/train/Wallet.vue'),  meta: { title: '钱包 / 兑换', app: 'train' } },
    ],
  },

  // ---------- 管理端(后缀 #/admin 进入)----------
  {
    path: '/admin/login',
    name: 'AdminLogin',
    component: () => import('@/views/Login.vue'),
    meta: { public: true, app: 'admin' },
  },
  {
    path: '/admin',
    component: () => import('@/layouts/AdminLayout.vue'),
    redirect: '/admin/dashboard',
    meta: { app: 'admin' },
    children: [
      { path: 'dashboard', name: 'Dashboard', component: () => import('@/views/Dashboard.vue'), meta: { title: '仪表盘', app: 'admin' } },
      { path: 'stocks',    name: 'Stocks',    component: () => import('@/views/Stocks.vue'),    meta: { title: '股票管理', app: 'admin' } },
      { path: 'tasks',     name: 'Tasks',     component: () => import('@/views/Tasks.vue'),     meta: { title: '数据更新', app: 'admin' } },
      { path: 'scheduler', name: 'Scheduler', component: () => import('@/views/Scheduler.vue'), meta: { title: '定时调度', app: 'admin' } },
      { path: 'backtest',  name: 'Backtest',  component: () => import('@/views/Backtest.vue'),  meta: { title: '回测中心', app: 'admin' } },
      { path: 'strategies', name: 'Strategies', component: () => import('@/views/Strategies.vue'), meta: { title: '策略编辑器', app: 'admin' } },
      { path: 'sources',   name: 'Sources',   component: () => import('@/views/Sources.vue'),   meta: { title: '数据源', app: 'admin' } },
      { path: 'system',    name: 'System',    component: () => import('@/views/System.vue'),    meta: { title: '系统状态', app: 'admin' } },
      // 训练端用户管理(管理员专属)
      { path: 'train-users', name: 'TrainUsersAdmin', component: () => import('@/views/train/UsersAdmin.vue'), meta: { title: '训练用户管理', app: 'admin' } },
      { path: 'train-redeem', name: 'TrainRedeemAdmin', component: () => import('@/views/train/RedeemAdmin.vue'), meta: { title: '兑换码生成', app: 'admin' } },
    ],
  },

  // 兜底:未匹配路径
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

// 2026-08-05: 双端视觉作用域 — 每次导航同步 html[data-app] 并应用该端主题模式
router.afterEach((to) => {
  const app = to.meta?.app || 'train'
  document.documentElement.dataset.app = app
  const theme = useThemeStore()
  theme.apply()
})

// 路由守卫
router.beforeEach((to) => {
  const app = to.meta?.app
  if (to.meta?.public) return true
  if (app === 'train') {
    const t = useTrainAuthStore()
    if (!t.isLoggedIn) return { path: '/', query: { redirect: to.fullPath } }
  } else if (app === 'admin') {
    const a = useAuthStore()
    if (!a.isLoggedIn) return { path: '/admin/login', query: { redirect: to.fullPath } }
  }
  return true
})

export default router
