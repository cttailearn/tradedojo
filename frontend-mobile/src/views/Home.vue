<template>
  <div class="home page page--no-navbar" :style="{ paddingTop: 'var(--navbar-h)' }">
    <!-- 顶部 Greeting + 余额大卡 -->
    <section class="hero">
      <div class="hero__greet">
        <div class="hero__name">你好,{{ auth.displayName }} 👋</div>
        <div class="hero__sub">开启今日盘感训练</div>
      </div>
      <div class="balance-card">
        <div class="balance-card__row">
          <span class="balance-card__lbl">训练资金余额</span>
          <span class="balance-card__hint">点击充值 →</span>
        </div>
        <div class="balance-card__amount num">
          ¥ {{ money(auth.wallet.balance) }}
        </div>
        <div class="balance-card__row balance-card__row--mini">
          <div class="balance-card__metric">
            <span>累计消耗</span>
            <span>¥ {{ money(auth.wallet.total_spent) }}</span>
          </div>
          <div class="balance-card__metric">
            <span>累计充值</span>
            <span>¥ {{ money(auth.wallet.total_topup) }}</span>
          </div>
        </div>
        <button class="btn btn--primary btn--block btn--lg" @click="goSetup">
          + 发起新训练
        </button>
      </div>
    </section>

    <!-- 我的训练记录 -->
    <section class="section">
      <div class="section__head">
        <h3 class="section__title">训练记录</h3>
        <van-tabs v-model:active="statusFilter" @change="applyFilter" type="card" shrink>
          <van-tab title="全部" name="all" />
          <van-tab title="进行中" name="active" />
          <van-tab title="已结束" name="finished" />
        </van-tabs>
      </div>
      <ul class="list" v-if="filteredSessions.length">
        <li
          v-for="row in filteredSessions"
          :key="row.id"
          class="session-row"
          @click="goTrade(row)"
        >
          <div class="session-row__head">
            <div class="session-row__name">
              <strong>{{ row.name }}</strong>
              <span class="session-row__code">({{ row.code }})</span>
            </div>
            <span class="tag" :class="row.status === 'active' ? 'tag--success' : ''">
              {{ row.status === 'active' ? '进行中' : '已结束' }}
            </span>
          </div>
          <div class="session-row__metrics">
            <div>
              <span class="muted">区间</span>
              <span>{{ row.start_date?.slice(0,10) }} → {{ row.end_date?.slice(0,10) }}</span>
            </div>
            <div>
              <span class="muted">已揭示</span>
              <span :class="isRevealAhead(row) ? 'up' : ''">
                {{ row.current_date?.slice(0,10) }}
              </span>
            </div>
            <div>
              <span class="muted">资金</span>
              <span>¥ {{ money(row.initial_cash) }}</span>
            </div>
          </div>
        </li>
      </ul>
      <div class="empty" v-else-if="!loading">
        <div class="empty__icon">📋</div>
        <div class="empty__text">还没有训练记录,先去发起一次吧</div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { trainApi } from '@/api/modules'
import { useTrainAuthStore } from '@/stores/trainAuth'
import { money } from '@/utils/trainFee'

const router = useRouter()
const auth = useTrainAuthStore()
const sessions = ref([])
const loading = ref(false)
const statusFilter = ref('all')

const filteredSessions = computed(() => {
  if (statusFilter.value === 'all') return sessions.value
  return sessions.value.filter((x) => x.status === statusFilter.value)
})

function isRevealAhead(row) {
  if (row.status !== 'active') return false
  if (!row.current_date || !row.end_date) return false
  return new Date(row.current_date).getTime() >= new Date(row.end_date).getTime()
}

function applyFilter() {
  /* statusFilter is reactive; computed 会触发重算 */
}

function goSetup() {
  router.push('/setup')
}
function goTrade(row) {
  router.push(`/trade/${row.id}`)
}

async function load() {
  loading.value = true
  try {
    const [me, list, w] = await Promise.all([
      trainApi.me().catch(() => null),
      trainApi.sessions(),
      trainApi.wallet(),
    ])
    if (me && me.username) {
      auth.user = {
        id: me.id,
        username: me.username,
        display_name: me.display_name,
        last_login: me.last_login,
      }
    }
    sessions.value = list?.items || []
    auth.setWallet(w || {})
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.hero { padding: var(--sp-4xl) var(--sp-4xl) 0; }
.hero__greet { padding: 0 var(--sp-2xl); margin-bottom: var(--sp-4xl); }
.hero__name { font-size: 0.40rem; font-weight: 700; color: var(--text-primary); }
.hero__sub { font-size: 0.26rem; color: var(--text-secondary); margin-top: 4px; }

.balance-card {
  background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
  color: #fff;
  border-radius: var(--radius-xl);
  padding: var(--sp-4xl) var(--sp-5xl);
  margin: 0 var(--sp-4xl);
  box-shadow: var(--shadow-md);
}
.balance-card__row {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: var(--sp-3xl);
}
.balance-card__lbl { font-size: 0.26rem; opacity: 0.85; }
.balance-card__hint { font-size: 0.22rem; opacity: 0.7; cursor: pointer; }
.balance-card__amount {
  font-size: 0.64rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  margin-bottom: var(--sp-4xl);
}
.balance-card__row--mini { font-size: 0.24rem; opacity: 0.92; margin-bottom: var(--sp-4xl); }
.balance-card__metric { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; flex: 1; }
.balance-card__metric span:first-child { opacity: 0.78; }
.balance-card .btn {
  background: rgba(255, 255, 255, 0.96);
  color: var(--color-primary);
  font-weight: 600;
}

.section { padding: var(--sp-5xl) var(--sp-4xl) 0; }
.section__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--sp-3xl);
}
.section__title { margin: 0; font-size: 0.32rem; font-weight: 600; }
.section__head :deep(.van-tabs) { width: 4.40rem; }

.session-row {
  background: var(--bg-card);
  padding: var(--sp-3xl) var(--sp-4xl);
  border-bottom: 1px solid var(--border-color-light);
}
.session-row:first-child { border-radius: var(--radius-lg) var(--radius-lg) 0 0; }
.session-row:last-child  { border-radius: 0 0 var(--radius-lg) var(--radius-lg); }
.session-row:active { background: var(--bg-hover); }

.session-row__head {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: var(--sp-3xl);
}
.session-row__name { display: flex; align-items: baseline; gap: var(--sp-lg); }
.session-row__name strong { font-size: 0.32rem; font-weight: 600; }
.session-row__code { font-size: 0.24rem; color: var(--text-secondary); }

.session-row__metrics {
  display: grid;
  grid-template-columns: 1fr 1fr;
  row-gap: var(--sp-2xl);
  column-gap: var(--sp-4xl);
  font-size: 0.24rem;
  color: var(--text-primary);
}
.session-row__metrics .muted { color: var(--text-placeholder); margin-right: 6px; }

.muted { color: var(--text-placeholder); }
</style>
