/**
 * 主题 store (2026-07-31 P2-1, 2026-08-05 重构为 per-app)
 * - admin 端默认深色金融终端, train 端默认亮色道场
 * - 两端模式独立记忆 + 持久化
 * - 同步到 <html class="dark">, 由 router afterEach 设置 html[data-app]
 */
import { defineStore } from 'pinia'

const STORAGE_KEY = 'app_theme_v2'
const LEGACY_KEY = 'app_theme'

export const useThemeStore = defineStore('theme', {
  state: () => {
    let modes = { admin: 'dark', train: 'light' }
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (raw) modes = { ...modes, ...JSON.parse(raw) }
      else {
        // 迁移旧版单值
        const legacy = localStorage.getItem(LEGACY_KEY)
        if (legacy === 'dark' || legacy === 'light') {
          modes = { admin: legacy, train: legacy }
          localStorage.removeItem(LEGACY_KEY)
        }
      }
    } catch { /* 忽略损坏的存储 */ }
    return { modes }
  },
  getters: {
    currentApp: () => document.documentElement.dataset.app || 'admin',
    mode: (s) => s.modes[s.currentApp] || 'light',
    isDark: (s) => s.mode === 'dark',
  },
  actions: {
    apply() {
      const root = document.documentElement
      const dark = this.modes[root.dataset.app || 'admin'] === 'dark'
      root.classList.toggle('dark', dark)
      this.persist()
    },
    persist() {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(this.modes))
    },
    toggle() {
      const app = document.documentElement.dataset.app || 'admin'
      this.modes[app] = this.modes[app] === 'dark' ? 'light' : 'dark'
      this.apply()
    },
    set(mode) {
      const app = document.documentElement.dataset.app || 'admin'
      this.modes[app] = mode
      this.apply()
    },
  },
})
