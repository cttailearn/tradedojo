<template>
  <div class="app-shell">
    <router-view v-slot="{ Component, route }">
      <transition :name="route.meta?.transition || 'slide'" mode="out-in">
        <keep-alive :include="['TrainHome', 'Trade']">
          <component :is="Component" :key="route.fullPath" />
        </keep-alive>
      </transition>
    </router-view>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { isTauri } from './main'

onMounted(() => {
  // Tauri 环境时,锁定竖屏;隐藏地址栏无关(本就是 native app)
  // 这里只 console 一下方便调试
  if (isTauri()) {
    // eslint-disable-next-line no-console
    console.log('[app] running inside Tauri runtime')
  }
})
</script>

<style>
.app-shell {
  /* 占满整屏 */
  min-height: 100vh;
  min-height: 100dvh;
  background: var(--bg-page);
  color: var(--text-primary);
}

.slide-enter-active,
.slide-leave-active {
  transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.25s;
}
.slide-enter-from { transform: translateX(30%); opacity: 0; }
.slide-leave-to   { transform: translateX(-30%); opacity: 0; }

.fade-enter-active, .fade-leave-active { transition: opacity 0.18s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
