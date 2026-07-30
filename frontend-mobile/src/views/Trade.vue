<template>
  <div class="trade">
    <NavBar :title="title" show-back @back="onBack">
      <template #right>
        <button class="navbar__btn" @click="showReport" aria-label="诊断报告">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 8h6"/><path d="M9 12h6"/><path d="M9 16h4"/>
          </svg>
        </button>
      </template>
    </NavBar>

    <div class="trade__body" v-loading="loading">
      <!-- 顶部 status bar -->
      <section class="status">
        <div class="status__row1">
          <div class="status__stock">
            <div class="status__name">
              <strong>{{ session?.name }}</strong>
              <span class="muted">({{ session?.code }})</span>
            </div>
            <div class="status__sub">{{ session?.industry }} · {{ session?.market }}</div>
          </div>
          <div class="status__equity" :class="(session?.total_pnl || 0) >= 0 ? 'up' : 'down'">
            <div class="status__lbl">总权益</div>
            <div class="status__big num">¥ {{ money(session?.total_equity) }}</div>
            <div class="status__delta">
              {{ (session?.total_pnl || 0) >= 0 ? '+' : '' }}{{ money(session?.total_pnl) }}
              ({{ pct(session?.total_pnl_pct) }})
            </div>
          </div>
        </div>
        <div class="status__row2">
          <div>
            <div class="status__lbl">可用资金</div>
            <div class="num">¥ {{ money(session?.cash) }}</div>
          </div>
          <div>
            <div class="status__lbl">持仓市值</div>
            <div class="num">¥ {{ money(session?.market_value) }}</div>
          </div>
          <div>
            <div class="status__lbl">初始资金</div>
            <div class="num">¥ {{ money(session?.initial_cash) }}</div>
          </div>
        </div>
      </section>

      <!-- 推进控制条 -->
      <section class="advance">
        <div class="advance__text">
          <div>
            <span class="advance__lbl">已揭示</span>
            <strong class="highlight">{{ session?.current_date?.slice(0,10) }}</strong>
          </div>
          <div>
            <span class="advance__lbl">起点</span>
            <span>{{ session?.start_date?.slice(0,10) }}</span>
          </div>
          <div>
            <span class="advance__lbl">终点</span>
            <span>{{ session?.end_date?.slice(0,10) }}</span>
          </div>
        </div>
        <van-progress
          :percentage="progressPct"
          :stroke-width="6"
          :color="progressColor"
          :show-text="false"
          style="margin: 0 var(--sp-3xl) var(--sp-2xl);"
        />
        <div class="advance__buttons">
          <button
            class="btn btn--plain btn--sm"
            :disabled="!canAdvance || advancing"
            @click="advance(1)"
          >推进 1 天</button>
          <button
            class="btn btn--plain btn--sm"
            :disabled="!canAdvance || advancing"
            @click="advance(5)"
          >+5 天</button>
          <button
            class="btn btn--plain btn--sm"
            :disabled="!canAdvance || advancing"
            @click="advance(30)"
          >+30 天</button>
        </div>
      </section>

      <!-- K 线图 -->
      <section class="chart-card">
        <div class="chart-card__head">
          <span>K线图</span>
          <van-tabs v-model:active="period" type="card" shrink @change="loadKline">
            <van-tab title="日K" name="daily" />
            <van-tab title="周K" name="weekly" />
            <van-tab title="月K" name="monthly" />
          </van-tabs>
        </div>
        <div class="chart-card__head" style="margin-top: var(--sp-2xl);">
          <span class="muted">现价 ¥ {{ price(currentPrice) }}
            <span v-if="pctToday !== null" :class="pctToday >= 0 ? 'up' : 'down'" style="margin-left:8px;">
              ({{ pct(pctToday) }})
            </span>
          </span>
          <span class="muted">已揭示 {{ klineBars.length }} 根{{ periodLabel }}</span>
        </div>
        <div ref="klineChartEl" class="kline-chart" />
        <div v-if="loadedSession && !klineBars.length" class="empty" style="padding: var(--sp-5xl) 0;">
          <div class="empty__icon">📉</div>
          <div class="empty__text">所选时间段暂无 K线数据</div>
        </div>
        <div class="bench-pick" v-if="klineBars.length">
          <span class="muted">对照指数:</span>
          <select v-model="benchCode" class="bench-pick__select" @change="loadBenchmark">
            <option :value="null">不叠加</option>
            <option v-for="i in benchList" :key="i.code" :value="i.code">
              {{ i.name }} ({{ i.code }})
            </option>
          </select>
        </div>
      </section>

      <!-- 资金曲线 -->
      <section class="chart-card">
        <div class="chart-card__head">
          <strong style="font-size:0.28rem;">资金曲线</strong>
          <span class="muted">初始 ¥ {{ money(session?.initial_cash) }}</span>
        </div>
        <div ref="equityChartEl" class="equity-chart" />
      </section>

      <!-- 折叠面板:持仓/成交/下单 -->
      <van-collapse v-model:active="activeCollapse" accordion class="collapse">
        <van-collapse-item title="下单" name="trade">
          <van-tabs v-model:active="tradeTab">
            <van-tab title="买入" name="buy">
              <div class="trade-panel">
                <label class="field">
                  <span class="field__label">买入金额 (元)</span>
                  <van-stepper
                    v-model="buyForm.amount"
                    :min="1000"
                    :step="10000"
                    input-width="2.0rem"
                  />
                </label>
                <van-tabs v-model:active="buyPreset" type="card" shrink @change="applyBuyPreset">
                  <van-tab title="1/4 仓" name="cash_quarter" />
                  <van-tab title="1/2 仓" name="cash_half" />
                  <van-tab title="全仓" name="cash_all" />
                  <van-tab title="自定股" name="custom" />
                </van-tabs>
                <label v-if="buyPreset === 'custom'" class="field" style="margin-top: var(--sp-3xl);">
                  <span class="field__label">股数 (100 整数倍)</span>
                  <van-stepper
                    v-model="customBuyShares"
                    :min="100" :step="100" :max="100000"
                    input-width="2.0rem"
                  />
                </label>
                <div class="alert alert--info">
                  将按 100 股取整,扣手续费约 ¥ {{ money(estimateFees('buy')) }}
                  <div v-if="estimatedBuyQty > 0" style="margin-top:4px;">
                    ≈ 买入 <b>{{ estimatedBuyQty }}</b> 股
                  </div>
                </div>
                <button
                  class="btn btn--primary btn--block btn--lg"
                  :disabled="!canTrade || trading"
                  @click="submit('BUY')"
                >买入</button>
              </div>
            </van-tab>
            <van-tab title="卖出" name="sell">
              <div class="trade-panel">
                <label class="field">
                  <span class="field__label">卖出股数 (100 整数倍)</span>
                  <van-stepper
                    v-model="sellForm.quantity"
                    :min="100" :step="100" :max="myPositionQty"
                    input-width="2.0rem"
                  />
                </label>
                <van-tabs v-model:active="sellPreset" type="card" shrink @change="applySellPreset">
                  <van-tab title="1/8" name="eighth" />
                  <van-tab title="1/4" name="quarter" />
                  <van-tab title="1/3" name="third" />
                  <van-tab title="1/2" name="half" />
                  <van-tab title="全部" name="all" />
                  <van-tab title="自定" name="custom" />
                </van-tabs>
                <div class="alert alert--warning" style="margin-top: var(--sp-2xl);">
                  持仓 <b>{{ myPositionQty }}</b> 股 · 均价 ¥ {{ price(myAvgCost) }}
                  <div v-if="sellForm.quantity > 0" :class="sellEstimatedPnl >= 0 ? 'up' : 'down'" style="margin-top:4px;">
                    预计实现:
                    <b>{{ sellEstimatedPnl >= 0 ? '+' : '' }}{{ money(sellEstimatedPnl) }} 元</b>
                  </div>
                </div>
                <button
                  class="btn btn--danger btn--block btn--lg"
                  :disabled="!canTrade || trading"
                  @click="submit('SELL')"
                >卖出</button>
              </div>
            </van-tab>
          </van-tabs>
        </van-collapse-item>

        <van-collapse-item title="当前持仓" name="pos">
          <ul class="list" v-if="session?.positions?.length">
            <li
              v-for="p in session.positions"
              :key="p.code"
              class="list-item"
            >
              <div class="list-item__body">
                <div class="list-item__title">{{ p.code }}</div>
                <div class="list-item__sub">{{ p.quantity }} 股 · 均价 {{ price(p.avg_cost) }}</div>
              </div>
              <div class="list-item__aside" :class="(p.float_pnl||0) >= 0 ? 'up' : 'down'">
                {{ (p.float_pnl||0) >= 0 ? '+' : '' }}{{ money(p.float_pnl) }}
              </div>
            </li>
          </ul>
          <div class="empty" v-else>
            <div class="empty__icon">📭</div>
            <div class="empty__text">暂无持仓</div>
          </div>
        </van-collapse-item>

        <van-collapse-item title="成交记录" name="orders">
          <ul class="list" v-if="session?.recent_orders?.length">
            <li v-for="(o, idx) in session.recent_orders" :key="idx" class="list-item">
              <div class="list-item__body">
                <div class="list-item__title">
                  <span class="tag" :class="o.side === 'BUY' ? 'tag--up' : 'tag--down'">
                    {{ o.side === 'BUY' ? '买' : '卖' }}
                  </span>
                  {{ o.trade_date }} · {{ o.quantity }}股 @ ¥{{ price(o.price) }}
                </div>
                <div class="list-item__sub">手续费 ¥ {{ price(o.total_fee) }}</div>
              </div>
              <div class="list-item__aside" :class="o.side === 'SELL' ? ((o.realized_pnl||0) >= 0 ? 'up' : 'down') : ''">
                {{ o.side === 'SELL' ? `${(o.realized_pnl||0) >= 0 ? '+' : ''}${money(o.realized_pnl)}` : '-' }}
              </div>
            </li>
          </ul>
          <div class="empty" v-else>
            <div class="empty__icon">📋</div>
            <div class="empty__text">还没有成交</div>
          </div>
        </van-collapse-item>
      </van-collapse>

      <div class="trade__footer-actions">
        <button
          class="btn btn--plain"
          :disabled="session?.status === 'finished'"
          @click="finish"
        >
          {{ session?.status === 'finished' ? '已结束' : '结束训练' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showToast, showSuccessToast, showConfirmDialog, showDialog } from 'vant'
// 已经由 main.js → plugins/echarts.js 一次性注册了
// 这里直接 import echarts core(已 .use())
import echarts from '@/plugins/echarts'
import { trainApi } from '@/api/modules'
import { money, pct, price } from '@/utils/trainFee'
import NavBar from '@/components/NavBar.vue'

const route = useRoute()
const router = useRouter()
const id = computed(() => Number(route.params.id))

const session = ref(null)
const klineBars = ref([])
const equity = ref([])
const benchList = ref([])
const benchCode = ref(null)
const benchBars = ref([])
const loadedSession = ref(false)
const loading = ref(false)
const advancing = ref(false)
const trading = ref(false)
const period = ref('daily')
const tradeTab = ref('buy')
const buyPreset = ref('')
const sellPreset = ref('')
const customBuyShares = ref(100)
const customSellShares = ref(100)
const buyForm = reactive({ amount: 100000 })
const sellForm = reactive({ quantity: 100 })
const activeCollapse = ref(['trade'])

let klineChart = null
let equityChart = null
const klineChartEl = ref(null)
const equityChartEl = ref(null)

const title = computed(() => `交易 #${id.value}`)

const canAdvance = computed(() =>
  session.value?.status === 'active'
  && session.value?.current_date < session.value?.end_date
)

const canTrade = computed(() =>
  session.value?.status === 'active'
  && currentPrice.value > 0
  && !!session.value?.current_bar
)

const periodLabel = computed(() =>
  ({ daily: '交易日', weekly: '周', monthly: '月' }[period.value])
)

const currentPrice = computed(() => {
  if (!klineBars.value.length) return 0
  return Number(klineBars.value[klineBars.value.length - 1].close || 0)
})

const pctToday = computed(() => {
  if (!klineBars.value.length) return null
  return Number(klineBars.value[klineBars.value.length - 1].pct_change || 0)
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
  if (!q || !myPositionQty.value || !session.value?.fee_rules) return 0
  const f = session.value.fee_rules
  const proceeds = currentPrice.value * q
  const cost = myAvgCost.value * q
  const sellCommission = Math.max(proceeds * f.commission_rate, f.min_commission)
  const sellStamp = proceeds * f.stamp_tax
  const sellTransfer = proceeds * f.transfer_fee
  return proceeds - cost - (sellCommission + sellStamp + sellTransfer)
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
  if (pnl > 0) return '#10b981'
  if (pnl < 0) return '#ef4444'
  return '#94a3b8'
})

function estimateFees(side) {
  if (!session.value || !session.value.fee_rules) return 0
  const f = session.value.fee_rules
  const px = currentPrice.value
  if (!px) return 0
  const amt = side === 'buy'
    ? (buyForm.amount || 0)
    : (sellForm.quantity || 0) * px
  if (!amt) return 0
  const commission = Math.max(amt * f.commission_rate, f.min_commission)
  const stamp = side === 'sell' ? amt * f.stamp_tax : 0
  const transfer = amt * f.transfer_fee
  return commission + stamp + transfer
}

function applyBuyPreset(v) {
  if (!v) return
  const cash = session.value?.cash || 0
  const px = currentPrice.value || 0
  if (v === 'cash_quarter') buyForm.amount = Math.floor((cash * 0.25) / 1000) * 1000
  else if (v === 'cash_half') buyForm.amount = Math.floor((cash * 0.5) / 1000) * 1000
  else if (v === 'cash_all')   buyForm.amount = Math.floor((cash * 0.95) / 1000) * 1000
  else if (v === 'custom') {
    const shares = Math.max(100, Math.round(customBuyShares.value / 100) * 100)
    customBuyShares.value = shares
    buyForm.amount = Math.ceil((shares * px) / 100) * 100
  }
}

function applySellPreset(v) {
  if (!v) return
  const qty = myPositionQty.value || 0
  const r100 = (n) => Math.max(100, Math.floor(n / 100) * 100)
  if (v === 'eighth')  sellForm.quantity = r100(qty * 0.125)
  else if (v === 'quarter') sellForm.quantity = r100(qty * 0.25)
  else if (v === 'third')   sellForm.quantity = r100(qty / 3)
  else if (v === 'half')    sellForm.quantity = r100(qty * 0.5)
  else if (v === 'all')     sellForm.quantity = qty
  else if (v === 'custom') {
    const shares = Math.max(100, Math.round(customSellShares.value / 100) * 100)
    customSellShares.value = Math.min(shares, qty)
    sellForm.quantity = customSellShares.value
  }
}

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
    showToast({ type: 'fail', message: e.message })
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
    showToast({ type: 'fail', message: e.message })
  }
}

