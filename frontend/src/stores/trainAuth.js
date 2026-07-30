/**
 * 训练端鉴权状态管理 (Pinia)
 * 与管理员鉴权完全独立,token / user 分两个 localStorage key
 */
import { defineStore } from 'pinia'
import { trainApi } from '@/api/modules'

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
  },
  actions: {
    setAuth(token, user) {
      this.token = token
      this.user = user
      localStorage.setItem(TOKEN_KEY, token)
      localStorage.setItem(USER_KEY, JSON.stringify(user))
    },
    clear() {
      this.token = ''
      this.user = null
      this.wallet = { balance: 0, total_spent: 0, total_topup: 0 }
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(USER_KEY)
    },
    async refreshWallet() {
      if (!this.token) return
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
