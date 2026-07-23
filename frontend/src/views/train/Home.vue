<template>
  <div class="home">
    <div class="page-card">
      <div class="hero">
        <h2>欢迎,{{ auth.user?.display_name || auth.user?.username }} 👋</h2>
        <p class="muted">设置训练参数,系统会从已有 A 股数据库中随机抽取一只符合条件的历史股票供你训练盘感。</p>
        <el-button type="primary" size="large" @click="$router.push('/train/setup')">
          <el-icon><Plus /></el-icon>发起一次训练
        </el-button>
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
            <div class="lbl">累计消耗</div>
            <div class="value">¥ {{ money(wallet.total_spent) }}</div>
            <div class="lbl-hint">从余额里扣的训练费</div>
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
.hero { padding: 8px 4px; }
.hero h2 { margin: 0 0 8px; color: #f3f3f3; }
.muted { color: #b4bcd0; margin: 0 0 16px; }
.page-card { background: #fff; padding: 18px 22px; border-radius: 6px; }

.metric-card {
  background: #f6f8fb; border-radius: 6px; padding: 16px;
  display: flex; flex-direction: column;
  border: 1px solid #ebeef5; transition: all 0.15s;
  min-height: 130px;
}
.metric-card:hover { border-color: #c0c4cc; }
.balance-card {
  background: linear-gradient(135deg, #1f3b66 0%, #0f1d33 100%);
  color: #fff;
}
.balance-card * { color: inherit; }
.balance-card .lbl { color: rgba(255, 255, 255, 0.85); font-size: 13px; }
.balance-card .lbl-hint { color: rgba(255, 255, 255, 0.55); font-size: 11px; margin-top: 2px; }
.balance-card .value { color: #67c23a; font-size: 28px; font-weight: bold; margin: 6px 0 8px; line-height: 1.1; }
.balance-card .btn-block { margin-top: auto; }

.btn-cta {
  width: 100%; margin-top: auto;
  background: rgba(255, 255, 255, 0.95); color: #1f3b66;
  border: none; font-weight: bold;
}
.btn-cta:hover { background: #fff; color: #0f1d33; transform: translateY(-1px); }
.btn-cta * { color: inherit !important; }

.muted-card .lbl { font-size: 12px; color: #909399; }
.muted-card .lbl-hint { font-size: 11px; color: #b4bcd0; margin-top: 2px; }
.muted-card .value { font-size: 24px; font-weight: bold; margin: 6px 0 8px; color: #303133; line-height: 1.1; }
.muted-card .meta { color: #606266; }

.btn-block { width: 100%; }

.page-title-row {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px;
}
.page-title-row .page-title { margin: 0; }
.muted-code { color: #909399; margin-left: 4px; font-size: 12px; }
.highlight-date { color: #67c23a; font-weight: bold; }
</style>