async function loadBenchmarkList() {
  try {
    const r = await trainApi.indices()
    benchList.value = r.items || []
  } catch { /* silent */ }
}

async function loadBenchmark() {
  if (!benchCode.value || !session.value) {
    benchBars.value = []
    renderKline()
    return
  }
  try {
    const sd = session.value?.start_date ? new Date(session.value.start_date) : null
    const ed = session.value?.current_date || session.value?.end_date
    const start = sd ? new Date(sd.getTime() - 365 * 86400000 * 2) : null
    const fmt = (d) => d ? d.toISOString().slice(0, 10) : undefined
    const r = await trainApi.indexKline(benchCode.value, {
      start: fmt(start), end: ed, limit: 1500,
    })
    benchBars.value = r.items || []
    await nextTick()
    renderKline()
  } catch (e) {
    showToast({ type: 'fail', message: e.message || '加载对照指数失败' })
  }
}

async function loadEquity() {
  try {
    const res = await trainApi.equity(id.value)
    equity.value = res.items || []
    await nextTick()
    renderEquity()
  } catch { /* silent */ }
}

function renderKline() {
  if (!klineChart) return
  const bars = klineBars.value
  if (!bars.length) { klineChart.clear(); return }

  const dates = bars.map((b) => b.trade_date)
  const ohlc = bars.map((b) => [b.open, b.close, b.low, b.high])
  const volumes = bars.map((b) => ({
    value: b.volume,
    itemStyle: {
      color: b.close >= b.open ? '#ef232a' : '#14b066',
      opacity: 0.85,
    },
  }))
  const closes = bars.map((b) => Number(b.close))
  const calcMA = (n) =>
    closes.map((_, i) => {
      if (i < n - 1) return '-'
      let s = 0
      for (let k = i - n + 1; k <= i; k++) s += closes[k]
      return +(s / n).toFixed(2)
    })
  const ma5 = calcMA(5), ma10 = calcMA(10), ma20 = calcMA(20),
        ma30 = calcMA(30), ma60 = calcMA(60)

  // 对照指数
  let benchSeries = []
  if (benchCode.value && benchBars.value.length) {
    const firstStock = dates[0]
    const sortedBench = benchBars.value.slice().sort((a, b) => a.trade_date.localeCompare(b.trade_date))
    let startIdx = 0
    for (let j = 0; j < sortedBench.length; j++) {
      if (sortedBench[j].trade_date <= firstStock) startIdx = j
      else break
    }
    const baseClose = Number(sortedBench[startIdx]?.close) || 1
    const aligned = dates.map((d) => {
      const hit = sortedBench.find((b) => b.trade_date === d)
      if (!hit) return '-'
      return +(((Number(hit.close) / baseClose) - 1) * 100).toFixed(2)
    })
    benchSeries = [{
      name: `对照${benchCode.value}%`,
      type: 'line',
      data: aligned,
      yAxisIndex: 1,
      smooth: true,
      showSymbol: false,
      lineStyle: { width: 1, color: '#ffd700', type: 'dashed' },
      itemStyle: { color: '#ffd700' },
    }]
  }

  const lastBar = bars[bars.length - 1]
  const lastClose = Number(lastBar.close)
  const lastDate = lastBar.trade_date
  const startDate = session.value?.start_date
  const startMark = (startDate && dates.includes(startDate))
    ? [{ xAxis: startDate, name: '训练起点' }]
    : []

  klineChart.setOption({
    backgroundColor: '#0a0e1a',
    animation: false,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      backgroundColor: 'rgba(20, 30, 50, 0.95)',
      borderColor: '#444',
      textStyle: { color: '#e0e0e0', fontSize: 11 },
    },
    legend: {
      data: ['K线', 'MA5', 'MA10', 'MA20', 'MA30', 'MA60'].concat(
        benchCode.value ? [`对照${benchCode.value}%`] : []
      ),
      top: 0, left: 'center',
      textStyle: { color: '#ccc', fontSize: 10 },
      itemWidth: 10, itemHeight: 6,
    },
    grid: [
      { left: 40, right: 50, top: 28, height: '60%' },
      { left: 40, right: 50, top: '74%', height: '18%' },
    ],
    xAxis: [
      { type: 'category', data: dates, scale: true, boundaryGap: false,
        axisLine: { lineStyle: { color: '#555' } },
        axisLabel: { show: false }, axisTick: { show: false } },
      { type: 'category', data: dates, gridIndex: 1,
        axisLine: { lineStyle: { color: '#555' } },
        axisTick: { show: false },
        axisLabel: { color: '#aaa', fontSize: 9, formatter: (v) => v?.slice(5) } },
    ],
    yAxis: [
      { scale: true, position: 'right',
        axisLine: { lineStyle: { color: '#555' } },
        axisLabel: { color: '#aaa', fontSize: 9 },
        splitLine: { lineStyle: { color: '#1f2937', type: 'dashed' } } },
      { scale: true, position: 'right',
        axisLine: { lineStyle: { color: '#665' } },
        axisLabel: { color: '#ffd700', fontSize: 8, formatter: (v) => `${v >= 0 ? '+' : ''}${v}%` },
        show: !!benchCode.value },
      { scale: true, gridIndex: 1, position: 'right',
        axisLine: { lineStyle: { color: '#555' } },
        axisLabel: { color: '#aaa', fontSize: 9,
          formatter: (v) => v >= 10000 ? `${(v / 10000).toFixed(0)}万` : v },
        splitNumber: 2, splitLine: { show: false } },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1] },
      { show: true, xAxisIndex: [0, 1], type: 'slider',
        bottom: 0, height: 14, start: 60, end: 100,
        backgroundColor: 'rgba(40, 50, 80, 0.5)',
        borderColor: '#444', fillerColor: 'rgba(80, 120, 220, 0.4)',
        handleStyle: { color: '#888' }, showDetail: false },
    ],
    series: [
      { name: 'K线', type: 'candlestick', data: ohlc,
        itemStyle: { color: '#ef232a', color0: '#14b066', borderColor: '#ef232a', borderColor0: '#14b066' },
        markLine: {
          symbol: 'none', silent: true,
          label: { show: true, position: 'end', color: '#fbbf24', formatter: '训练起点', fontSize: 9 },
          lineStyle: { color: '#fbbf24', type: 'dashed', width: 1 },
          data: startMark,
        },
      },
      { name: 'MA5',  type: 'line', data: ma5,  smooth: true, lineStyle: { width: 1, color: '#ff9800' }, showSymbol: false },
      { name: 'MA10', type: 'line', data: ma10, smooth: true, lineStyle: { width: 1, color: '#ff5722' }, showSymbol: false },
      { name: 'MA20', type: 'line', data: ma20, smooth: true, lineStyle: { width: 1, color: '#2196f3' }, showSymbol: false },
      { name: 'MA30', type: 'line', data: ma30, smooth: true, lineStyle: { width: 1, color: '#9c27b0' }, showSymbol: false },
      { name: 'MA60', type: 'line', data: ma60, smooth: true, lineStyle: { width: 1, color: '#ffc107' }, showSymbol: false },
      { name: '成交量', type: 'bar', data: volumes, xAxisIndex: 1, yAxisIndex: 1 },
      ...benchSeries,
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
    legend: { data: ['总权益', '可用资金'], top: 0, textStyle: { fontSize: 10 } },
    grid: { left: 40, right: 16, top: 24, bottom: 24 },
    xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 9 } },
    yAxis: { type: 'value', scale: true, axisLabel: { fontSize: 9 } },
    series: [
      { name: '总权益', type: 'line', data: equityArr, smooth: true,
        lineStyle: { color: '#3b82f6', width: 2 },
        areaStyle: { color: 'rgba(64, 158, 255, .15)' } },
      { name: '可用资金', type: 'line', data: cashArr, smooth: true,
        lineStyle: { color: '#f59e0b', width: 1, type: 'dashed' } },
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
      showToast('已到达训练终点')
    }
  } catch (e) {
    showToast({ type: 'fail', message: e.message })
  } finally {
    advancing.value = false
  }
}

