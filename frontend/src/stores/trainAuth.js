/**
 * 训练端鉴权状态管理 (Pinia) - 2026-07-31 P0-1 修复
 *
 * 鉴权机制改为 httpOnly cookie 模式:
 *   - token 完全由后端管理(浏览器自动随请求带 cookie)
 *   - 前端不持有 token, 不存 localStorage, 杜绝 XSS 盗 token
 *   - 仅保留 user 标识用于 UI 展示 + 路由守卫
 *   - 401 响应统一清 user state, 跳登录页
 */
import { defineStore } from 'pinia'
import { trainApi } from '@/api/modules'

const USER_KEY = 'stock_train_user'

export const useTrainAuthStore = defineStore('trainAuth', {
  state: () => ({
    // 旧 TOKEN_KEY 已废弃(2026-07-31),保留显式清理旧 localStorage
    user: JSON.parse(localStorage.getItem(USER_KEY) || 'null'),
    wallet: { balance: 0, total_spent: 0, total_topup: 0 },
  }),
  getters: {
    isLoggedIn: (s) => !!s.user && !!s.user.id,
  },
  actions: {
    setUser(user) {
      this.user = user
      if (user) {
        localStorage.setItem(USER_KEY, JSON.stringify(user))
      } else {
        localStorage.removeItem(USER_KEY)
      }
      // 清理旧的 token localStorage(2026-07-31 前可能残留)
      try { localStorage.removeItem('stock_train_token') } catch (_) { /* noop */ }
    },
    setAuth(_legacyToken, user) {
      // 兼容旧调用:忽略 token 参数,只存 user
      this.setUser(user)
    },
    clear() {
      this.user = null
      this.wallet = { balance: 0, total_spent: 0, total_topup: 0 }
      localStorage.removeItem(USER_KEY)
      try { localStorage.removeItem('stock_train_token') } catch (_) { /* noop */ }
    },
    async refreshWallet() {
      if (!this.user?.id) return
      try {
        const me = await trainApi.me()
        if (me?.wallet) {
          this.wallet = { ...this.wallet, ...me.wallet }
        } else if (me?.wallet_balance != null) {
          this.wallet = {
            ...this.wallet,
            balance: Number(me.wallet_balance || 0),
          }
        }
      } catch (e) {
        // 静默失败,避免训练页签到 / 下单循环报错
        console.warn('[trainAuth] refreshWallet failed', e?.message || e)
      }
    },
  },
})
