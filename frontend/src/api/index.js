/**
 * Axios 实例 - 自动添加 Token + 401 跳转 + 统一解包 + CSRF
 *
 * 后端响应有两种格式:
 *   1. 包装格式: { code: 0, message: "ok", data: {...} }
 *   2. 裸格式:   { ... }
 *
 * 鉴权模式:
 *   - 首选: cookie(由后端登录下发, httpOnly + Secure)
 *   - 备用: localStorage 中的 access_token(Bearer)
 *   - 写操作: 自动带 X-CSRF-Token(双 cookie 模式)
 */
import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'
import { useAuthStore } from '@/stores/auth'
import { useTrainAuthStore } from '@/stores/trainAuth'

const api = axios.create({
  baseURL: '/api',
  timeout: 60000,
  withCredentials: true, // 关键:带 cookie
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

// 请求拦截器: Bearer + CSRF
api.interceptors.request.use((cfg) => {
  const url = cfg.url || ''
  let store = null
  if (url.includes('/train/admin/')) {
    store = useAuthStore()
  } else if (url.includes('/train/')) {
    store = useTrainAuthStore()
  } else {
    store = useAuthStore()
  }
  // 1. 优先用 store 里的 token 显式发 Bearer(header 可绕过 cookie-only 后端)
  if (store?.token) {
    cfg.headers.Authorization = `Bearer ${store.token}`
  }
  // 2. 写操作时附加 CSRF header(双 cookie 模式)
  if (isWriteMethod(cfg.method)) {
    const csrf = readCookie('tdj_csrf')
    if (csrf) cfg.headers['X-CSRF-Token'] = csrf
  }
  return cfg
})

// 响应拦截器
api.interceptors.response.use(
  (resp) => {
    const body = resp.data
    if (body && typeof body === 'object' && typeof body.code === 'number' && 'message' in body) {
      if (body.code === 0) {
        return body.data === undefined ? body : body.data
      }
      return Promise.reject(new Error(body.message || '请求失败'))
    }
    return body
  },
  (err) => {
    const status = err.response?.status
    const url = err.config?.url || ''
    const data = err.response?.data
    const msg = data?.detail || data?.message || err.message || '请求失败'

    if (status === 401) {
      if (url.includes('/train/admin/')) {
        const auth = useAuthStore()
        auth.clear()
        if (router.currentRoute.value.path !== '/admin/login') {
          ElMessage.error('管理员登录已过期,请重新登录')
          router.push('/admin/login')
        }
      } else if (url.includes('/train/')) {
        const t = useTrainAuthStore()
        t.clear()
        const isTrainPage = router.currentRoute.value.path.startsWith('/train/')
        if (isTrainPage && router.currentRoute.value.path !== '/') {
          ElMessage.error('用户端登录已过期,请重新登录')
          router.push('/')
        }
      } else {
        const auth = useAuthStore()
        auth.clear()
        if (router.currentRoute.value.path !== '/admin/login') {
          ElMessage.error('管理员登录已过期,请重新登录')
          router.push('/admin/login')
        }
      }
      return Promise.reject(new Error('登录已过期'))
    }
    if (status === 429) {
      ElMessage.error(typeof msg === 'string' ? msg : '请求过于频繁')
      return Promise.reject(new Error('rate_limited'))
    }
    if (err.code === 'ECONNABORTED' || /timeout/i.test(err.message || '')) {
      ElMessage.error('请求超时,请稍后重试')
      return Promise.reject(new Error('请求超时'))
    }
    if (!err.response) {
      ElMessage.error('网络连接失败,请检查网络')
      return Promise.reject(new Error('网络连接失败'))
    }
    return Promise.reject(new Error(typeof msg === 'string' ? msg : JSON.stringify(msg)))
  }
)

export default api