async function submit(side) {
  if (side === 'BUY') {
    if (!buyForm.amount || buyForm.amount < 1000) {
      return showToast('请输入有效买入金额')
    }
    try {
      await showConfirmDialog({
        title: '买入确认',
        message: `买入约 ${estimatedBuyQty.value} 股 @ ¥ ${price(currentPrice.value)},扣手续费 ¥ ${money(estimateFees('buy'))}`,
      })
    } catch { return }
  } else {
    if (!sellForm.quantity || sellForm.quantity < 100 || sellForm.quantity > myPositionQty.value) {
      return showToast(`请填有效卖出股数(最多 ${myPositionQty.value})`)
    }
    try {
      await showConfirmDialog({
        title: '卖出确认',
        message: `卖出 ${sellForm.quantity} 股,预计实现 ¥ ${sellEstimatedPnl.value >= 0 ? '+' : ''}${money(sellEstimatedPnl.value)}`,
      })
    } catch { return }
  }
  trading.value = true
  try {
    const payload = side === 'BUY'
      ? { side: 'BUY', amount: buyForm.amount }
      : { side: 'SELL', quantity: sellForm.quantity }
    session.value = await trainApi.trade(id.value, payload)
    showSuccessToast('成交成功')
    buyPreset.value = ''
    sellPreset.value = ''
    await loadKline()
    await loadEquity()
  } catch (e) {
    showToast({ type: 'fail', message: e.message })
  } finally {
    trading.value = false
  }
}

