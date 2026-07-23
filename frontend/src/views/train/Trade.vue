<template>
  <div class="trade" v-loading="loading">
    <!-- 顶部 资金 / 盈亏 -->
    <div class="metric-bar">
      <div class="m-block">
        <div class="lbl">股票</div>
        <div class="val">{{ session?.name }} <span class="code">{{ session?.code }}</span></div>
        <div class="meta">{{ session?.industry }} · {{ session?.market }}</div>
      </div>
      <div class="m-block">
        <div class="lbl">训练起点</div>
        <div class="val val-sm">{{ session?.start_date }}</div>
        <div class="meta">数据至 {{ session?.end_date }}</div>
      </div>
      <div class="m-block highlight">
        <div class="lbl">当前日期</div>
        <div class="val">{{ session?.current_date || session?.start_date }}</div>
        <div class="meta">仅此日及更早可见</div>
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
      <div class="m-block">
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
      <div class="m-block actions">
        <el-button-group vertical>
          <el-button :disabled="!canAdvance || advancing" :loading="advancing"
                      @click="advance(1)">
            <el-icon><Right /></el-icon>推进 1 天
          </el-button>
          <el-button :disabled="!canAdvance || advancing" :loading="advancing"
                      @click="advance(5)">
            +5 天
          </el-button>
          <el-button :disabled="!canAdvance || advancing" :loading="advancing"
                      @click="advance(30)">
            +30 天
          </el-button>
        </el-button-group>
        <el-button type="warning" plain size="small" class="finish-btn"
                  @click="finish" :disabled="session?.status === 'finished'">
          <el-icon><CircleClose /></el-icon>{{ session?.status === 'finished' ? '已结束' : '结束训练' }}
        </el-button>
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
                <span v-if="pctToday !== null" :class="pctToday >= 0 ? 'green' : 'red'">
                  ({{ pctToday >= 0 ? '+' : '' }}{{ pctToday.toFixed(2) }}%)
                </span>
              </span>
            </div>
            <div>
              <span class="hint">已揭示 <b>{{ klineBars.length }}</b> 个{{ periodLabel }} ({{ weeklyHint }})</span>
            </div>
          </div>
          <div ref="klineChart" class="kline-chart" />
        </div>

        <div class="page-card" style="margin-top: 16px;">
          <div class="chart-head">
            <h3 class="page-title">资金曲线</h3>
            <span class="hint">含历史初始资金 ¥ {{ money(session?.initial_cash) }}</span>
          </div>
          <div ref="equityChart" class="equity-chart" />
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
                <el-form-item label="快捷选择">
                  <el-radio-group v-model="buyPreset" size="small" @change="applyBuyPreset">
                    <el-radio-button value="50000">5万</el-radio-button>
                    <el-radio-button value="100000">10万</el-radio-button>
                    <el-radio-button value="200000">20万</el-radio-button>
                    <el-radio-button value="cash_half">半仓</el-radio-button>
                    <el-radio-button value="cash_all">全仓</el-radio-button>
                  </el-radio-group>
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
                <el-form-item label="快捷选择">
                  <el-radio-group v-model="sellPreset" size="small" @change="applySellPreset">
                    <el-radio-button value="quarter">1/4</el-radio-button>
                    <el-radio-button value="half">1/2</el-radio-button>
                    <el-radio-button value="all">全部</el-radio-button>
                  </el-radio-group>
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
import { trainApi } from '@/api/modules'

const route = useRoute()
const router = useRouter()
const id = computed(() => Number(route.params.id))

const session = ref(null)
const klineBars = ref([])
const equity = ref([])
const loading = ref(false)
const advancing = ref(false)
const trading = ref(false)
const period = ref('daily')
const tradeTab = ref('buy')
const buyPreset = ref('')
const sellPreset = ref('')
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
  if (v === 'cash_half') {
    buyForm.amount = Math.floor((session.value?.cash || 0) / 2 / 1000) * 1000
  } else if (v === 'cash_all') {
    buyForm.amount = Math.floor(((session.value?.cash || 0) * 0.95) / 1000) * 1000
  } else {
    buyForm.amount = Number(v)
  }
}

