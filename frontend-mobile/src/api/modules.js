/**
 * 训练端 API 封装(仅训练端,无 admin 部分)
 */
import api from './index'

export const stocksApi = {
  industries: () => api.get('/stocks/industries'),
}

export const trainApi = {
  register: (username, password, display_name) =>
    api.post('/train/register', { username, password, display_name }),
  login: (username, password) => api.post('/train/login', { username, password }),
  me: () => api.get('/train/me'),
  wallet: () => api.get('/train/wallet'),
  redeem: (code) => api.post('/train/redeem', { code }),

  sessions: () => api.get('/train/sessions'),
  startSession: (payload) => api.post('/train/sessions/start', payload),
  session: (id) => api.get(`/train/sessions/${id}`),
  kline: (id, period = 'daily') =>
    api.get(`/train/sessions/${id}/kline`, { params: { period } }),
  equity: (id) => api.get(`/train/sessions/${id}/equity`),
  trade: (id, payload) => api.post(`/train/sessions/${id}/trade`, payload),
  advance: (id, payload = { days: 1 }) => api.post(`/train/sessions/${id}/advance`, payload),
  finish: (id) => api.post(`/train/sessions/${id}/finish`),

  statsOverview: () => api.get('/train/stats/overview'),
  sessionStats: (id) => api.get(`/train/stats/session/${id}`),

  indices: () => api.get('/train/indices'),
  indexKline: (code, params = {}) =>
    api.get('/train/indices/kline', { params: { code, ...params } }),
}