async function finish() {
  if (session.value?.status === 'finished') return
  try {
    await showConfirmDialog({ title: '结束训练?', message: '结束后将无法继续下单' })
  } catch { return }
  try {
    session.value = await trainApi.finish(id.value)
    showSuccessToast('已结束训练')
  } catch (e) {
    showToast({ type: 'fail', message: e.message })
  }
}

function showReport() {
  router.push(`/report/${id.value}`)
}
function onBack() { /* NavBar 内部已处理 */ }

function resize() {
  klineChart && klineChart.resize()
  equityChart && equityChart.resize()
}

onMounted(async () => {
  klineChart = echarts.init(klineChartEl.value)
  equityChart = echarts.init(equityChartEl.value)
  window.addEventListener('resize', resize)
  await loadSession()
  await Promise.all([loadKline(), loadEquity(), loadBenchmarkList()])
})

onUnmounted(() => {
  window.removeEventListener('resize', resize)
  klineChart && klineChart.dispose()
  equityChart && equityChart.dispose()
})

watch(() => session.value?.current_date, async () => {
  await loadKline()
  await loadEquity()
  if (benchCode.value) await loadBenchmark()
})
</script>

<style scoped>
.trade { background: var(--bg-page); min-height: 100vh; min-height: 100dvh; padding-top: var(--navbar-h); }
.trade__body { padding-bottom: calc(var(--safe-bottom) + var(--sp-5xl)); }

