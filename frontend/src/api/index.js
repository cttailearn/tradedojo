/**
 * Axios 实例 - 自动添加 Token + 401 跳转 + 统一解包 {code,message,data}
 *
 * 后端响应有两种格式:
 *   1. 包装格式: { code: 0, message: "ok", data: {...} }     ← 登录/任务等
 *   2. 裸格式:   { ... }                                       ← 股票/K线/系统状态等
 * 拦截器自动统一:成功时返回实际 data,失败时抛 Error
 *
 * Token 策略:
 *   - 当请求 URL 含 /train/admin/ 时,使用管理端 token (管理员操作用户端数据)
 *   - 当请求 URL 含 /train/ 时,使用用户端 token (普通用户业务)
 *   - 其他情况使用管理端 token (默认)
 */
import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'
import { useAuthStore } from '@/stores/auth'
import { useTrainAuthStore } from '@/stores/trainAuth'

const api = axios.create({
  baseURL: '/api',
  timeout: 60000,
})

// 请求拦截器:自动加 Authorization
api.interceptors.request.use((cfg) => {
  const url = cfg.url || ''
  // /api/train/admin/* 必须带管理端 admin token (不是训练 token)
  if (url.includes('/train/admin/')) {
    const a = useAuthStore()
    if (a.token) cfg.headers.Authorization = `Bearer ${a.token}`
  } else if (url.includes('/train/')) {
    const t = useTrainAuthStore()
    if (t.token) cfg.headers.Authorization = `Bearer ${t.token}`
  } else {
    const a = useAuthStore()
    if (a.token) cfg.headers.Authorization = `Bearer ${a.token}`
  }
  return cfg
})

// 响应拦截器
api.interceptors.response.use(
  (resp) => {
    const body = resp.data
    // 后端包装格式 {code: number, message: string, data: any}
    // 注意: 只检查 NUMBER 类型的 code，避免把股票代码 "000001" 误判为包装格式
    if (body && typeof body === 'object' && typeof body.code === 'number' && 'message' in body) {
      if (body.code === 0) {
        return body.data === undefined ? body : body.data
      }
      // 业务错误
      return Promise.reject(new Error(body.message || '请求失败'))
    }
    // 裸格式直接返回
    return body
  },
  (err) => {
    const status = err.response?.status
    const url = err.config?.url || ''
    if (status === 401) {
      // 判断依据:哪一类 token 应该出现在该请求里,401 就跳到对应登录页
      //   /train/admin/* —— 应该带管理端 token  →  跳管理端登录页
      //   /train/*       —— 应该带用户端 token  →  跳用户端登录页
      //   其他           —— 默认管理端 token    →  跳管理端登录页
      if (url.includes('/train/admin/')) {
        // 管理端 token 过期/失效
        const auth = useAuthStore()
        auth.clear()
        if (router.currentRoute.value.path !== '/admin/login') {
          ElMessage.error('管理员登录已过期,请重新登录')
          router.push('/admin/login')
        }
      } else if (url.includes('/train/')) {
        // 用户端 token 过期/失效
        const t = useTrainAuthStore()
        t.clear()
        if (router.currentRoute.value.path !== '/') {
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
    const data = err.response?.data
    const msg =
      data?.detail ||
      data?.message ||
      err.message ||
      '请求失败'
    return Promise.reject(new Error(typeof msg === 'string' ? msg : JSON.stringify(msg)))
  }
)

export default api