<template>
  <div class="shell" :class="{ 'shell--no-tabbar': !showTabbar }">
    <!-- 顶部导航条 -->
    <NavBar :title="title" :show-back="false">
      <template #right>
        <slot name="nav-right" />
      </template>
    </NavBar>

    <!-- 内容区 -->
    <main class="shell__main">
      <router-view v-slot="{ Component, route }">
        <transition :name="route.meta?.transition || 'fade'" mode="out-in">
          <keep-alive :include="['TrainHome', 'Trade', 'TrainStats', 'TrainWallet']">
            <component :is="Component" :key="route.fullPath" />
          </keep-alive>
        </transition>
      </router-view>
    </main>

    <!-- 底部 TabBar -->
    <BottomTabBar v-if="showTabbar" :active="activeTab" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import NavBar from '@/components/NavBar.vue'
import BottomTabBar from '@/components/BottomTabBar.vue'

const route = useRoute()
const router = useRouter()

const title = computed(() => route.meta?.title || 'K线训练')
const showTabbar = computed(() => !route.meta?.hideTabbar)
const activeTab = computed(() => {
  const t = route.path.split('/')[1]
  return ['home', 'setup', 'stats', 'wallet', 'me'].includes(t) ? t : 'home'
})

// 如果 / 根走的是 shell 但实际命中 login,redirect
const path = computed(() => route.path)
</script>

<style scoped>
.shell {
  min-height: 100vh;
  min-height: 100dvh;
  background: var(--bg-page);
  display: flex;
  flex-direction: column;
  /* 顶部刘海/挖孔安全区 */
  padding-top: var(--safe-top);
}
.shell__main {
  flex: 1;
  /* 给底部 tabbar 留位置 */
  padding-bottom: var(--tabbar-with-safe);
}
.shell--no-tabbar .shell__main {
  padding-bottom: var(--sp-3xl);
}
</style>
