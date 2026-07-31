/**
 * 主题 store (2026-07-31 P2-1)
 * - light / dark 切换
 * - localStorage 持久化
 * - 同步到 <html class="dark">
 */
import { defineStore } from 'pinia'

const STORAGE_KEY = 'app_theme'

export const useThemeStore = defineStore('theme', {
  state: () => ({
    mode: localStorage.getItem(STORAGE_KEY) || 'light',
  }),
  getters: {
    isDark: (s) => s.mode === 'dark',
  },
  actions: {
    apply() {
      const root = document.documentElement
      if (this.mode === 'dark') {
        root.classList.add('dark')
      } else {
        root.classList.remove('dark')
      }
      localStorage.setItem(STORAGE_KEY, this.mode)
    },
    toggle() {
      this.mode = this.mode === 'dark' ? 'light' : 'dark'
      this.apply()
    },
    set(mode) {
      this.mode = mode
      this.apply()
    },
  },
})
