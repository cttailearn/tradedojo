/**
 * 训练端鉴权状态管理 (Pinia)
 * 与管理员鉴权完全独立,token / user 分两个 localStorage key
 */
import { defineStore } from 'pinia'

const TOKEN_KEY = 'stock_train_token'
const USER_KEY = 'stock_train_user'

export const useTrainAuthStore = defineStore('trainAuth', {
  state: () => ({
    token: localStorage.getItem(TOKEN_KEY) || '',
    user: JSON.parse(localStorage.getItem(USER_KEY) || 'null'),
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
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(USER_KEY)
    },
  },
})
