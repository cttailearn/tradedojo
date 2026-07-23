<template>
  <div class="report" v-loading="loading">
    <div class="page-header">
      <h2>训练诊断报告</h2>
      <div class="actions">
        <el-button @click="$router.push(`/train/trade/${sessionId}`)">
          <el-icon><ArrowLeft /></el-icon>返回训练
        </el-button>
      </div>
    </div>

    <!-- 概览卡片 -->
    <div class="page-card" v-if="session">
      <h3 class="page-title">训练概况</h3>
      <div class="report-grid">
        <div class="report-item">
          <span class="ri-label">股票</span>
          <span class="ri-value">{{ session.name }} <small>({{ session.code }})</small></span>
        </div>
        <div class="report-item">
          <span class="ri-label">训练区间</span>
          <span class="ri-value">{{ session.start_date }} — {{ session.end_date }}</span>
        </div>
        <div class="report-item">
          <span class="ri-label">初始资金</span>
          <span class="ri-value">¥ {{ money(session.initial_cash) }}</span>
        </div>
        <div class="report-item" :class="totalPnl >= 0 ? 'positive' : 'negative'">
          <span class="ri-label">总盈亏</span>
          <span class="ri-value">
            {{ totalPnl >= 0 ? '+' : '' }}¥ {{ money(totalPnl) }}
            ({{ (totalPnlPct || 0) >= 0 ? '+' : '' }}{{ (totalPnlPct || 0).toFixed(2) }}%)
          </span>
        </div>
        <div class="report-item">
          <span class="ri-label">训练状态</span>
          <span class="ri-value">
            <el-tag :type="session.status === 'finished' ? 'info' : 'success'" size="small">
              {{ session.status === 'finished' ? '已结束' : '进行中' }}
            </el-tag>
          </span>
        </div>
        <div class="report-item">
          <span class="ri-label">总交易次数</span>
          <span class="ri-value">{{ stats.totalTrades }}</span>
        </div>
      </div>
    </div>

    <!-- 核心指标 -->
    <el-row :gutter="16" v-if="stats.totalTrades > 0">
      <el-col :span="6" v-for="m in metrics" :key="m.label">
        <div class="stat-card">
          <div class="stat-icon" :class="m.color">
            <el-icon><component :is="m.icon" /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-label">{{ m.label }}</div>
            <div class="stat-value">{{ m.value }}</div>
            <div class="stat-sub" v-if="m.sub">{{ m.sub }}</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 空状态 -->
    <div v-if="stats.totalTrades === 0 && !loading" class="page-card">
      <div class="empty-state">
        <div class="icon">📋</div>
        <div class="title">暂无交易记录</div>
        <div class="desc">完成一些买卖操作后再来查看诊断报告</div>
        <el-button type="primary" @click="$router.push(`/train/trade/${sessionId}`)">
          返回训练
        </el-button>
      </div>
    </div>

    <template v-if="stats.totalTrades > 0">
      <!-- 交易分析 -->
      <div class="page-card">
        <h3 class="page-title">交易分析</h3>
        <div class="report-grid report-grid-3">
          <div class="report-item">
            <span class="ri-label">买入次数</span>
            <span class="ri-value">{{ stats.buyCount }}</span>
          </div>
          <div class="report-item">
            <span class="ri-label">卖出次数</span>
            <span class="ri-value">{{ stats.sellCount }}</span>
          </div>
          <div class="report-item" :class="stats.winRate >= 50 ? 'positive' : 'negative'">
            <span class="ri-label">胜率</span>
            <span class="ri-value">{{ stats.winRate.toFixed(1) }}%</span>
          </div>
          <div class="report-item">
            <span class="ri-label">盈利次数</span>
            <span class="ri-value up">{{ stats.winCount }}</span>
          </div>
          <div class="report-item">
            <span class="ri-label">亏损次数</span>
            <span class="ri-value down">{{ stats.lossCount }}</span>
          </div>
          <div class="report-item" :class="stats.profitFactor >= 1 ? 'positive' : 'negative'">
            <span class="ri-label">盈亏比</span>
            <span class="ri-value">{{ stats.profitFactor.toFixed(2) }}</span>
          </div>
          <div class="report-item positive">
            <span class="ri-label">最大单笔盈利</span>
            <span class="ri-value up">+¥ {{ money(stats.maxWin) }}</span>
          </div>
          <div class="report-item negative">
            <span class="ri-label">最大单笔亏损</span>
            <span class="ri-value down">-¥ {{ money(Math.abs(stats.maxLoss)) }}</span>
          </div>
          <div class="report-item">
            <span class="ri-label">总手续费</span>
            <span class="ri-value">¥ {{ money(stats.totalFee) }}</span>
          </div>
        </div>
      </div>

      <!-- 交易明细 -->
      <div class="page-card" v-if="stats.tradeDetails.length">
        <h3 class="page-title">交易明细</h3>
        <el-table :data="stats.tradeDetails" max-height="400" size="small">
          <el-table-column type="index" label="#" width="50" />
          <el-table-column label="日期" width="110">
            <template #default="{ row }">{{ row.date?.slice(0, 10) || '-' }}</template>
          </el-table-column>
          <el-table-column label="方向" width="70">
            <template #default="{ row }">
              <el-tag :type="row.side === 'buy' ? 'danger' : 'success'" size="small">
                {{ row.side === 'buy' ? '买入' : '卖出' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="price" label="价格" align="right" width="90" />
          <el-table-column prop="qty" label="股数" align="right" width="80" />
          <el-table-column prop="amount" label="金额" align="right" width="110">
            <template #default="{ row }">¥ {{ money(row.amount) }}</template>
          </el-table-column>
          <el-table-column prop="fee" label="手续费" align="right" width="90">
            <template #default="{ row }">¥ {{ money(row.fee) }}</template>
          </el-table-column>
          <el-table-column label="实现盈亏" align="right" width="110">
            <template #default="{ row }">
              <span v-if="row.realized_pnl != null" :class="row.realized_pnl >= 0 ? 'up' : 'down'">
                {{ row.realized_pnl >= 0 ? '+' : '' }}¥ {{ money(row.realized_pnl) }}
              </span>
              <span v-else style="color: var(--text-placeholder);">-</span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 行为诊断 -->
      <div class="page-card">
        <h3 class="page-title">行为诊断</h3>
        <div class="diagnosis-list">
          <div
            v-for="(d, i) in diagnosis" :key="i"
            class="diagnosis-item"
            :class="d.level"
          >
            <div class="di-icon">
              <el-icon v-if="d.level === 'good'"><CircleCheck /></el-icon>
              <el-icon v-else-if="d.level === 'warn'"><WarningFilled /></el-icon>
              <el-icon v-else><InfoFilled /></el-icon>
            </div>
            <div class="di-content">
              <div class="di-title">{{ d.title }}</div>
              <div class="di-desc">{{ d.desc }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 改进建议 -->
      <div class="page-card">
        <h3 class="page-title">改进建议</h3>
        <div class="suggestions">
          <div v-for="(s, i) in suggestions" :key="i" class="suggestion-item">
            <span class="si-num">{{ i + 1 }}</span>
            <div>
              <div class="si-title">{{ s.title }}</div>
              <div class="si-desc">{{ s.desc }}</div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { trainApi } from '@/api/modules'

const route = useRoute()
const sessionId = route.params.id
const loading = ref(false)
const session = ref(null)
const trades = ref([])
const equity = ref([])

function money(v) {
  return Number(v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const totalPnl = computed(() => session.value?.total_pnl || 0)
const totalPnlPct = computed(() => session.value?.total_pnl_pct || 0)

// 交易统计
const stats = computed(() => {
  const list = trades.value || []
  const sellTrades = list.filter(t => t.side === 'sell' && t.realized_pnl != null)
  const wins = sellTrades.filter(t => t.realized_pnl > 0)
  const losses = sellTrades.filter(t => t.realized_pnl < 0)

  const totalWin = wins.reduce((a, b) => a + (b.realized_pnl || 0), 0)
  const totalLoss = Math.abs(losses.reduce((a, b) => a + (b.realized_pnl || 0), 0))
  const totalFee = list.reduce((a, b) => a + (b.fee || 0), 0)

  return {
    totalTrades: list.length,
    buyCount: list.filter(t => t.side === 'buy').length,
    sellCount: sellTrades.length,
    winCount: wins.length,
    lossCount: losses.length,
    winRate: sellTrades.length > 0 ? (wins.length / sellTrades.length * 100) : 0,
    maxWin: wins.length > 0 ? Math.max(...wins.map(t => t.realized_pnl || 0)) : 0,
    maxLoss: losses.length > 0 ? Math.min(...losses.map(t => t.realized_pnl || 0)) : 0,
    profitFactor: totalLoss > 0 ? totalWin / totalLoss : (totalWin > 0 ? 999 : 0),
    totalFee,
    tradeDetails: [...list].sort((a, b) => (a.date || '').localeCompare(b.date || '')),
  }
})

// 核心指标卡片
const metrics = computed(() => {
  const s = stats.value
  return [
    {
      label: '胜率',
      value: s.winRate.toFixed(1) + '%',
      color: s.winRate >= 50 ? 'green' : 'red',
      icon: 'TrendCharts',
      sub: `${s.winCount}胜 / ${s.lossCount}负`,
    },
    {
      label: '盈亏比',
      value: s.profitFactor.toFixed(2),
      color: s.profitFactor >= 1.5 ? 'green' : (s.profitFactor >= 1 ? 'orange' : 'red'),
      icon: 'Money',
      sub: s.profitFactor >= 2 ? '优秀' : (s.profitFactor >= 1 ? '一般' : '需改进'),
    },
    {
      label: '总交易',
      value: s.totalTrades,
      color: 'blue',
      icon: 'List',
      sub: `${s.buyCount}买 / ${s.sellCount}卖`,
    },
    {
      label: '总手续费',
      value: '¥ ' + money(s.totalFee),
      color: 'purple',
      icon: 'Coin',
      sub: '含佣金+印花税+过户费',
    },
  ]
})

// 行为诊断
const diagnosis = computed(() => {
  const s = stats.value
  const diag = []

  // 胜率分析
  if (s.sellCount > 0) {
    if (s.winRate >= 60) {
      diag.push({ level: 'good', title: '胜率优秀', desc: `胜率达到 ${s.winRate.toFixed(1)}%，选股和择时能力较强。` })
    } else if (s.winRate >= 40) {
      diag.push({ level: 'info', title: '胜率中等', desc: `胜率 ${s.winRate.toFixed(1)}%，处于正常范围，可尝试提高入场标准。` })
    } else {
      diag.push({ level: 'warn', title: '胜率偏低', desc: `胜率仅 ${s.winRate.toFixed(1)}%，建议优化入场时机，减少追高操作。` })
    }
  }

  // 盈亏比分析
  if (s.sellCount > 0) {
    if (s.profitFactor >= 2) {
      diag.push({ level: 'good', title: '盈亏比优秀', desc: '盈利金额远超亏损金额，风险控制能力强。' })
    } else if (s.profitFactor >= 1) {
      diag.push({ level: 'info', title: '盈亏比一般', desc: '盈亏基本持平，建议设置更严格的止盈止损纪律。' })
    } else {
      diag.push({ level: 'warn', title: '盈亏比不足', desc: '亏损大于盈利，需要严格止损并及时止盈，避免利润回吐。' })
    }
  }

  // 最大回撤
  const md = computeMaxDrawdown()
  if (md > 20) {
    diag.push({ level: 'warn', title: '回撤过大', desc: `最大回撤 ${md.toFixed(1)}%，资金管理过于激进，建议控制单笔仓位。` })
  } else if (md > 10) {
    diag.push({ level: 'info', title: '回撤可控', desc: `最大回撤 ${md.toFixed(1)}%，在可接受范围内。` })
  } else if (s.sellCount > 0) {
    diag.push({ level: 'good', title: '回撤控制良好', desc: `最大回撤 ${md.toFixed(1)}%，资金管理谨慎稳健。` })
  }

  // 交易频率
  if (s.totalTrades > 50) {
    diag.push({ level: 'warn', title: '交易过于频繁', desc: `${s.totalTrades} 次交易，手续费 ¥${money(s.totalFee)}，频繁交易损耗收益。` })
  } else if (s.totalTrades < 5 && s.sellCount > 0) {
    diag.push({ level: 'info', title: '交易量偏少', desc: `仅 ${s.totalTrades} 次交易，样本不足，建议适度增加操作。` })
  }

  if (diag.length === 0) {
    diag.push({ level: 'info', title: '数据不足', desc: '交易次数较少，尚无法进行全面诊断。完成更多交易后再来查看。' })
  }

  return diag
})

// 改进建议
const suggestions = computed(() => {
  const s = stats.value
  const diag = diagnosis.value
  const sugs = []

  if (diag.some(d => d.title.includes('胜率偏低') || d.title.includes('回撤过大'))) {
    sugs.push({
      title: '严格设置止损位',
      desc: '每笔交易入场前设定止损价，建议不超过入场价的 5-8%。止损是保护资金的第一道防线。',
    })
  }

  if (diag.some(d => d.title.includes('交易过于频繁'))) {
    sugs.push({
      title: '减少无意义交易',
      desc: '提高入场标准，只在自己最有把握的时候出手。减少交易频率可以显著降低手续费损耗。',
    })
  }

  if (diag.some(d => d.title.includes('盈亏比'))) {
    sugs.push({
      title: '优化盈亏比',
      desc: '让利润奔跑——盈利时不要急于卖出；截断亏损——亏损达到止损线时果断离场。目标是盈亏比 > 2。',
    })
  }

  if (s.maxLoss < 0 && Math.abs(s.maxLoss) > (session.value?.initial_cash || 100000) * 0.1) {
    sugs.push({
      title: '控制单笔风险',
      desc: `最大单笔亏损达 ¥${money(Math.abs(s.maxLoss))}，超过初始资金的 10%。建议单笔仓位不超过总资金的 20%。`,
    })
  }

  // Always add general advice
  sugs.push({
    title: '坚持记录交易日志',
    desc: '记录每笔交易的入场理由、出场理由和情绪状态。复盘是最好的老师，持续反思才能不断提升。',
  })

  return sugs
})

// 计算最大回撤
function computeMaxDrawdown() {
  const eq = equity.value || []
  if (eq.length === 0) return 0
  let peak = eq[0].total_equity || eq[0].value || eq[0]
  let maxDd = 0
  for (const point of eq) {
    const v = point.total_equity || point.value || point
    if (typeof v !== 'number') continue
    if (v > peak) peak = v
    const dd = (peak - v) / peak * 100
    if (dd > maxDd) maxDd = dd
  }
  return maxDd
}

async function load() {
  loading.value = true
  try {
    const [sess, tradeData, eqData] = await Promise.all([
      trainApi.session(sessionId),
      trainApi.session(sessionId).then(() => {
        // 通过 session 数据获取 trades（如果API支持）
        return []
      }).catch(() => []),
      trainApi.equity(sessionId).catch(() => []),
    ])
    session.value = sess

    // 尝试从 session 获取 trades
    if (sess.trades) {
      trades.value = sess.trades
    }

    // equity curve
    if (Array.isArray(eqData)) {
      equity.value = eqData
    } else if (eqData?.equity) {
      equity.value = eqData.equity
    }
  } catch (e) {
    ElMessage.error('加载报告数据失败: ' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.report-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-lg) var(--space-2xl);
}
.report-grid-3 {
  grid-template-columns: repeat(3, 1fr);
}
.report-item {
  display: flex; flex-direction: column; gap: var(--space-xs);
}
.report-item.positive .ri-value { color: var(--color-up); }
.report-item.negative .ri-value { color: var(--color-down); }
.ri-label {
  font-size: var(--text-xs); color: var(--text-secondary);
  font-weight: var(--font-medium);
}
.ri-value {
  font-size: var(--text-lg); font-weight: var(--font-semibold);
  color: var(--text-primary);
}
.ri-value small { font-size: var(--text-xs); color: var(--text-placeholder); }

.diagnosis-list {
  display: flex; flex-direction: column; gap: var(--space-md);
}
.diagnosis-item {
  display: flex; gap: var(--space-lg);
  padding: var(--space-lg); border-radius: var(--radius-md);
  border: 1px solid var(--border-color-light);
}
.diagnosis-item.good {
  background: var(--color-success-light);
  border-color: var(--color-success);
}
.diagnosis-item.warn {
  background: var(--color-warning-light);
  border-color: var(--color-warning);
}
.diagnosis-item.info {
  background: var(--color-info-light);
  border-color: var(--color-info);
}
.di-icon {
  font-size: var(--text-2xl); flex-shrink: 0;
  display: flex; align-items: flex-start; padding-top: 2px;
}
.diagnosis-item.good .di-icon { color: var(--color-success); }
.diagnosis-item.warn .di-icon { color: var(--color-warning); }
.diagnosis-item.info .di-icon { color: var(--color-info); }
.di-content { flex: 1; }
.di-title {
  font-weight: var(--font-semibold); margin-bottom: var(--space-xs);
  color: var(--text-primary);
}
.di-desc { color: var(--text-secondary); font-size: var(--text-sm); line-height: var(--leading-relaxed); }

.suggestions {
  display: flex; flex-direction: column; gap: var(--space-lg);
}
.suggestion-item {
  display: flex; gap: var(--space-lg);
}
.si-num {
  width: 28px; height: 28px;
  background: var(--color-primary);
  color: #fff; border-radius: var(--radius-full);
  display: flex; align-items: center; justify-content: center;
  font-size: var(--text-sm); font-weight: var(--font-bold);
  flex-shrink: 0;
}
.si-title {
  font-weight: var(--font-semibold); color: var(--text-primary);
  margin-bottom: var(--space-xs);
}
.si-desc {
  color: var(--text-secondary); font-size: var(--text-sm);
  line-height: var(--leading-relaxed);
}
</style>
