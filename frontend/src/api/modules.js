/**
 * 各业务模块 API 封装
 */
import api from './index'

export const authApi = {
  login: (username, password) =>
    api.post('/auth/login', { username, password }),
  me: () => api.get('/auth/me'),
  logout: () => api.post('/auth/logout'),
  changePassword: (old_password, new_password) =>
    api.post('/auth/change-password', { old_password, new_password }),
}

export const stocksApi = {
  list: (params) => api.get('/stocks', { params }),
  detail: (code) => api.get(`/stocks/${code}`),
  markets: () => api.get('/stocks/markets'),
  industries: () => api.get('/stocks/industries'),
}

export const klineApi = {
  query: (params) => api.get('/kline', { params }),
  indices: (params) => api.get('/kline/indices', { params }),
}

export const tasksApi = {
  trigger: (payload) => api.post('/tasks/update', payload),
  status: (taskId) => api.get(`/tasks/${taskId}`),
  list: (params) => api.get('/tasks', { params }),
  resetCheckpoint: (task) => api.post('/tasks/reset-checkpoint', { task }),
}

export const backtestApi = {
  single: (payload) => api.post('/backtest', payload),
  portfolio: (payload) => api.post('/backtest/portfolio', payload),
  asyncRun: (payload) => api.post('/backtest/async', payload),
}

export const systemApi = {
  status: () => api.get('/system/status'),
  check: () => api.get('/system/check'),
  logs: () => api.get('/system/logs'),
  tailLog: (name, lines = 200) =>
    api.get(`/system/logs/${name}`, { params: { lines } }),
}

export const schedulerApi = {
  status: () => api.get('/scheduler/status'),
  start: (config) => api.post('/scheduler/start', config || {}),
  stop: () => api.post('/scheduler/stop'),
  updateConfig: (config) => api.put('/scheduler/config', config),
  trigger: () => api.post('/scheduler/trigger'),
  history: (limit = 10) => api.get('/scheduler/history', { params: { limit } }),

  // 新端点:按数据类型操作
  listJobs: () => api.get('/scheduler/jobs'),
  updateJob: (task, body) => api.put(`/scheduler/jobs/${task}`, body),
  triggerJob: (task) => api.post(`/scheduler/jobs/${task}/trigger`),
}

export const sourcesApi = {
  list: () => api.get('/sources'),
  switch: (name) => api.post('/sources/switch', { name }),
  test: (name) => api.post(`/sources/test/${name}`),
  testAll: () => api.post('/sources/test-all'),
}

export const kronosApi = {
  status: () => api.get('/kronos/status'),
  load: (model, device) => api.post('/kronos/load', { model, device }),
  predict: (payload) => api.post('/kronos/predict', payload),
  unload: () => api.post('/kronos/unload'),
}

// ==========================================
// 训练端(用户端 K 线交易训练)
// ==========================================
export const trainApi = {
  // 注册 / 登录 / 登出 / refresh (2026-07-31 P0-1 改 cookie 模式)
  register: (username, password, display_name) =>
    api.post('/train/register', { username, password, display_name }),
  login: (username, password) => api.post('/train/login', { username, password }),
  logout: () => api.post('/train/logout'),
  refresh: () => api.post('/train/refresh'),
  me: () => api.get('/train/me'),
  wallet: () => api.get('/train/wallet'),
  redeem: (code) => api.post('/train/redeem', { code }),

  // 会话
  sessions: () => api.get('/train/sessions'),
  startSession: (payload) => api.post('/train/sessions/start', payload),
  session: (id) => api.get(`/train/sessions/${id}`),
  kline: (id, period = 'daily') => api.get(`/train/sessions/${id}/kline`, { params: { period } }),
  equity: (id) => api.get(`/train/sessions/${id}/equity`),
  trade: (id, payload) => api.post(`/train/sessions/${id}/trade`, payload),
  advance: (id, days = 1) => api.post(`/train/sessions/${id}/advance`, { days }),
  finish: (id) => api.post(`/train/sessions/${id}/finish`),
  rollback: (id) => api.post(`/train/sessions/${id}/rollback`),
  signals: (id) => api.get(`/train/sessions/${id}/signals`),
  attribution: (id) => api.get(`/train/sessions/${id}/attribution`),
  benchmark: (id) => api.get(`/train/sessions/${id}/benchmark`),
  leaderboard: (params = {}) => api.get('/train/stats/leaderboard', { params }),
  sessionStats: (id) => api.get(`/train/stats/session/${id}`),

  // 交割单统计 & 行为分析
  statsOverview: () => api.get('/train/stats/overview'),
  sessionStats: (id) => api.get(`/train/stats/session/${id}`),

  // 兑换码管理(管理员)
  redeemCodes: () => api.get('/train/admin/redeem-codes'),

  // 指数对照(训练端拉指数日线,与个股 K 线叠加)
  indices: () => api.get('/train/indices'),
  indexKline: (code, params = {}) =>
    api.get('/train/indices/kline', { params: { code, ...params } }),
  createRedeemCodes: (amount, count, note) =>
    api.post('/train/admin/redeem-codes', { amount, count, note }),

  // ---- 训练端·管理员后台 ----
  // 用户管理
  adminListUsers: (params = {}) =>
    api.get('/train/admin/users', { params }),
  adminGetUser: (userId) =>
    api.get(`/train/admin/users/${userId}`),
  adminSetActive: (userId, isActive, reason) =>
    api.post(`/train/admin/users/${userId}/set-active`, {
      is_active: isActive, reason,
    }),
  adminResetPassword: (userId, newPassword, reason) =>
    api.post(`/train/admin/users/${userId}/reset-password`, {
      new_password: newPassword, reason,
    }),
  adminAdjustWallet: (userId, delta, reason, adjustTopup = false) =>
    api.post(`/train/admin/users/${userId}/adjust-wallet`, {
      delta, reason, adjust_topup: adjustTopup,
    }),
  // 兑换码作废
  adminRevokeCode: (code, reason) =>
    api.post(`/train/admin/redeem-codes/${code}/revoke`, { reason }),
  // 分页 + 过滤的兑换码列表(可选 search/is_used/revoked)
  adminListCodes: (params = {}) =>
    api.get('/train/admin/redeem-codes', { params }),
  // 操作日志
  adminActionLog: (params = {}) =>
    api.get('/train/admin/action-log', { params }),
}