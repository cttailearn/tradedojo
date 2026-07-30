<template>
  <nav class="tabbar" aria-label="主导航">
    <router-link
      v-for="t in tabs"
      :key="t.key"
      :to="t.path"
      class="tabbar__item"
      :class="{ 'is-active': active === t.key }"
    >
      <span class="tabbar__icon" v-html="t.icon" />
      <span class="tabbar__label">{{ t.label }}</span>
    </router-link>
  </nav>
</template>

<script setup>
defineProps({
  active: { type: String, default: 'home' },
})

const tabs = [
  {
    key: 'home',
    label: '首页',
    path: '/home',
    icon: `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 11 12 4l9 7"/><path d="M5 10v10h14V10"/></svg>`,
  },
  {
    key: 'setup',
    label: '新训练',
    path: '/setup',
    icon: `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 8v4l3 2"/></svg>`,
  },
  {
    key: 'stats',
    label: '统计',
    path: '/stats',
    icon: `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20V10"/><path d="M10 20V4"/><path d="M16 20v-6"/><path d="M22 20H2"/></svg>`,
  },
  {
    key: 'wallet',
    label: '钱包',
    path: '/wallet',
    icon: `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12V7H3v10a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-1h-4a2 2 0 0 1 0-4h4Z"/></svg>`,
  },
  {
    key: 'me',
    label: '我的',
    path: '/me',
    icon: `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>`,
  },
]
</script>

<style scoped>
.tabbar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 50;
  height: var(--tabbar-with-safe);
  padding-bottom: var(--safe-bottom);
  display: flex;
  background: var(--bg-tabbar);
  border-top: 1px solid var(--border-color-light);
  box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.04);
}
.tabbar__item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  text-decoration: none;
  color: var(--text-secondary);
  font-size: 0.20rem;
  transition: color 0.15s;
  padding-top: 4px;
}
.tabbar__item.is-active { color: var(--color-primary); }
.tabbar__item:active { background: var(--bg-hover); }
.tabbar__label { line-height: 1; }
</style>
