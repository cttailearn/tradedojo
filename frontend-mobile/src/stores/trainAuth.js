/**
 * 训练端鉴权状态管理 (Pinia)
 * - token 持久化在 localStorage 同一 key 名 (与后端校验一致)
 * - 如果你想走 Tauri secureStorage,把 localStorage 换成 Tauri 的 store
 */
import { defineStore } from 'pinia'

const TOKEN_KEY = 'stock_train_token'
const USER_KEY = 'stock_train_user'

export const useTrainAuthStore = defineStore('trainAuth', {
  state: () => ({
    token: localStorage.getItem(TOKEN_KEY) || '',
    user: JSON.parse(localStorage.getItem(USER_KEY) || 'null'),
    wallet: { balance: 0, total_spent: 0, total_topup: 0 },
  }),
  getters: {
    isLoggedIn: (s) => !!s.token,
    displayName: (s) => s.user?.display_name || s.user?.username || '用户',
  },
  actions: {
    setAuth(token, user) {
      this.token = token
      this.user = user
      localStorage.setItem(TOKEN_KEY, token)
      localStorage.setItem(USER_KEY, JSON.stringify(user))
    },
    setWallet(w) {
      if (w) this.wallet = { ...this.wallet, ...w }
    },
    clear() {
      this.token = ''
      this.user = null
      this.wallet = { balance: 0, total_spent: 0, total_topup: 0 }
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(USER_KEY)
    },
  },
})