function applySellPreset(v) {
  if (!v) return
  if (v === 'quarter') sellForm.quantity = Math.max(100, Math.floor(myPositionQty.value * 0.25 / 100) * 100)
  else if (v === 'half') sellForm.quantity = Math.max(100, Math.floor(myPositionQty.value * 0.5 / 100) * 100)
  else if (v === 'all') sellForm.quantity = myPositionQty.value
}

async function loadSession() {
  loading.value = true
  try {
    session.value = await trainApi.session(id.value)
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
  const volumes = bars.map((b) => ({
    value: b.volume,
    itemStyle: { color: b.close >= b.open ? '#ef4f4f' : '#14b066' },
  }))

  klineChart.setOption({
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'cross' },
      formatter: (params) => {
        const k = params.find((p) => p.seriesType === 'candlestick')
        if (!k) return ''
        const idx = k.dataIndex
        const bar = bars[idx]
        const chg = bar.close >= bar.open
        return `<div style="font-size:12px;">
          <b>${bar.trade_date}</b> ${chg ? '↑' : '↓'}<br/>
          开 ${bar.open} 收 ${bar.close}<br/>
          高 ${bar.high} 低 ${bar.low}<br/>
          量 ${(bar.volume / 10000).toFixed(1)}万手<br/>
          换手 ${bar.turnover_rate || 0}%
        </div>`
      },
    },
    grid: [
      { left: 50, right: 20, top: 20, height: '65%' },
      { left: 50, right: 20, top: '78%', height: '16%' },
    ],
    xAxis: [
      { type: 'category', data: dates, scale: true, boundaryGap: false,
        axisLabel: { show: false }, axisLine: { onZero: false } },
      { type: 'category', data: dates, gridIndex: 1, axisLabel: { show: false } },
    ],
    yAxis: [
      { scale: true, splitArea: { show: true },
        axisLabel: { color: '#909399' } },
      { scale: true, gridIndex: 1, splitNumber: 2,
        axisLabel: { show: false }, axisLine: { show: false }, splitLine: { show: false } },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], start: 70, end: 100 },
      { show: true, xAxisIndex: [0, 1], type: 'slider', bottom: 10,
        start: 70, end: 100, height: 18 },
    ],
    series: [
      {
        name: 'K线', type: 'candlestick', data: ohlc,
        itemStyle: {
          color: '#ef4f4f', color0: '#14b066',
          borderColor: '#ef4f4f', borderColor0: '#14b066',
        },
      },
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
  await loadSession()
  await Promise.all([loadKline(), loadEquity()])
})

onUnmounted(() => {
  window.removeEventListener('resize', resize)
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
  display: flex; gap: 10px;
  background: #fff; padding: 12px 16px;
  border-radius: 6px;
  box-shadow: 0 1px 4px rgba(0,0,0,.06);
  align-items: stretch;
}
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
.m-block.actions { flex-direction: row; align-items: center; gap: 12px; }
.finish-btn { margin-left: 8px; }

.page-card { background: #fff; padding: 12px 16px; border-radius: 6px;
             box-shadow: 0 1px 4px rgba(0,0,0,.06); }
.page-card h3 { margin: 0 0 8px; }
.chart-head { display: flex; align-items: center; justify-content: space-between;
              margin-bottom: 8px; }
.chart-head .t { font-size: 14px; color: #303133; font-weight: bold; }
.chart-head .hint { font-size: 12px; color: #909399; }
.kline-chart { width: 100%; height: 380px; }
.equity-chart { width: 100%; height: 220px; }
.green { color: #67c23a; }
.red { color: #f56c6c; }
.muted { color: #b4bcd0; }
.estimated-qty { margin-top: 4px; font-size: 12px; color: #606266; }
</style>