.status { padding: var(--sp-3xl) var(--sp-4xl); background: var(--bg-card); }
.status__row1 {
  display: flex; align-items: flex-start; justify-content: space-between;
  margin-bottom: var(--sp-3xl);
}
.status__name strong { font-size: 0.34rem; }
.status__name .muted { font-size: 0.24rem; margin-left: var(--sp-sm); }
.status__sub { font-size: 0.22rem; color: var(--text-placeholder); margin-top: 2px; }
.status__equity { text-align: right; }
.status__lbl { font-size: 0.22rem; color: var(--text-placeholder); }
.status__big { font-size: 0.40rem; font-weight: 700; line-height: 1.1; }
.status__delta { font-size: 0.24rem; }
.status__row2 {
  display: grid; grid-template-columns: 1fr 1fr 1fr;
  gap: var(--sp-3xl);
  font-size: 0.26rem;
  padding-top: var(--sp-3xl);
  border-top: 1px solid var(--border-color-light);
}

.advance {
  background: var(--bg-card);
  margin: var(--sp-2xl) var(--sp-4xl);
  border-radius: var(--radius-lg);
  padding: var(--sp-3xl) 0;
}
.advance__text {
  display: flex; justify-content: space-around; padding: 0 var(--sp-4xl) var(--sp-2xl);
  font-size: 0.22rem;
}
.advance__lbl { color: var(--text-placeholder); margin-right: 4px; }
.highlight {
  background: #ecf5ff; color: var(--color-primary);
  padding: 2px var(--sp-2xl); border-radius: var(--radius-full);
  font-weight: 600;
}
.advance__buttons {
  display: grid; grid-template-columns: 1fr 1fr 1fr;
  gap: var(--sp-2xl);
  padding: var(--sp-2xl) var(--sp-4xl) 0;
}
.advance__buttons .btn { width: 100%; padding: 0; }

