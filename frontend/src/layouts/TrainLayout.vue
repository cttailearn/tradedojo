<template>
  <el-container class="train-layout">
    <el-header class="train-header">
      <div class="brand" @click="$router.push('/train/home')">
        <span class="logo">📊</span>
        <span class="name">K线交易训练系统</span>
      </div>
      <div class="nav">
        <el-menu
          mode="horizontal"
          :default-active="activeMenu"
          :ellipsis="false"
          background-color="transparent"
          active-text-color="#409EFF"
          text-color="#e6e8eb"
          router
        >
          <el-menu-item index="/train/home">训练首页</el-menu-item>
          <el-menu-item index="/train/setup">发起训练</el-menu-item>
          <el-menu-item index="/train/wallet">钱包 / 兑换</el-menu-item>
          <el-menu-item index="/train/redeem-admin">兑换码生成</el-menu-item>
          <el-menu-item index="/train/admin">用户/资金管理</el-menu-item>
        </el-menu>
      </div>
      <div class="user-box">
        <el-tag size="small" type="warning" effect="dark" round>
          ¥ {{ money(wallet.balance) }}
        </el-tag>
        <el-dropdown @command="onCommand">
          <span class="user-info">
            <el-icon><UserFilled /></el-icon>
            <span>{{ auth.user?.display_name || auth.user?.username }}</span>
            <el-icon><ArrowDown /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item disabled>已用 ¥ {{ money(wallet.total_spent) }}</el-dropdown-item>
              <el-dropdown-item disabled>累计充值 ¥ {{ money(wallet.total_topup) }}</el-dropdown-item>
              <el-dropdown-item divided command="logout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </el-header>

    <el-main class="train-main">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </el-main>

    <el-footer class="train-footer" height="36px">
      <span>© 2026 Stock Data System · 用户训练端</span>
      <span style="margin-left:auto;">
        <el-link type="info" href="#/dashboard" target="_self">切换到管理后台</el-link>
      </span>
    </el-footer>
  </el-container>
</template>

<script setup>
import { ref, computed, onMounted, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useTrainAuthStore } from '@/stores/trainAuth'
import { trainApi } from '@/api/modules'

const auth = useTrainAuthStore()
const router = useRouter()
const route = useRoute()
const activeMenu = computed(() => '/' + (route.path.split('/').slice(0, 3).join('/')))
const wallet = reactive({ balance: 0, total_spent: 0, total_topup: 0 })

async function refreshWallet() {
  try {
    const w = await trainApi.wallet()
    Object.assign(wallet, w || {})
  } catch {}
}

function money(v) {
  return Number(v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function onCommand(cmd) {
  if (cmd === 'logout') {
    auth.clear()
    ElMessage.success('已退出')
    router.replace('/train/login')
  }
}

onMounted(async () => {
  try {
    const me = await trainApi.me()
    if (me?.username) {
      auth.user = {
        username: me.username,
        display_name: me.display_name,
        id: me.id,
        last_login: me.last_login,
      }
    }
    Object.assign(wallet, me?.wallet || {})
  } catch {
    auth.clear()
    router.push('/train/login')
  }
})

defineExpose({ refreshWallet })
// 暴露给子页面(Setup / Trade)调用的刷新函数
</script>

<style scoped>
.train-layout {
  min-height: 100vh;
  flex-direction: column;
  background: #0f1622;
}
.train-header {
  display: flex;
  align-items: center;
  height: 60px;
  background: #14202e;
  border-bottom: 1px solid #1f2d3d;
  padding: 0 24px;
}
.brand {
  display: flex;
  align-items: center;
  cursor: pointer;
  margin-right: 32px;
}
.brand .logo { font-size: 24px; margin-right: 8px; }
.brand .name { color: #f3f3f3; font-size: 16px; font-weight: bold; }
.nav { flex: 1; }
.nav :deep(.el-menu) { border-bottom: none; }
.user-box { display: flex; align-items: center; gap: 12px; }
.user-info {
  display: flex; align-items: center; gap: 6px;
  color: #e6e8eb; cursor: pointer;
}
.train-main {
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
  width: 100%;
}
.train-footer {
  display: flex; align-items: center;
  background: #14202e; color: #8a99ad;
  border-top: 1px solid #1f2d3d;
  padding: 0 24px; font-size: 12px;
}

.fade-enter-active, .fade-leave-active { transition: opacity 0.15s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
