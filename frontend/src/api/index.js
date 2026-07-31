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

// =============================================================================
// baseURL 配置:
//   - 默认:用 Vite proxy 相对路径 /api(适合本地后端 dev,无 CORS 问题)
//   - 想打线上 API:在 .env.development.local 里设 VITE_API_BASE=https://api.cttai.art/api
//     然后 npm run dev 就直接打服务器,不必启本地 FastAPI。
//     ⚠️ 线上域名走 https 跨域,后端必须把该 origin 放进 STOCK_CORS_ORIGINS,
//        且 Nginx 不能重复加 Access-Control-Allow-Credentials 头(否则会变成 "true, true"
//        被浏览器拒掉)。
//   ⚠️ baseURL 必须以 /api 结尾(后端所有路由都以 /api 为前缀)。
//     直连本机:VITE_API_BASE=http://127.0.0.1:8000/api
//     直连线上:VITE_API_BASE=https://api.cttai.art/api
//     走代理(默认):留空 → /api
// =============================================================================
const apiBase = (import.meta.env.VITE_API_BASE || '/api').replace(/\/+$/, '')
// 自动补全 /api 后缀(若用户漏写,直接拼接的请求会落到错误的路径)
const _normalizedBase = apiBase.endsWith('/api') ? apiBase : `${apiBase}/api`
const api = axios.create({
  baseURL: _normalizedBase,
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

// 请求拦截器: Bearer(管理端) + CSRF
// 2026-07-31 P0-1 修复: 训练端已改 cookie 模式, 拦截器不再为 train 端加 Bearer
api.interceptors.request.use((cfg) => {
  const url = cfg.url || ''
  // /train/admin/* 是管理员用的训练后台接口 → 走 admin token
  // 其他 /train/* 是用户端 → 走 train cookie(自动, 不需要手动加)
  // 其余全部走 admin token (管理端 API)
  let store = null
  if (url.includes('/train/admin/')) {
    store = useAuthStore()
  } else if (url.includes('/train/')) {
    store = useTrainAuthStore()
  } else {
    store = useAuthStore()
  }
  // 1. 仅管理端显式加 Bearer(训练端已迁 cookie, 浏览器自动带 httpOnly cookie)
  if (store === useAuthStore() && store?.token) {
    cfg.headers.Authorization = `Bearer ${store.token}`
  }
  // 2. 写操作时附加 CSRF header(双 cookie 模式,管理端)
  //    训练端不强制 CSRF(2026-07-31 设计:cookie + SameSite=Lax 已提供基础保护)
  if (isWriteMethod(cfg.method) && store === useAuthStore()) {
    const csrf = readCookie('tdj_csrf')
    if (csrf) cfg.headers['X-CSRF-Token'] = csrf
  }
  return cfg
})

// 响应拦截器
// 401 跳转策略:
//   - 当前路由属于 admin (/admin/*) → 跳 /admin/login,清理 admin token
//   - 当前路由属于 train (/train/*、根 / ) → 跳 /(训练登录),清理 train token
//   - 其他兜底:
//       - url 是 /api/train/* → 当成 train 跳 /
//       - 其余 → 当成 admin 跳 /admin/login
//   这样无论接口是哪个 token 失败,落到对应用户的登录页,绝不会把训练用户扔回 admin。
//
// 2026-07-31 P0-2 修复: 训练端 401 → 先尝试 /api/train/refresh, 成功则重发原请求;
//   refresh 失败再走原清理 + 跳登录流程。
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
  async (err) => {
    const status = err.response?.status
    const originalConfig = err.config || {}
    const url = originalConfig.url || ''
    const data = err.response?.data
    const msg = data?.detail || data?.message || err.message || '请求失败'

    if (status === 401) {
      const path = router.currentRoute.value.path || ''
      const onAdminPage = path.startsWith('/admin')
      const onTrainPage = path === '/' || path.startsWith('/train')
      // URL 维度:谁家的请求(只用于"URL 决定 app 走向"这一层)
      const isTrainUrl = url.includes('/train/') && !url.includes('/train/admin/')
      let app = 'admin'
      if (isTrainUrl) app = 'train'
      else if (onTrainPage && !onAdminPage) app = 'train'

      // 训练端 401 → 尝试 refresh(未重试过 + 非 /refresh/ /login/ /register/ 自身)
      const isAuthEndpoint = /\/(refresh|login|register|logout)(\/|$|\?)/.test(url)
      if (app === 'train' && !originalConfig._retried && !isAuthEndpoint) {
        try {
          await api.post('/train/refresh')
          originalConfig._retried = true
          return api(originalConfig)  // 重发原请求,新 cookie 已 set
        } catch {
          // refresh 失败 → 走原清理 + 跳登录
        }
      }

      if (app === 'train') {
        const t = useTrainAuthStore()
        t.clear()
        if (path !== '/' && onTrainPage) {
          ElMessage.error('用户端登录已过期,请重新登录')
          router.push({ path: '/', query: { redirect: path } })
        }
      } else {
        const auth = useAuthStore()
        auth.clear()
        if (path !== '/admin/login') {
          ElMessage.error('管理员登录已过期,请重新登录')
          router.push({ path: '/admin/login', query: { redirect: path } })
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