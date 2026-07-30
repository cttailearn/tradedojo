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
          router
        >
          <el-menu-item index="/train/home">训练首页</el-menu-item>
          <el-menu-item index="/train/setup">发起训练</el-menu-item>
          <el-menu-item index="/train/stats">交割单统计</el-menu-item>
          <el-menu-item index="/train/wallet">钱包 / 兑换</el-menu-item>
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
    </el-footer>
  </el-container>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useTrainAuthStore } from '@/stores/trainAuth'
import { trainApi } from '@/api/modules'

const auth = useTrainAuthStore()
const router = useRouter()
const route = useRoute()
const activeMenu = computed(() => '/' + (route.path.split('/').slice(0, 3).join('/')))
const wallet = computed(() => auth.wallet)
let walletTimer = null

function money(v) {
  return Number(v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function onCommand(cmd) {
  if (cmd === 'logout') {
    auth.clear()
    ElMessage.success('已退出')
    router.replace('/')
  }
}

function startWalletPolling() {
  if (walletTimer) return
  // 立即拉一次,然后每 8 秒同步一次,确保下单 / 推进 / 充值后右上角能反映
  auth.refreshWallet()
  walletTimer = setInterval(() => auth.refreshWallet(), 8000)
}

function stopWalletPolling() {
  if (walletTimer) {
    clearInterval(walletTimer)
    walletTimer = null
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
    if (me?.wallet) {
      auth.wallet = { ...auth.wallet, ...me.wallet }
    } else if (me?.wallet_balance != null) {
      auth.wallet = {
        ...auth.wallet,
        balance: Number(me.wallet_balance || 0),
      }
    }
    startWalletPolling()
  } catch {
    auth.clear()
    router.push('/')
  }
})

onUnmounted(() => {
  stopWalletPolling()
})

defineExpose({ refreshWallet: () => auth.refreshWallet() })
// 暴露给子页面(Setup / Trade)调用的刷新函数
</script>

<style scoped>
.train-layout {
  min-height: 100vh;
  flex-direction: column;
  background: var(--bg-page);
}
.train-header {
  display: flex;
  align-items: center;
  height: var(--header-height);
  background: var(--bg-header);
  border-bottom: 1px solid var(--border-color-light);
  padding: 0 var(--space-2xl);
  box-shadow: var(--shadow-xs);
}
.brand {
  display: flex;
  align-items: center;
  cursor: pointer;
  margin-right: var(--space-3xl);
  gap: var(--space-sm);
}
.brand .logo {
  width: 32px; height: 32px;
  background: var(--color-primary);
  border-radius: var(--radius-md);
  display: flex; align-items: center; justify-content: center;
  font-size: 16px; color: #fff;
}
.brand .name {
  color: var(--text-primary); font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  letter-spacing: -0.01em;
}
.nav { flex: 1; }
.nav :deep(.el-menu) {
  border-bottom: none;
  background: transparent;
}
.nav :deep(.el-menu-item) { font-size: var(--text-base); }
.user-box { display: flex; align-items: center; gap: var(--space-md); }
.user-info {
  display: flex; align-items: center; gap: var(--space-sm);
  color: var(--text-regular); cursor: pointer;
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  transition: all var(--transition-fast);
}
.user-info:hover { background: var(--bg-hover); }
.train-main {
  padding: var(--space-2xl);
  max-width: var(--content-max-width);
  margin: 0 auto;
  width: 100%;
}
.train-footer {
  display: flex; align-items: center;
  background: var(--bg-header); color: var(--text-secondary);
  border-top: 1px solid var(--border-color-light);
  padding: 0 var(--space-2xl); font-size: var(--text-xs);
}

.fade-enter-active, .fade-leave-active { transition: opacity 0.15s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
