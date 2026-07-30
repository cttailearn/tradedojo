/**
 * Axios 实例 - 移动端
 *
 * 与 web 版差异:
 *   - 默认 baseURL 在 Tauri APK 模式下指向上线 https://api.cttai.art/api
 *   - Web 开发模式 (npm run dev) 用 /api 相对路径(被 Vite 代理)
 *   - 401 自动登出用 Vant 的 showToast 而非 ElMessage
 *
 * ⚠️ 重要:上线前必须确认 `VITE_API_BASE` 已配置,且后端 CORS/SameSite 允许移动来源
 */
import axios from 'axios'
import { showToast, showFailToast } from 'vant'
import router from '@/router'
import { useTrainAuthStore } from '@/stores/trainAuth'

// 优先用 VITE_API_BASE;默认指向上线(FastAPI)
const apiBase = (import.meta.env.VITE_API_BASE || 'https://api.cttai.art/api').replace(/\/+$/, '')

export const api = axios.create({
  baseURL: apiBase,
  timeout: 30000,
  withCredentials: true,
})

function readCookie(name) {
  if (typeof document === 'undefined') return ''
  const m = document.cookie.match(new RegExp('(^|;\\s*)' + name + '=([^;]+)'))
  return m ? decodeURIComponent(m[2]) : ''
}

function isWriteMethod(method) {
  const m = (method || 'get').toLowerCase()
  return ['post', 'put', 'patch', 'delete'].includes(m)
}

api.interceptors.request.use((cfg) => {
  const url = cfg.url || ''
  // 训练端没有 admin 范畴,统一从 trainAuth 取 token
  const auth = useTrainAuthStore()
  if (auth.token) {
    cfg.headers.Authorization = `Bearer ${auth.token}`
  }
  if (isWriteMethod(cfg.method)) {
    const csrf = readCookie('tdj_csrf')
    if (csrf) cfg.headers['X-CSRF-Token'] = csrf
  }
  // 调试:打印请求路径(只在 dev)
  if (import.meta.env.DEV) {
    // eslint-disable-next-line no-console
    console.log('[api]', cfg.method?.toUpperCase(), url)
  }
  return cfg
})

api.interceptors.response.use(
  (resp) => {
    const body = resp.data
    if (body && typeof body === 'object' && typeof body.code === 'number' && 'message' in body) {
      if (body.code === 0) return body.data === undefined ? body : body.data
      return Promise.reject(new Error(body.message || '请求失败'))
    }
    return body
  },
  (err) => {
    const status = err.response?.status
    const data = err.response?.data
    const msg = (typeof data === 'object' ? (data.detail || data.message) : null)
      || err.message
      || '请求失败'

    if (status === 401) {
      const auth = useTrainAuthStore()
      auth.clear()
      // 当前已在登录页则不再提示/跳转
      if (router.currentRoute.value.path !== '/') {
        showFailToast('登录已过期,请重新登录')
        router.replace('/')
      }
      return Promise.reject(new Error('登录已过期'))
    }
    if (status === 429) {
      showFailToast(typeof msg === 'string' ? msg : '请求过于频繁')
      return Promise.reject(new Error('rate_limited'))
    }
    if (err.code === 'ECONNABORTED' || /timeout/i.test(err.message || '')) {
      showFailToast('请求超时,请检查网络')
      return Promise.reject(new Error('请求超时'))
    }
    if (!err.response) {
      showFailToast('网络连接失败')
      return Promise.reject(new Error('网络连接失败'))
    }
    return Promise.reject(new Error(typeof msg === 'string' ? msg : '请求失败'))
  },
)

export default api
