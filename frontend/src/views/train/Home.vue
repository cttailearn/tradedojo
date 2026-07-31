<template>
  <div class="home">
    <div class="page-card">
      <div class="hero">
        <h2>欢迎,{{ auth.user?.display_name || auth.user?.username }} 👋</h2>
        <p class="muted">设置训练参数,系统会从已有 A 股数据库中随机抽取一只符合条件的历史股票供你训练盘感。</p>
        <el-button type="primary" size="large" @click="$router.push('/train/setup')">
          <el-icon><Plus /></el-icon>发起一次训练
        </el-button>
        <!-- 2026-07-31 P1-7: 快捷入口 -->
        <div v-if="lastFinishedSession" class="hero-shortcuts">
          <span class="hint">上次训练:</span>
          <strong>{{ lastFinishedSession.name }} ({{ lastFinishedSession.code }})</strong>
          <span :class="lastFinishedSession.total_pnl >= 0 ? 'green' : 'red'">
            {{ lastFinishedSession.total_pnl >= 0 ? '+' : '' }}¥{{ money(lastFinishedSession.total_pnl) }}
          </span>
          <el-button size="small" type="primary" plain @click="$router.push(`/train/report/${lastFinishedSession.id}`)">
            <el-icon><Document /></el-icon>查看报告
          </el-button>
          <el-button size="small" @click="quickRestart">
            <el-icon><RefreshRight /></el-icon>再来一局
          </el-button>
        </div>
      </div>

      <el-row :gutter="16" style="margin-top: 24px;">
        <el-col :span="6">
          <div class="metric-card balance-card">
            <div class="lbl">训练资金余额</div>
            <div class="value">¥ {{ money(wallet.balance) }}</div>
            <el-button size="small" class="btn-cta" @click="$router.push('/train/wallet')">
              <el-icon><Wallet /></el-icon>充值兑换码
            </el-button>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="metric-card muted-card">
            <div class="lbl">累计交易消耗</div>
            <div class="value">¥ {{ money(wallet.total_spent) }}</div>
            <div class="lbl-hint">买入手续费/印花税/过户费合计</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="metric-card muted-card">
            <div class="lbl">累计充值</div>
            <div class="value">¥ {{ money(wallet.total_topup) }}</div>
            <div class="lbl-hint">通过兑换码充值</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="metric-card muted-card">
            <div class="lbl">活跃训练</div>
            <div class="value">{{ activeCount }}</div>
            <div class="lbl-hint">共 {{ sessions.length }} 条记录</div>
          </div>
        </el-col>
      </el-row>
    </div>

    <div class="page-card">
      <div class="page-title-row">
        <h3 class="page-title">我的训练记录</h3>
        <el-radio-group v-model="statusFilter" size="small" @change="applyFilter">
          <el-radio-button value="all">全部</el-radio-button>
          <el-radio-button value="active">进行中</el-radio-button>
          <el-radio-button value="finished">已结束</el-radio-button>
        </el-radio-group>
      </div>
      <el-table :data="filteredSessions" stripe v-loading="loading" empty-text="还没有训练记录,先去发起一次吧">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column label="股票" min-width="180">
          <template #default="{ row }">
            <strong>{{ row.name }}</strong>
            <span class="muted-code">({{ row.code }})</span>
          </template>
        </el-table-column>
        <el-table-column prop="start_date" label="训练开始" width="120">
          <template #default="{ row }">{{ formatDate(row.start_date) }}</template>
        </el-table-column>
        <el-table-column prop="end_date" label="数据终点" width="120">
          <template #default="{ row }">{{ formatDate(row.end_date) }}</template>
        </el-table-column>
        <el-table-column prop="current_date" label="已揭示到" width="120">
          <template #default="{ row }">
            <span :class="isRevealAhead(row) ? 'highlight-date' : ''">
              {{ formatDate(row.current_date) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="initial_cash" label="初始资金" align="right" width="120">
          <template #default="{ row }">¥ {{ money(row.initial_cash) }}</template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">
              {{ row.status === 'active' ? '进行中' : '已结束' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" @click="goTrade(row)">
              {{ row.status === 'active' ? '继续' : '查看' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { trainApi } from '@/api/modules'
import { useTrainAuthStore } from '@/stores/trainAuth'

const router = useRouter()
const auth = useTrainAuthStore()
const sessions = ref([])
const wallet = ref({ balance: 0, total_spent: 0, total_topup: 0 })
const loading = ref(false)
const statusFilter = ref('all')

const activeCount = computed(() => sessions.value.filter((x) => x.status === 'active').length)

// 2026-07-31 P1-7: 上次训练记录
const lastFinishedSession = computed(() => {
  const fin = sessions.value.filter((x) => x.status === 'finished')
    .sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0))
  return fin[0] || null
})
// 2026-07-31 P1-7: 上次训练设置
const lastSetup = ref(null)
async function quickRestart() {
  // 复制上次训练设置(如果有)
  if (lastSetup.value) {
    sessionStorage.setItem('train_quick_setup', JSON.stringify(lastSetup.value))
  }
  router.push('/train/setup')
}

const filteredSessions = computed(() => {
  if (statusFilter.value === 'all') return sessions.value
  return sessions.value.filter((x) => x.status === statusFilter.value)
})

function money(v) {
  return Number(v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatDate(s) {
  if (!s) return '-'
  return String(s).slice(0, 10)
}

function isRevealAhead(row) {
  if (row.status !== 'active') return false
  if (!row.current_date || !row.end_date) return false
  // 显示已揭示到接近数据终点的提示
  const cur = new Date(row.current_date).getTime()
  const end = new Date(row.end_date).getTime()
  return cur >= end
}

async function load() {
  loading.value = true
  try {
    const [list, w] = await Promise.all([
      trainApi.sessions(),
      trainApi.wallet(),
    ])
    sessions.value = list?.items || []
    wallet.value = w || {}
    // 2026-07-31 P1-7: 拉上次训练设置给 quickRestart 用
    if (lastFinishedSession.value) {
      try {
        const stats = await trainApi.sessionStats(lastFinishedSession.value.id)
        lastSetup.value = stats?.session || null
      } catch {}
    }
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

function goTrade(row) {
  router.push(`/train/trade/${row.id}`)
}

function applyFilter() {
  /* statusFilter is reactive; computed handles filter */
}

onMounted(load)
</script>

<style scoped>
.hero { padding: var(--space-md) 0; }
.hero h2 {
  margin: 0 0 var(--space-sm);
  color: var(--text-primary);
  font-size: var(--text-3xl);
  font-weight: var(--font-bold);
}
.muted { color: var(--text-secondary); margin: 0 0 var(--space-lg); }
/* 2026-07-31 P1-7: 快捷入口 */
.hero-shortcuts {
  margin-top: 16px;
  padding: 12px 16px;
  background: #f0f5ff;
  border-radius: 6px;
  display: flex; align-items: center; gap: 12px;
  flex-wrap: wrap;
}
.hero-shortcuts .hint { color: #909399; font-size: 13px; }
.hero-shortcuts strong { color: #303133; }
.hero-shortcuts .green { color: #67c23a; font-weight: 600; }
.hero-shortcuts .red { color: #f56c6c; font-weight: 600; }
.page-card {
  background: var(--bg-card);
  padding: var(--space-2xl);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-color-light);
  box-shadow: var(--shadow-xs);
  margin-bottom: var(--space-lg);
}

.metric-card {
  background: var(--bg-card);
  border-radius: var(--radius-md);
  padding: var(--space-xl);
  display: flex; flex-direction: column;
  border: 1px solid var(--border-color-light);
  transition: all var(--transition-fast);
  min-height: 130px;
  box-shadow: var(--shadow-xs);
}
.metric-card:hover { border-color: var(--border-color-dark); box-shadow: var(--shadow-sm); }

/* 余额卡:用浅渐变 + 左侧色条,保留重点但不与全局风格割裂 */
.balance-card {
  background: linear-gradient(135deg, #f0f5ff 0%, #e6efff 100%);
  border-left: 4px solid var(--color-primary);
}
.balance-card .lbl { font-size: var(--text-sm); color: var(--text-secondary); }
.balance-card .value { color: var(--color-primary); font-size: var(--text-4xl);
  font-weight: var(--font-bold); margin: var(--space-sm) 0 var(--space-md); line-height: 1.1; }

.muted-card .lbl { font-size: var(--text-xs); color: var(--text-secondary); }
.muted-card .lbl-hint { font-size: var(--text-xs); color: var(--text-placeholder); margin-top: var(--space-xs); }
.muted-card .value { font-size: var(--text-3xl); font-weight: var(--font-bold); margin: var(--space-sm) 0 var(--space-md); color: var(--text-primary); line-height: 1.1; }

.btn-cta {
  width: 100%; margin-top: auto;
  background: var(--color-primary); color: #fff;
  border: none; font-weight: var(--font-semibold);
}
.btn-cta:hover { background: var(--color-primary-dark); transform: translateY(-1px); }

.btn-block { width: 100%; }

.page-title-row {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: var(--space-lg);
}
.page-title-row .page-title { margin: 0; }
.muted-code { color: var(--text-placeholder); margin-left: var(--space-xs); font-size: var(--text-xs); }
.highlight-date { color: var(--color-success); font-weight: var(--font-semibold); }
</style>
