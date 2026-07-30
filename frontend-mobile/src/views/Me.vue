<template>
  <div class="me page page--no-navbar" :style="{ paddingTop: 'var(--navbar-h)' }">
    <!-- 用户信息卡 -->
    <section class="profile">
      <div class="profile__avatar">
        {{ auth.displayName?.slice(0, 1).toUpperCase() }}
      </div>
      <div class="profile__info">
        <div class="profile__name">{{ auth.displayName }}</div>
        <div class="profile__username">@{{ auth.user?.username }}</div>
      </div>
      <van-tag type="success" plain size="medium">已登录</van-tag>
    </section>

    <section class="card">
      <h3 class="card__title">训练资金</h3>
      <ul class="list">
        <li class="list-item">
          <div class="list-item__body">
            <div class="list-item__title">余额</div>
          </div>
          <div class="list-item__aside num">¥ {{ money(auth.wallet.balance) }}</div>
        </li>
        <li class="list-item">
          <div class="list-item__body">
            <div class="list-item__title">累计充值</div>
          </div>
          <div class="list-item__aside num">¥ {{ money(auth.wallet.total_topup) }}</div>
        </li>
        <li class="list-item">
          <div class="list-item__body">
            <div class="list-item__title">累计消耗</div>
          </div>
          <div class="list-item__aside num">¥ {{ money(auth.wallet.total_spent) }}</div>
        </li>
      </ul>
      <button class="btn btn--primary btn--block" style="margin-top: var(--sp-3xl);" @click="goto('/wallet')">
        兑换码充值
      </button>
    </section>

    <section class="card">
      <h3 class="card__title">偏好</h3>
      <ul class="list">
        <li class="list-item" @click="toggleDark">
          <div class="list-item__body">
            <div class="list-item__title">深色模式</div>
            <div class="list-item__sub">适合夜盘复盘</div>
          </div>
          <van-switch v-model="darkMode" />
        </li>
        <li class="list-item">
          <div class="list-item__body">
            <div class="list-item__title">涨跌配色</div>
            <div class="list-item__sub">A股红涨绿跌(不可调整)</div>
          </div>
          <span class="tag tag--info">A 股</span>
        </li>
      </ul>
    </section>

    <section class="card">
      <h3 class="card__title">关于</h3>
      <ul class="list">
        <li class="list-item">
          <div class="list-item__body">
            <div class="list-item__title">版本</div>
          </div>
          <div class="list-item__aside">v1.0.0</div>
        </li>
        <li class="list-item">
          <div class="list-item__body">
            <div class="list-item__title">数据来源</div>
          </div>
          <div class="list-item__aside">BaoStock / Tushare</div>
        </li>
        <li class="list-item">
          <div class="list-item__body">
            <div class="list-item__title">免责声明</div>
            <div class="list-item__sub">仅供训练使用,不构成投资建议</div>
          </div>
        </li>
      </ul>
    </section>

    <section class="card">
      <button class="btn btn--plain btn--block" @click="logout">退出登录</button>
    </section>

    <div style="text-align: center; color: var(--text-placeholder); font-size: 0.22rem; padding: var(--sp-5xl) 0;">
      Tradedojo © 2026 · K线交易训练
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watchEffect } from 'vue'
import { useRouter } from 'vue-router'
import { showConfirmDialog, showSuccessToast } from 'vant'
import { useTrainAuthStore } from '@/stores/trainAuth'
import { money } from '@/utils/trainFee'
import { trainApi } from '@/api/modules'

const router = useRouter()
const auth = useTrainAuthStore()
const darkMode = ref(localStorage.getItem('tdj_mobile_dark') === '1')

watchEffect(() => {
  document.documentElement.classList.toggle('theme-dark', darkMode.value)
  localStorage.setItem('tdj_mobile_dark', darkMode.value ? '1' : '0')
})

function toggleDark() { /* v-model 自动更新 */ }

function goto(path) {
  router.push(path)
}

async function logout() {
  try {
    await showConfirmDialog({ title: '退出登录?', message: '退出后需要重新登录' })
  } catch { return }
  auth.clear()
  showSuccessToast('已退出登录')
  router.replace('/')
}

async function refreshWallet() {
  try {
    const w = await trainApi.wallet()
    auth.setWallet(w || {})
  } catch { /* silent */ }
}

onMounted(refreshWallet)
</script>

<style scoped>
.profile {
  margin: var(--sp-3xl) var(--sp-4xl) var(--sp-3xl);
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  padding: var(--sp-4xl);
  display: flex;
  align-items: center;
  gap: var(--sp-4xl);
  box-shadow: var(--shadow-xs);
}
.profile__avatar {
  width: 1.20rem; height: 1.20rem;
  border-radius: var(--radius-full);
  background: linear-gradient(135deg, var(--color-primary), var(--color-primary-dark));
  color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 0.48rem;
  font-weight: 700;
  flex-shrink: 0;
}
.profile__info { flex: 1; min-width: 0; }
.profile__name {
  font-size: 0.36rem;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.profile__username {
  font-size: 0.24rem;
  color: var(--text-secondary);
  margin-top: var(--sp-sm);
}

/* ========== Dark theme ========== */
:global(html.theme-dark) body {
  background: #0f172a;
  color: #e2e8f0;
}
:global(html.theme-dark) :root {
  --bg-page: #0f172a;
  --bg-card: #1e293b;
  --bg-muted: #334155;
  --bg-hover: #334155;
  --bg-tabbar: #1e293b;
  --text-primary: #f1f5f9;
  --text-regular: #e2e8f0;
  --text-secondary: #94a3b8;
  --border-color: #334155;
  --border-color-light: #1e293b;
}
:global(html.theme-dark) .profile,
:global(html.theme-dark) .card,
:global(html.theme-dark) .list-item {
  background-color: var(--bg-card) !important;
  color: var(--text-primary);
}
:global(html.theme-dark) .balance {
  filter: brightness(0.85);
}
</style>