.chart-card {
  background: var(--bg-card);
  margin: var(--sp-2xl) var(--sp-4xl);
  border-radius: var(--radius-lg);
  padding: var(--sp-3xl);
}
.chart-card__head {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: var(--sp-3xl);
}
.chart-card__head > span:first-child { font-weight: 600; font-size: 0.28rem; }
.muted { color: var(--text-placeholder); font-size: 0.22rem; }

.kline-chart {
  width: 100%;
  height: 4.00rem;
  background: #0a0e1a;
  border-radius: var(--radius-md);
  margin-top: var(--sp-2xl);
}
.equity-chart {
  width: 100%; height: 2.50rem;
  margin-top: var(--sp-2xl);
}

.bench-pick {
  display: flex; align-items: center; gap: var(--sp-2xl);
  margin-top: var(--sp-3xl);
}
.bench-pick__select {
  flex: 1; height: 0.60rem; padding: 0 var(--sp-2xl);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  font-size: 0.26rem; background: #fff;
  -webkit-appearance: none; appearance: none;
}

.collapse {
  margin: var(--sp-2xl) var(--sp-4xl);
  border-radius: var(--radius-lg);
  overflow: hidden;
}
.collapse :deep(.van-collapse-item__content) {
  padding: var(--sp-3xl) 0;
}
.trade-panel { padding: 0 var(--sp-2xl); }

.alert {
  padding: var(--sp-3xl);
  border-radius: var(--radius-md);
  font-size: 0.24rem;
  margin: var(--sp-3xl) 0;
}
.alert--info { background: var(--color-primary-lighter); color: var(--text-regular); }
.alert--warning { background: #fff7e6; color: var(--text-regular); }

.up   { color: var(--color-up); }
.down { color: var(--color-down); }

.trade__footer-actions {
  padding: var(--sp-3xl) var(--sp-4xl) 0;
}
.trade__footer-actions .btn { width: 100%; }
</style>
