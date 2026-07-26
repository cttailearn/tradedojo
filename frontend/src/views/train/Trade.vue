<template>
  <div class="trade" v-loading="loading">
    <!-- 顶部 资金 / 盈亏 -->
    <div class="metric-bar">
      <div class="metric-row metric-row-1">
        <div class="m-block stock">
          <div class="lbl">股票</div>
          <div class="val">{{ session?.name }} <span class="code">{{ session?.code }}</span></div>
          <div class="meta">{{ session?.industry }} · {{ session?.market }}</div>
        </div>
        <div class="m-block profit">
          <div class="lbl">总权益</div>
          <div class="val" :class="(session?.total_pnl || 0) >= 0 ? 'green' : 'red'">
            ¥ {{ money(session?.total_equity) }}
          </div>
          <div class="meta">
            <span :class="(session?.total_pnl || 0) >= 0 ? 'green' : 'red'">
              {{ (session?.total_pnl || 0) >= 0 ? '+' : '' }}{{ money(session?.total_pnl) }}
              ({{ (session?.total_pnl_pct || 0) >= 0 ? '+' : '' }}{{ (session?.total_pnl_pct || 0).toFixed(2) }}%)
            </span>
          </div>
        </div>
        <div class="m-block">
          <div class="lbl">可用资金</div>
          <div class="val">¥ {{ money(session?.cash) }}</div>
          <div class="meta">初始 ¥ {{ money(session?.initial_cash) }}</div>
        </div>
        <div class="m-block">
          <div class="lbl">持仓市值</div>
          <div class="val">¥ {{ money(session?.market_value) }}</div>
        </div>
      </div>

      <div class="metric-row metric-row-2">
        <div class="progress-block">
          <div class="progress-text">
            <span>起点 <b>{{ session?.start_date }}</b></span>
            <span class="progress-current highlight">
              当前 <b>{{ session?.current_date || session?.start_date }}</b>
            </span>
            <span>终点 <b>{{ session?.end_date }}</b></span>
          </div>
          <el-progress
            :percentage="progressPct"
            :stroke-width="10"
            :show-text="false"
            :color="progressColor"
          />
          <div class="progress-hint">
            已揭示 <b>{{ klineBars.length }}</b> 个{{ periodLabel }}
            ({{ weeklyHint }}) · 仅当前日及更早可见
          </div>
        </div>
        <div class="action-block">
          <el-button-group>
            <el-button :disabled="!canAdvance || advancing" :loading="advancing"
                        @click="advance(1)">
              <el-icon><Right /></el-icon>推进 1 天
            </el-button>
            <el-button :disabled="!canAdvance || advancing" :loading="advancing"
                        @click="advance(5)">+5 天</el-button>
            <el-button :disabled="!canAdvance || advancing" :loading="advancing"
                        @click="advance(30)">+30 天</el-button>
          </el-button-group>
          <el-button type="warning" plain size="small"
                    @click="finish" :disabled="session?.status === 'finished'">
            <el-icon><CircleClose /></el-icon>{{ session?.status === 'finished' ? '已结束' : '结束训练' }}
          </el-button>
          <el-button type="info" plain size="small"
                    @click="$router.push(`/train/report/${sessionId}`)">
            <el-icon><Document /></el-icon>诊断报告
          </el-button>
        </div>
      </div>
    </div>

    <!-- 主体:左 K 线,右 资金曲线 + 交易面板 -->
    <el-row :gutter="16" style="margin-top: 16px;">
      <el-col :span="16">
        <div class="page-card">
          <div class="chart-head">
            <div>
              <span class="t">K 线图</span>
              <el-radio-group v-model="period" size="small" style="margin-left: 12px;"
                              @change="loadKline">
                <el-radio-button value="daily">日 K</el-radio-button>
                <el-radio-button value="weekly">周 K</el-radio-button>
                <el-radio-button value="monthly">月 K</el-radio-button>
              </el-radio-group>
              <span class="hint">
                当前价(收盘): ¥ {{ currentPrice.toFixed(2) }}
                <span v-if="pctToday !== null" :class="pctToday >= 0 ? 'red' : 'green'">
                  ({{ pctToday >= 0 ? '+' : '' }}{{ pctToday.toFixed(2) }}%)
                </span>
              </span>
            </div>
          </div>
          <div ref="klineChartEl" class="kline-chart" />
          <div v-if="loadedSession && !klineBars.length" class="chart-empty">
            <el-empty description="所选时间段暂无 K 线数据">
              <template #image>
                <el-icon :size="48" color="#c0c4cc"><WarningFilled /></el-icon>
              </template>
              <div class="empty-hint">
                可能原因:① 训练开始日是节假日 ② 该股票停牌 ③ <b>该股尚未在系统中维护 K 线</b>
                <br />可点击下方按钮一次性补全该股 K 线,或点击"推进 1 天"继续揭示下一个交易日
              </div>
              <el-button type="primary" plain :loading="loadingKlineUpdate"
                @click="triggerKlineUpdate" style="margin-top:8px;">
                <el-icon><Download /></el-icon>立即补全 K线
              </el-button>
            </el-empty>
          </div>
          <!-- 数据不足提示(已有 K线但 MA 画不出) -->
          <el-alert
            v-else-if="klineBars.length && klineBars.length < 60"
            type="warning" :closable="false" show-icon
            style="margin: 6px 0;"
          >
            <template #title>当前 K线数据较少 ({{ klineBars.length }} 根),均线尚未完整</template>
            <div>
              <span style="color:#909399; font-size:12px;">
                MA5 需 ≥5 根 · MA10 需 ≥10 根 · MA20 需 ≥20 根 · MA30 需 ≥30 根 · MA60 需 ≥60 根
              </span>
              <el-button type="primary" size="small" :loading="loadingKlineUpdate"
                @click="triggerKlineUpdate" style="margin-left: 12px;">
                <el-icon><Download /></el-icon>补全该股 K线
              </el-button>
            </div>
          </el-alert>
        </div>

        <div class="page-card" style="margin-top: 16px;">
          <div class="chart-head">
            <h3 class="page-title">资金曲线</h3>
            <span class="hint">含历史初始资金 ¥ {{ money(session?.initial_cash) }}</span>
          </div>
          <div ref="equityChartEl" class="equity-chart" />
        </div>
      </el-col>

      <el-col :span="8">
        <div class="page-card">
          <h3 class="page-title">下单</h3>
          <el-tabs v-model="tradeTab">
            <el-tab-pane label="买入" name="buy">
              <el-form label-position="top">
                <el-form-item label="买入金额 (元)">
                  <el-input-number v-model="buyForm.amount" :min="1000" :step="10000"
                                   style="width: 100%" />
                </el-form-item>
                <el-form-item label="快捷选择 (仓位 / 自定义股数)">
                  <el-radio-group v-model="buyPreset" size="small" @change="applyBuyPreset">
                    <el-radio-button value="cash_quarter">1/4 仓</el-radio-button>
                    <el-radio-button value="cash_half">1/2 仓</el-radio-button>
                    <el-radio-button value="cash_all">全仓</el-radio-button>
                    <el-radio-button value="custom">自定义股</el-radio-button>
                  </el-radio-group>
                  <div v-if="buyPreset === 'custom'" style="margin-top: 8px;">
                    <el-input-number v-model="customBuyShares" :min="100" :step="100"
                                     :max="100000" style="width: 200px;" />
                    <span style="margin-left: 8px; color: #909399; font-size: 12px;">
                      股 (100 整数倍) · 约 ¥ {{ money((customBuyShares || 0) * currentPrice) }} 元
                    </span>
                  </div>
                  <div class="preset-hint">提示:全仓会预留 5% 资金用于手续费;自定义股按 100 整数倍</div>
                </el-form-item>
                <el-form-item label="限价 (可选,默认按收盘价)">
                  <el-input-number v-model="buyForm.price" :min="0.01" :step="0.01"
                                   :precision="2" style="width: 100%" placeholder="不填按收盘价" />
                </el-form-item>
                <el-alert :closable="false" type="info" show-icon>
                  将按 100 股取整,自动扣除 <b>¥ {{ money(estimateFees('buy')) }}</b> 元手续费(估)
                  <div v-if="estimatedBuyQty > 0" class="estimated-qty">
                    约买入 <b>{{ estimatedBuyQty }}</b> 股
                  </div>
                </el-alert>
                <div style="margin-top: 12px;">
                  <el-button type="primary" :loading="trading" :disabled="!canTrade"
                            style="width: 100%;" @click="submit('BUY')">
                    <el-icon><Top /></el-icon>买入 (按收盘价)
                  </el-button>
                </div>
              </el-form>
            </el-tab-pane>
            <el-tab-pane label="卖出" name="sell">
              <el-form label-position="top">
                <el-form-item label="卖出股数 (100 股整数倍)">
                  <el-input-number v-model="sellForm.quantity" :min="100" :step="100"
                                   style="width: 100%" />
                </el-form-item>
                <el-form-item label="快捷选择 (仓位 / 自定义股数)">
                  <el-radio-group v-model="sellPreset" size="small" @change="applySellPreset">
                    <el-radio-button value="eighth">1/8</el-radio-button>
                    <el-radio-button value="quarter">1/4</el-radio-button>
                    <el-radio-button value="third">1/3</el-radio-button>
                    <el-radio-button value="half">1/2</el-radio-button>
                    <el-radio-button value="all">全部</el-radio-button>
                    <el-radio-button value="custom">自定义股</el-radio-button>
                  </el-radio-group>
                  <div v-if="sellPreset === 'custom'" style="margin-top: 8px;">
                    <el-input-number v-model="customSellShares" :min="100" :step="100"
                                     :max="myPositionQty" style="width: 200px;" />
                    <span style="margin-left: 8px; color: #909399; font-size: 12px;">
                      股 (100 整数倍,最大 {{ myPositionQty }})
                    </span>
                  </div>
                </el-form-item>
                <el-form-item label="限价 (可选,默认按收盘价)">
                  <el-input-number v-model="sellForm.price" :min="0.01" :step="0.01"
                                   :precision="2" style="width: 100%" placeholder="不填按收盘价" />
                </el-form-item>
                <el-alert :closable="false" type="warning" show-icon>
                  当前持仓 <b>{{ myPositionQty }}</b> 股,均价 <b>¥ {{ myAvgCost.toFixed(2) }}</b>
                  <div v-if="sellForm.quantity > 0" :class="sellEstimatedPnl >= 0 ? 'estimated-qty green' : 'estimated-qty red'">
                    预计实现盈亏: <b>{{ sellEstimatedPnl >= 0 ? '+' : '' }}{{ money(sellEstimatedPnl) }}</b> 元
                  </div>
                </el-alert>
                <div style="margin-top: 12px;">
                  <el-button type="danger" :loading="trading" :disabled="!canTrade"
                            style="width: 100%;" @click="submit('SELL')">
                    <el-icon><Bottom /></el-icon>卖出
                  </el-button>
                </div>
              </el-form>
            </el-tab-pane>
          </el-tabs>
        </div>

        <div class="page-card" style="margin-top: 16px;">
          <h3 class="page-title">当前持仓</h3>
          <el-table :data="session?.positions || []" size="small" stripe>
            <el-table-column prop="code" label="代码" width="90" />
            <el-table-column prop="quantity" label="股数" align="right" />
            <el-table-column prop="avg_cost" label="成本" align="right">
              <template #default="{ row }">{{ Number(row.avg_cost || 0).toFixed(2) }}</template>
            </el-table-column>
            <el-table-column prop="current_price" label="现价" align="right">
              <template #default="{ row }">
                <span v-if="row.current_price">{{ Number(row.current_price).toFixed(2) }}</span>
                <span v-else class="muted">-</span>
              </template>
            </el-table-column>
            <el-table-column prop="float_pnl" label="浮盈亏" align="right">
              <template #default="{ row }">
                <span :class="(row.float_pnl||0) >= 0 ? 'green' : 'red'">
                  {{ (row.float_pnl||0) >= 0 ? '+' : '' }}{{ money(row.float_pnl) }}
                </span>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!(session?.positions || []).length" description="暂无持仓,试试买点" :image-size="60" />
        </div>

        <div class="page-card" style="margin-top: 16px;">
          <h3 class="page-title">成交记录</h3>
          <el-table :data="session?.recent_orders || []" size="small" stripe
                    :max-height="220">
            <el-table-column prop="trade_date" label="日期" width="100" />
            <el-table-column label="方向" width="56">
              <template #default="{ row }">
                <el-tag :type="row.side === 'BUY' ? 'danger' : 'success'" size="small">
                  {{ row.side === 'BUY' ? '买' : '卖' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="price" label="价" align="right">
              <template #default="{ row }">{{ Number(row.price).toFixed(2) }}</template>
            </el-table-column>
            <el-table-column prop="quantity" label="股" align="right" />
            <el-table-column prop="total_fee" label="费" align="right">
              <template #default="{ row }">{{ Number(row.total_fee || 0).toFixed(2) }}</template>
            </el-table-column>
            <el-table-column prop="realized_pnl" label="实现" align="right">
              <template #default="{ row }">
                <span v-if="row.side === 'SELL'" :class="(row.realized_pnl||0) >= 0 ? 'green' : 'red'">
                  {{ (row.realized_pnl||0) >= 0 ? '+' : '' }}{{ money(row.realized_pnl) }}
                </span>
                <span v-else class="muted">-</span>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!(session?.recent_orders || []).length" description="还没有成交" :image-size="60" />
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as echarts from 'echarts'
import { trainApi, tasksApi } from '@/api/modules'

const route = useRoute()
const router = useRouter()
const id = computed(() => Number(route.params.id))

const session = ref(null)
const klineBars = ref([])
const equity = ref([])
const loadedSession = ref(false)
const loading = ref(false)
const advancing = ref(false)
const trading = ref(false)
const loadingKlineUpdate = ref(false)
const period = ref('daily')
const tradeTab = ref('buy')
const buyPreset = ref('')
const sellPreset = ref('')
const customBuyShares = ref(100)
const customSellShares = ref(100)
const buyForm = reactive({ amount: 100000, price: null })
const sellForm = reactive({ quantity: 100, price: null })

let klineChart = null
let equityChart = null
const klineChartEl = ref(null)
const equityChartEl = ref(null)

const canAdvance = computed(() => session.value?.status === 'active'
  && session.value?.current_date < session.value?.end_date)

const canTrade = computed(() => session.value?.status === 'active'
  && currentPrice.value > 0
  && !!session.value?.current_bar)

const periodLabel = computed(() => ({ daily: '交易日', weekly: '周', monthly: '月' }[period.value]))

const currentPrice = computed(() => {
  if (!klineBars.value.length) return 0
  return Number(klineBars.value[klineBars.value.length - 1].close || 0)
})

const pctToday = computed(() => {
  if (!klineBars.value.length) return null
  const last = klineBars.value[klineBars.value.length - 1]
  return Number(last.pct_change || 0)
})

const myPositionQty = computed(() => {
  if (!session.value?.positions) return 0
  const me = session.value.positions.find((p) => p.code === session.value.code)
  return me?.quantity || 0
})

const myAvgCost = computed(() => {
  if (!session.value?.positions) return 0
  const me = session.value.positions.find((p) => p.code === session.value.code)
  return Number(me?.avg_cost || 0)
})

const estimatedBuyQty = computed(() => {
  if (!currentPrice.value || !buyForm.amount) return 0
  return Math.floor(buyForm.amount / (currentPrice.value * 100)) * 100
})

const sellEstimatedPnl = computed(() => {
  const q = Number(sellForm.quantity) || 0
  if (!q || !myPositionQty.value) return 0
  const ratio = Math.min(q / myPositionQty.value, 1)
  const currentVal = currentPrice.value * q
  const costVal = myAvgCost.value * q
  const feeEst = (currentVal * 0.0003 + currentVal * 0.001 + 5) // 保守估
  return currentVal - costVal - feeEst * ratio * 2
})

const weeklyHint = computed(() => {
  const cur = session.value?.current_date
  const start = session.value?.start_date
  if (!cur || !start) return ''
  return `约 ${Math.max(0, Math.ceil((new Date(cur).getTime() - new Date(start).getTime()) / (7 * 86400000)))} 周`
})

const progressPct = computed(() => {
  const s = session.value?.start_date
  const e = session.value?.end_date
  const c = session.value?.current_date
  if (!s || !e || !c) return 0
  const total = new Date(e).getTime() - new Date(s).getTime()
  if (total <= 0) return 100
  const cur = new Date(c).getTime() - new Date(s).getTime()
  return Math.min(100, Math.max(0, Math.round((cur / total) * 100)))
})

const progressColor = computed(() => {
  const pnl = session.value?.total_pnl || 0
  if (pnl > 0) return '#67c23a'
  if (pnl < 0) return '#f56c6c'
  return '#909399'
})

function money(v) {
  return Number(v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function estimateFees(side) {
  if (!session.value || !session.value.fee_rules) return 0
  const f = session.value.fee_rules
  const price = currentPrice.value
  if (!price) return 0
  const amt = side === 'buy' ? (buyForm.amount || 0) : (sellForm.quantity || 0) * price
  if (!amt) return 0
  const commission = Math.max(amt * f.commission_rate, f.min_commission)
  const stamp = side === 'sell' ? amt * f.stamp_tax : 0
  const transfer = amt * f.transfer_fee
  return commission + stamp + transfer
}

function applyBuyPreset(v) {
  if (!v) return
  const cash = session.value?.cash || 0
  const price = currentPrice.value || 0
  if (v === 'cash_quarter') {
    // 1/4 仓位
    buyForm.amount = Math.floor((cash * 0.25) / 1000) * 1000
  } else if (v === 'cash_half') {
    buyForm.amount = Math.floor((cash * 0.5) / 1000) * 1000
  } else if (v === 'cash_all') {
    // 全仓:留 5% 给手续费与最低限价余量
    buyForm.amount = Math.floor((cash * 0.95) / 1000) * 1000
  } else if (v === 'custom') {
    // 自定义股:按 100 整数倍 → 折算金额(向上取整到 100 元)
    const shares = Math.max(100, Math.round(customBuyShares.value / 100) * 100)
    customBuyShares.value = shares
    buyForm.amount = Math.ceil((shares * price) / 100) * 100
  } else {
    buyForm.amount = Number(v)
  }
}

function applySellPreset(v) {
  if (!v) return
  const qty = myPositionQty.value || 0
  const r100 = (n) => Math.max(100, Math.floor(n / 100) * 100)
  if (v === 'eighth') sellForm.quantity = r100(qty * 0.125)
  else if (v === 'quarter') sellForm.quantity = r100(qty * 0.25)
  else if (v === 'third') sellForm.quantity = r100(qty / 3)
  else if (v === 'half') sellForm.quantity = r100(qty * 0.5)
  else if (v === 'all') sellForm.quantity = qty
  else if (v === 'custom') {
    const shares = Math.max(100, Math.round(customSellShares.value / 100) * 100)
    customSellShares.value = Math.min(shares, qty)
    sellForm.quantity = customSellShares.value
  }
}

// 自定义股数变化时,实时同步到 buyForm.amount / sellForm.quantity
watch([customBuyShares, currentPrice], () => {
  if (buyPreset.value === 'custom') {
    const shares = Math.max(100, Math.round(customBuyShares.value / 100) * 100)
    buyForm.amount = Math.ceil((shares * (currentPrice.value || 0)) / 100) * 100
  }
})
watch([customSellShares, myPositionQty], () => {
  if (sellPreset.value === 'custom') {
    const shares = Math.max(100, Math.round(customSellShares.value / 100) * 100)
    sellForm.quantity = Math.min(shares, myPositionQty.value || 0)
  }
})

async function loadSession() {
  loading.value = true
  try {
    session.value = await trainApi.session(id.value)
    loadedSession.value = true
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function loadKline() {
  try {
    const res = await trainApi.kline(id.value, period.value)
    klineBars.value = res.items || []
    await nextTick()
    renderKline()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function triggerKlineUpdate() {
  const code = session.value?.code
  if (!code) {
    ElMessage.error('缺少股票代码')
    return
  }
  try {
    await ElMessageBox.confirm(
      `将拉取 [${code} ${session.value?.name || ''}] 1 年的日 K线数据(smart 模式只补缺失/过期)。`,
      '补全 K线', { type: 'info' },
    )
  } catch { return }
  loadingKlineUpdate.value = true
  try {
    const r = await tasksApi.trigger({
      task: 'kline_daily',
      params: {
        mode: 'smart', adjust: 'qfq', days_back: 365,
        workers: 4, codes: [code],
      },
    })
    ElMessage.success(
      `已提交 ${code} 的 K线更新任务,任务ID: ${r.task_id || '-'},完成后会自动刷新`,
    )
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loadingKlineUpdate.value = false
  }
}

async function loadEquity() {
  try {
    const res = await trainApi.equity(id.value)
    equity.value = res.items || []
    await nextTick()
    renderEquity()
  } catch {}
}

function renderKline() {
  if (!klineChart) return
  const bars = klineBars.value
  if (!bars.length) {
    klineChart.clear()
    return
  }

  const dates = bars.map((b) => b.trade_date)
  const ohlc = bars.map((b) => [b.open, b.close, b.low, b.high])

  // 成交量(A股红涨绿跌)
  const volumes = bars.map((b) => ({
    value: b.volume,
    itemStyle: {
      color: b.close >= b.open ? '#ef232a' : '#14b066',
      opacity: 0.85,
    },
  }))

  // 5 条均线 MA5 / MA10 / MA20 / MA30 / MA60
  const closes = bars.map((b) => Number(b.close))
  const calcMA = (n) =>
    closes.map((_, i) => {
      if (i < n - 1) return '-'
      let s = 0
      for (let k = i - n + 1; k <= i; k++) s += closes[k]
      return +(s / n).toFixed(2)
    })
  const ma5  = calcMA(5)
  const ma10 = calcMA(10)
  const ma20 = calcMA(20)
  const ma30 = calcMA(30)
  const ma60 = calcMA(60)

  // 最新价标牌
  const lastBar = bars[bars.length - 1]
  const lastClose = Number(lastBar.close)
  const lastDate = lastBar.trade_date
  const lastUp = lastBar.close >= lastBar.open

  // 训练起点垂直虚线
  const startDate = session.value?.start_date
  const startMark = (startDate && dates.includes(startDate))
    ? [{ xAxis: startDate, name: '训练起点' }]
    : []

  // MA 值格式化辅助
  const fmtMA = (v) => (v === '-' || v == null ? '-' : Number(v).toFixed(2))

  klineChart.setOption({
    backgroundColor: '#0a0e1a',
    animation: false,
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'cross',
        crossStyle: { color: '#aaa', type: 'dashed' },
        lineStyle: { color: '#aaa', type: 'dashed' },
      },
      backgroundColor: 'rgba(20, 30, 50, 0.95)',
      borderColor: '#444',
      textStyle: { color: '#e0e0e0', fontSize: 12 },
      padding: [8, 12],
      formatter: (params) => {
        const k = params.find((p) => p.seriesType === 'candlestick')
        if (!k) return ''
        const idx = k.dataIndex
        const bar = bars[idx]
        const chg = bar.close - bar.open
        const chgPct = bar.open ? ((chg / bar.open) * 100).toFixed(2) : '0.00'
        const chgColor = chg >= 0 ? '#ef232a' : '#14b066'
        const arrow = chg >= 0 ? '▲' : '▼'
        return `<div style="line-height:1.7;">
          <div style="font-weight:bold; margin-bottom:6px; color:#fff; font-size:13px;">
            ${bar.trade_date} <span style="color:${chgColor}; font-size:11px;">${arrow}</span>
          </div>
          <div><span style="color:#888;">开</span> <b style="color:#fff;">${bar.open}</b>
            &nbsp;<span style="color:#888;">收</span> <b style="color:${chgColor};">${bar.close}</b></div>
          <div><span style="color:#888;">高</span> <b style="color:#ef232a;">${bar.high}</b>
            &nbsp;<span style="color:#888;">低</span> <b style="color:#14b066;">${bar.low}</b></div>
          <div><span style="color:#888;">涨跌</span> <b style="color:${chgColor};">
            ${chg >= 0 ? '+' : ''}${chg.toFixed(2)} (${chg >= 0 ? '+' : ''}${chgPct}%)</b></div>
          <div><span style="color:#888;">成交量</span> <b style="color:#fff;">${(bar.volume / 10000).toFixed(1)}万手</b>
            &nbsp;<span style="color:#888;">换手</span> <b style="color:#fff;">${bar.turnover_rate || 0}%</b></div>
          <div style="border-top:1px solid #444; margin-top:4px; padding-top:4px; font-size:11px;">
            <span style="color:#ff9800;">MA5</span> <span style="color:#fff;">${fmtMA(ma5[idx])}</span> &nbsp;
            <span style="color:#ff5722;">MA10</span> <span style="color:#fff;">${fmtMA(ma10[idx])}</span> &nbsp;
            <span style="color:#2196f3;">MA20</span> <span style="color:#fff;">${fmtMA(ma20[idx])}</span>
          </div>
          <div style="font-size:11px;">
            <span style="color:#9c27b0;">MA30</span> <span style="color:#fff;">${fmtMA(ma30[idx])}</span> &nbsp;
            <span style="color:#ffc107;">MA60</span> <span style="color:#fff;">${fmtMA(ma60[idx])}</span>
          </div>
        </div>`
      },
    },
    legend: {
      data: ['K线', 'MA5', 'MA10', 'MA20', 'MA30', 'MA60'],
      top: 4, left: 'center',
      textStyle: { color: '#ccc', fontSize: 11 },
      itemWidth: 12, itemHeight: 8,
      itemGap: 14,
    },
    grid: [
      { left: 50, right: 60, top: 30, height: '60%' },
      { left: 50, right: 60, top: '74%', height: '18%' },
    ],
    xAxis: [
      {
        type: 'category', data: dates, scale: true, boundaryGap: false,
        axisLine: { lineStyle: { color: '#555' } },
        axisLabel: { show: false },
        splitLine: { show: false },
        axisTick: { show: false },
      },
      {
        type: 'category', data: dates, gridIndex: 1,
        axisLine: { lineStyle: { color: '#555' } },
        axisTick: { show: false },
        axisLabel: {
          color: '#aaa', fontSize: 10,
          formatter: (val) => {
            // 月初显示完整 MM-DD,平时只显示 DD
            try {
              const d = new Date(val)
              if (d.getDate() <= 3) return val.slice(5)
            } catch {}
            return val.slice(8)
          },
        },
      },
    ],
    yAxis: [
      {
        scale: true,
        position: 'right',
        axisLine: { lineStyle: { color: '#555' } },
        axisLabel: { color: '#aaa', fontSize: 10 },
        splitLine: { lineStyle: { color: '#1f2937', type: 'dashed' } },
      },
      {
        scale: true, gridIndex: 1, position: 'right',
        axisLine: { lineStyle: { color: '#555' } },
        axisLabel: {
          color: '#aaa', fontSize: 10,
          formatter: (v) => v >= 10000 ? `${(v / 10000).toFixed(0)}万` : v,
        },
        splitNumber: 2, splitLine: { show: false },
      },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1] },
      {
        show: true, xAxisIndex: [0, 1], type: 'slider',
        bottom: 4, height: 18,
        start: 0, end: 100,           // 默认全量显示(旧版 start:60 end:100 导致只看到 1-2 根)
        backgroundColor: 'rgba(40, 50, 80, 0.5)',
        borderColor: '#444',
        fillerColor: 'rgba(80, 120, 220, 0.4)',
        handleStyle: { color: '#888', borderColor: '#aaa' },
        moveHandleStyle: { color: '#666' },
        textStyle: { color: '#aaa', fontSize: 10 },
        showDetail: false,
      },
    ],
    series: [
      {
        name: 'K线', type: 'candlestick', data: ohlc,
        itemStyle: {
          color: '#ef232a',        // 涨红
          color0: '#14b066',       // 跌绿
          borderColor: '#ef232a',
          borderColor0: '#14b066',
        },
        markLine: {
          symbol: 'none',
          silent: true,
          label: {
            show: true, position: 'end', color: '#fbbf24',
            formatter: '训练起点', fontSize: 10,
            backgroundColor: 'rgba(251, 191, 36, 0.18)',
            padding: [2, 4],
          },
          lineStyle: { color: '#fbbf24', type: 'dashed', width: 1 },
          data: startMark,
        },
        markPoint: {
          symbol: 'pin',
          symbolSize: 40,
          symbolOffset: [0, -20],
          data: [{
            name: '最新价',
            coord: [lastDate, lastClose],
            value: lastClose.toFixed(2),
            itemStyle: { color: lastUp ? '#ef232a' : '#14b066' },
            label: { color: '#fff', fontSize: 10, fontWeight: 'bold' },
          }],
        },
      },
      { name: 'MA5',  type: 'line', data: ma5,  smooth: true, lineStyle: { width: 1, color: '#ff9800' }, showSymbol: false },
      { name: 'MA10', type: 'line', data: ma10, smooth: true, lineStyle: { width: 1, color: '#ff5722' }, showSymbol: false },
      { name: 'MA20', type: 'line', data: ma20, smooth: true, lineStyle: { width: 1, color: '#2196f3' }, showSymbol: false },
      { name: 'MA30', type: 'line', data: ma30, smooth: true, lineStyle: { width: 1, color: '#9c27b0' }, showSymbol: false },
      { name: 'MA60', type: 'line', data: ma60, smooth: true, lineStyle: { width: 1, color: '#ffc107' }, showSymbol: false },
      { name: '成交量', type: 'bar', data: volumes, xAxisIndex: 1, yAxisIndex: 1 },
    ],
  }, true)
}

function renderEquity() {
  if (!equityChart) return
  const data = equity.value
  if (!data.length) { equityChart.clear(); return }
  const dates = data.map((d) => d.trade_date)
  const equityArr = data.map((d) => d.total_equity)
  const cashArr = data.map((d) => d.cash)
  equityChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['总权益', '可用资金'], top: 0 },
    grid: { left: 50, right: 20, top: 30, bottom: 30 },
    xAxis: { type: 'category', data: dates },
    yAxis: { type: 'value', scale: true },
    series: [
      {
        name: '总权益', type: 'line', data: equityArr, smooth: true,
        lineStyle: { color: '#409EFF', width: 2 },
        areaStyle: { color: 'rgba(64,158,255,.15)' },
      },
      {
        name: '可用资金', type: 'line', data: cashArr, smooth: true,
        lineStyle: { color: '#e6a23c', width: 1, type: 'dashed' },
      },
    ],
  }, true)
}

async function advance(days) {
  advancing.value = true
  try {
    session.value = await trainApi.advance(id.value, days)
    await loadKline()
    await loadEquity()
    if (session.value?.current_date >= session.value?.end_date) {
      ElMessage.info('已到达训练终点,无法再推进')
    }
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    advancing.value = false
  }
}

async function submit(side) {
  if (side === 'BUY') {
    if (!buyForm.amount || buyForm.amount < 1000) {
      return ElMessage.warning('请输入有效买入金额')
    }
    try {
      await ElMessageBox.confirm(
        `买入约 <b>${estimatedBuyQty.value}</b> 股 @ ¥ ${currentPrice.value.toFixed(2)},扣手续费 ¥ ${money(estimateFees('buy'))} 元,确认?`,
        '买入确认',
        { confirmButtonText: '确定买入', cancelButtonText: '取消', dangerouslyUseHTMLString: true }
      )
    } catch { return }
  } else {
    if (!sellForm.quantity || sellForm.quantity < 100 || sellForm.quantity > myPositionQty.value) {
      return ElMessage.warning(`请填有效卖出股数 (最多 ${myPositionQty.value})`)
    }
    try {
      await ElMessageBox.confirm(
        `卖出 <b>${sellForm.quantity}</b> 股 @ ¥ ${currentPrice.value.toFixed(2)},预计实现盈亏 <b style="color:${sellEstimatedPnl.value >= 0 ? '#67c23a' : '#f56c6c'}">${sellEstimatedPnl.value >= 0 ? '+' : ''}${money(sellEstimatedPnl.value)}</b> 元,确认?`,
        '卖出确认',
        { confirmButtonText: '确定卖出', cancelButtonText: '取消', dangerouslyUseHTMLString: true }
      )
    } catch { return }
  }
  trading.value = true
  try {
    const payload = side === 'BUY'
      ? { side: 'BUY', amount: buyForm.amount, price: buyForm.price || undefined }
      : { side: 'SELL', quantity: sellForm.quantity, price: sellForm.price || undefined }
    session.value = await trainApi.trade(id.value, payload)
    ElMessage.success(`${side === 'BUY' ? '买入' : '卖出'}成功`)
    buyPreset.value = ''
    sellPreset.value = ''
    await loadKline()
    await loadEquity()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    trading.value = false
  }
}

function onKeydown(e) {
  // 避免在输入框内误触发
  const tag = (e.target?.tagName || '').toUpperCase()
  if (tag === 'INPUT' || tag === 'TEXTAREA' || e.target?.isContentEditable) return
  if (!session.value || session.value.status !== 'active') return
  if (e.key === 'ArrowRight') {
    e.preventDefault(); advance(1)
  } else if (e.key === ' ') {
    e.preventDefault(); advance(5)
  } else if (e.key === 'Enter') {
    e.preventDefault(); advance(30)
  }
}

async function finish() {
  if (session.value?.status === 'finished') return
  try {
    await ElMessageBox.confirm('结束训练后将无法继续下单,确定?', '提示', { type: 'warning' })
  } catch { return }
  try {
    session.value = await trainApi.finish(id.value)
    ElMessage.success('已结束训练')
  } catch (e) {
    ElMessage.error(e.message)
  }
}

function resize() {
  klineChart && klineChart.resize()
  equityChart && equityChart.resize()
}

onMounted(async () => {
  klineChart = echarts.init(klineChartEl.value)
  equityChart = echarts.init(equityChartEl.value)
  window.addEventListener('resize', resize)
  window.addEventListener('keydown', onKeydown)
  await loadSession()
  await Promise.all([loadKline(), loadEquity()])
})

onUnmounted(() => {
  window.removeEventListener('resize', resize)
  window.removeEventListener('keydown', onKeydown)
  klineChart && klineChart.dispose()
  equityChart && equityChart.dispose()
})

watch(() => session.value?.current_date, async () => {
  await loadKline()
  await loadEquity()
})
</script>

<style scoped>
.trade { padding: 0 4px; }
.metric-bar {
  background: #fff; padding: 14px 18px;
  border-radius: 6px;
  box-shadow: 0 1px 4px rgba(0,0,0,.06);
}
.metric-row { display: flex; gap: 12px; align-items: stretch; flex-wrap: wrap; }
.metric-row-1 { padding-bottom: 12px; border-bottom: 1px dashed #ebeef5; margin-bottom: 12px; }
.metric-row-2 { align-items: center; }
.m-block { padding: 0 12px; min-width: 130px; border-right: 1px dashed #ebeef5;
          display: flex; flex-direction: column; justify-content: center; }
.m-block:last-child { border-right: none; }
.m-block.highlight { background: #f0f9eb; border-radius: 4px; }
.m-block .lbl { font-size: 12px; color: #909399; }
.m-block .val { font-size: 18px; font-weight: bold; margin-top: 2px;
                line-height: 1.2; color: #303133; }
.m-block .val.val-sm { font-size: 15px; }
.m-block .val .code { font-size: 12px; color: #909399; font-weight: normal; margin-left: 4px; }
.m-block .val.green { color: #67c23a; }
.m-block .val.red { color: #f56c6c; }
.m-block .meta { font-size: 12px; color: #909399; }
.m-block .meta .green { color: #67c23a; }
.m-block .meta .red { color: #f56c6c; }
.m-block.profit { min-width: 180px; }
.m-block.profit .val { font-size: 22px; }
.m-block.stock { min-width: 180px; }
.finish-btn { margin-left: 8px; }

/* 进度条行 */
.progress-block { flex: 1; min-width: 320px; padding: 0 12px; }
.progress-text { display: flex; justify-content: space-between;
                 font-size: 12px; color: #909399; margin-bottom: 4px; }
.progress-text b { color: #303133; }
.progress-current.highlight { background: #ecf5ff; color: #409eff;
                               padding: 2px 8px; border-radius: 10px; }
.progress-hint { font-size: 12px; color: #909399; margin-top: 4px; }
.progress-hint b { color: #303133; }

/* 操作行 */
.action-block { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

.page-card { background: #fff; padding: 12px 16px; border-radius: 6px;
             box-shadow: 0 1px 4px rgba(0,0,0,.06); }
.page-card h3 { margin: 0 0 8px; }
.chart-head { display: flex; align-items: center; justify-content: space-between;
              margin-bottom: 8px; }
.chart-head .t { font-size: 14px; color: #303133; font-weight: bold; }
.chart-head .hint { font-size: 12px; color: #909399; }
.kline-chart {
  width: 100%;
  height: 460px;
  background: #0a0e1a;
  border-radius: 6px;
  padding: 4px 0;
  box-shadow: inset 0 0 12px rgba(0,0,0,.5);
}
.equity-chart { width: 100%; height: 220px; }
.chart-empty { padding: 60px 0; text-align: center; }
.empty-hint { font-size: 12px; color: #909399; margin-top: 8px; line-height: 1.8; }
.green { color: #67c23a; }
.red { color: #f56c6c; }
.muted { color: #b4bcd0; }
.estimated-qty { margin-top: 4px; font-size: 12px; color: #606266; }
.preset-hint { font-size: 11px; color: #909399; margin-top: 4px; }
</style>
