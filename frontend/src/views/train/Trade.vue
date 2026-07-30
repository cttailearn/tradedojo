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
          <div class="val">¥ {{ money(walletBalance) }}</div>
          <div class="meta">初始 ¥ {{ money(session?.initial_cash) }}</div>
        </div>
        <div class="m-block">
          <div class="lbl">持仓市值</div>
          <div class="val">¥ {{ money(session?.market_value) }}</div>
        </div>
        <div class="m-block m-actions">
          <div class="lbl">训练操作</div>
          <div class="val actions-row">
            <el-button type="warning" plain size="small" @click="finish"
                      :disabled="session?.status === 'finished'">
              <el-icon><CircleClose /></el-icon>
              {{ session?.status === 'finished' ? '已结束' : '结束训练' }}
            </el-button>
            <el-button type="info" plain size="small"
                      @click="$router.push(`/train/report/${sessionId}`)">
              <el-icon><Document /></el-icon>训练总结
            </el-button>
          </div>
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
      </div>
    </div>

    <!-- 主体:K线(左大) + 时间推进(右上) + 下单(右下,买/卖按股) + 持仓 + 成交/资金曲线 -->
    <el-row :gutter="16" class="trade-top">
      <!-- 左:K线图 -->
      <el-col :xs="24" :sm="24" :md="16" :lg="16">
        <div class="page-card">
          <div class="chart-head">
            <div class="chart-head-left">
              <span class="t">K 线图</span>
              <el-radio-group v-model="period" size="small" class="period-group"
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
            <div class="bench-pick">
              <span class="hint">对照指数:</span>
              <el-select v-model="benchCode" placeholder="不叠加" clearable size="small"
                         class="bench-select" @change="loadBenchmark">
                <el-option
                  v-for="i in benchList" :key="i.code"
                  :label="`${i.name} (${i.code})`" :value="i.code"
                />
              </el-select>
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
      </el-col>

      <!-- 右:时间推进(上) + 下单(下) -->
      <el-col :xs="24" :sm="24" :md="8" :lg="8">
        <!-- 1) 时间推进(独立卡) -->
        <div class="page-card">
          <h3 class="page-title">
            时间推进
            <span class="hint" style="float:right; font-weight:normal; font-size:12px;">
              仅揭示未来,不可倒退
            </span>
          </h3>
          <div class="advance-row">
            <el-button class="advance-btn" :disabled="!canAdvance || advancing"
                       :loading="advancing" @click="advance(1)">
              <el-icon><Right /></el-icon>推进 1 天
            </el-button>
            <el-button class="advance-btn" :disabled="!canAdvance || advancing"
                       :loading="advancing" @click="advance(5)">+5 天</el-button>
            <el-button class="advance-btn" :disabled="!canAdvance || advancing"
                       :loading="advancing" @click="advance(30)">+30 天</el-button>
          </div>
          <div class="advance-extra">
            <span class="hint" style="color:#909399; font-size:12px;">在顶部进度区已提供"结束训练 / 训练总结"</span>
          </div>
        </div>

        <!-- 2) 下单(买/卖都按股) -->
        <div class="page-card" style="margin-top: 12px;">
          <h3 class="page-title">下单</h3>
          <div class="trade-pane">
            <!-- 买入 -->
            <div class="trade-pane-col trade-pane-buy">
              <div class="trade-pane-header">
                <el-icon color="#ef232a"><Top /></el-icon>
                <span>买入</span>
              </div>
              <el-form label-position="top" class="trade-form">
                <el-form-item label="买入股数 (100 股整数倍)">
                  <el-input-number v-model="buyForm.quantity" :min="100" :step="100"
                                   class="full-width" />
                </el-form-item>
                <el-form-item label="快捷选择 (按持仓资金)">
                  <el-radio-group v-model="buyPreset" size="small"
                                  class="preset-radio" @change="applyBuyPreset">
                    <el-radio-button value="cash_half">1/2 仓</el-radio-button>
                    <el-radio-button value="cash_third">1/3 仓</el-radio-button>
                    <el-radio-button value="cash_all">全仓</el-radio-button>
                    <el-radio-button value="custom">自定义股</el-radio-button>
                  </el-radio-group>
                  <div v-if="buyPreset === 'custom'" class="custom-row">
                    <el-input-number v-model="customBuyShares" :min="100" :step="100"
                                     :max="100000" class="custom-shares" />
                    <span class="custom-hint">股 (100 整数倍)</span>
                  </div>
                </el-form-item>
                <el-form-item label="限价 (可选,默认按收盘价)">
                  <el-input-number v-model="buyForm.price" :min="0.01" :step="0.01"
                                   :precision="2" class="full-width" placeholder="不填按收盘价" />
                </el-form-item>
                <el-alert :closable="false" type="info" show-icon>
                  将按 100 股取整,自动扣除 <b>¥ {{ money(estimateFees('buy')) }}</b> 元手续费(估)
                </el-alert>
                <div class="trade-action">
                  <el-button type="primary" :loading="trading" :disabled="!canTrade"
                            class="full-width" @click="submit('BUY')">
                    <el-icon><Top /></el-icon>买入 (按收盘价)
                  </el-button>
                </div>
              </el-form>
            </div>
            <!-- 卖出 -->
            <div class="trade-pane-col trade-pane-sell">
              <div class="trade-pane-header">
                <el-icon color="#14b066"><Bottom /></el-icon>
                <span>卖出</span>
              </div>
              <el-form label-position="top" class="trade-form">
                <el-form-item label="卖出股数 (100 股整数倍)">
                  <el-input-number v-model="sellForm.quantity" :min="100" :step="100"
                                   class="full-width" />
                </el-form-item>
                <el-form-item label="快捷选择 (按当前持仓)">
                  <el-radio-group v-model="sellPreset" size="small"
                                  class="preset-radio" @change="applySellPreset">
                    <el-radio-button value="half">1/2 仓</el-radio-button>
                    <el-radio-button value="third">1/3 仓</el-radio-button>
                    <el-radio-button value="all">全仓</el-radio-button>
                    <el-radio-button value="custom">自定义股</el-radio-button>
                  </el-radio-group>
                  <div v-if="sellPreset === 'custom'" class="custom-row">
                    <el-input-number v-model="customSellShares" :min="100" :step="100"
                                     :max="myPositionQty" class="custom-shares" />
                    <span class="custom-hint">股 (100 整数倍,最大 {{ myPositionQty }})</span>
                  </div>
                </el-form-item>
                <el-form-item label="限价 (可选,默认按收盘价)">
                  <el-input-number v-model="sellForm.price" :min="0.01" :step="0.01"
                                   :precision="2" class="full-width" placeholder="不填按收盘价" />
                </el-form-item>
                <el-alert :closable="false" type="warning" show-icon>
                  当前持仓 <b>{{ myPositionQty }}</b> 股,均价 <b>¥ {{ myAvgCost.toFixed(2) }}</b>
                  <div v-if="sellForm.quantity > 0" :class="sellEstimatedPnl >= 0 ? 'estimated-qty green' : 'estimated-qty red'">
                    预计实现盈亏: <b>{{ sellEstimatedPnl >= 0 ? '+' : '' }}{{ money(sellEstimatedPnl) }}</b> 元
                  </div>
                </el-alert>
                <div class="trade-action">
                  <el-button type="danger" :loading="trading" :disabled="!canTrade"
                            class="full-width" @click="submit('SELL')">
                    <el-icon><Bottom /></el-icon>卖出
                  </el-button>
                </div>
              </el-form>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 下方:当前持仓 + 成交记录 + 资金曲线 -->
    <el-row :gutter="16" class="trade-bottom">
      <el-col :xs="24" :sm="24" :md="24" :lg="24">
        <div class="page-card">
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
      </el-col>

      <el-col :xs="24" :sm="24" :md="14" :lg="14">
        <div class="page-card">
          <h3 class="page-title">成交记录</h3>
          <el-table :data="session?.recent_orders || []" size="small" stripe
                    :max-height="260">
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
      <el-col :xs="24" :sm="24" :md="10" :lg="10">
        <div class="page-card">
          <div class="chart-head">
            <h3 class="page-title" style="margin:0;">资金曲线</h3>
            <span class="hint">含初始 ¥ {{ money(session?.initial_cash) }}</span>
          </div>
          <div ref="equityChartEl" class="equity-chart" />
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
import { useTrainAuthStore } from '@/stores/trainAuth'

const route = useRoute()
const router = useRouter()
const id = computed(() => Number(route.params.id))
const auth = useTrainAuthStore()

const session = ref(null)
const walletBalance = computed(() => Number(auth.wallet?.balance || 0))
const klineBars = ref([])
const equity = ref([])
// 对照指数
const benchList = ref([])
const benchCode = ref(null)
const benchBars = ref([])   // [{ trade_date, close }]
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
const buyForm = reactive({ quantity: 1000, price: null })
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
  if (!currentPrice.value) return 0
  return Math.max(100, Math.round((buyForm.quantity || 0) / 100) * 100)
})

const sellEstimatedPnl = computed(() => {
  const q = Number(sellForm.quantity) || 0
  if (!q || !myPositionQty.value || !session.value?.fee_rules) return 0
  const f = session.value.fee_rules
  const ratio = Math.min(q / myPositionQty.value, 1)
  const proceeds = currentPrice.value * q                                  // 卖出价 × 股数
  const cost = myAvgCost.value * q                                          // 买入成本
  // 卖出端: 佣金 + 印花税 + 过户费
  const sellCommission = Math.max(proceeds * f.commission_rate, f.min_commission)
  const sellStamp      = proceeds * f.stamp_tax
  const sellTransfer   = proceeds * f.transfer_fee
  const sellFees       = sellCommission + sellStamp + sellTransfer
  // 买入端: 平均成本已经含手续费(FIFO 模式 avg_cost 已含买入费),
  // 这里 avg_cost 已经是含税均价,所以不再减买入费. 后端公式:
  //   realized_pnl = proceeds - sellFees - cost_basis - buy_fee_proportion
  // 若 avg_cost 已是含买入费均价,则 buy_fee_proportion ≈ 0,只减 sellFees.
  return proceeds - cost - sellFees
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
  const amt = side === 'buy'
    ? (buyForm.quantity || 0) * price
    : (sellForm.quantity || 0) * price
  if (!amt) return 0
  const commission = Math.max(amt * f.commission_rate, f.min_commission)
  const stamp = side === 'sell' ? amt * f.stamp_tax : 0
  const transfer = amt * f.transfer_fee
  return commission + stamp + transfer
}

function applyBuyPreset(v) {
  if (!v) return
  const cash = walletBalance.value || 0
  const price = currentPrice.value || 0
  const sharesFromCash = (multi) => {
    // 留 5% 给手续费,计算能买的股数
    const budget = cash * multi * 0.95
    if (!price) return 100
    return Math.max(100, Math.floor(budget / (price * 100)) * 100)
  }
  if (v === 'cash_half') {
    buyForm.quantity = sharesFromCash(0.5)
  } else if (v === 'cash_third') {
    buyForm.quantity = sharesFromCash(1 / 3)
  } else if (v === 'cash_all') {
    buyForm.quantity = sharesFromCash(0.95)
  } else if (v === 'custom') {
    const shares = Math.max(100, Math.round(customBuyShares.value / 100) * 100)
    customBuyShares.value = shares
    buyForm.quantity = shares
  } else {
    buyForm.quantity = Math.max(100, Math.round((Number(v) || 0) / 100) * 100)
  }
}

function applySellPreset(v) {
  if (!v) return
  const qty = myPositionQty.value || 0
  const r100 = (n) => Math.max(100, Math.floor(n / 100) * 100)
  if (v === 'third') sellForm.quantity = r100(qty / 3)
  else if (v === 'half') sellForm.quantity = r100(qty * 0.5)
  else if (v === 'all') sellForm.quantity = qty
  else if (v === 'custom') {
    const shares = Math.max(100, Math.round(customSellShares.value / 100) * 100)
    customSellShares.value = Math.min(shares, qty)
    sellForm.quantity = customSellShares.value
  }
}

// 自定义股数变化时,实时同步到 buyForm.quantity
watch([customBuyShares, currentPrice], () => {
  if (buyPreset.value === 'custom') {
    const shares = Math.max(100, Math.round(customBuyShares.value / 100) * 100)
    customBuyShares.value = shares
    buyForm.quantity = shares
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

async function loadBenchmarkList() {
  try {
    const r = await trainApi.indices()
    benchList.value = r.items || []
    // 默认 None,不自动叠加;用户主动选.
  } catch (e) {
    /* 静默失败,UI 仍可用 */
  }
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
    // 拉整段训练区间 → reveal_date 的指数(包含历史回看)
    const start = sd ? new Date(sd.getTime() - 365 * 86400000 * 2) : null // 多拉 2 年
    const fmt = (d) => d ? d.toISOString().slice(0, 10) : undefined
    const r = await trainApi.indexKline(benchCode.value, {
      start: fmt(start),
      end: ed,
      limit: 1500,
    })
    benchBars.value = r.items || []
    await nextTick()
    renderKline()
  } catch (e) {
    ElMessage.error(e.message || '加载对照指数失败')
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
      task: 'sync_latest',
      params: {
        days_back: 120, adjust: 'qfq',
        workers: 2, codes: [code],
        since_list_date: true,
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

// 从 session.recent_orders(已按时序)构建买卖点位 + 持仓区间
// 颜色用中国市场习惯:买入红(▲)、卖出绿(▼)
function buildTradeMarks(dates, lastDate, lastClose, lastUp) {
  const orders = Array.isArray(session.value?.recent_orders)
    ? session.value.recent_orders.slice().reverse()  // 转升序
    : []
  const dateIdx = new Map(dates.map((d, i) => [d, i]))
  const points = orders.flatMap((o) => {
    if (!dateIdx.has(o.trade_date)) return []
    const idx = dateIdx.get(o.trade_date)
    const bar = klineBars.value[idx]
    if (!bar) return []
    const isBuy = o.side === 'BUY'
    return [{
      name: isBuy ? '买' : '卖',
      coord: [o.trade_date, Number(o.price)],
      value: isBuy ? 'B' : 'S',
      itemStyle: {
        color: isBuy ? '#ef232a' : '#14b066',
        borderColor: '#fff',
        borderWidth: 1,
      },
      label: {
        show: true,
        position: isBuy ? 'top' : 'bottom',
        color: '#fff',
        fontSize: 10,
        fontWeight: 'bold',
        formatter: () => `${isBuy ? 'B' : 'S'} ${Number(o.price).toFixed(2)}`,
      },
    }]
  })
  // 保留最新价标牌
  points.push({
    name: '最新价',
    coord: [lastDate, lastClose],
    value: lastClose.toFixed(2),
    itemStyle: { color: lastUp ? '#ef232a' : '#14b066' },
    label: { color: '#fff', fontSize: 10, fontWeight: 'bold' },
  })
  return points
}

// 持仓区间:BUY 起到 后续 SELL(全部)为止;剩余未平仓持仓延伸到 end_date
function buildTradeAreas(dates) {
  const orders = Array.isArray(session.value?.recent_orders)
    ? session.value.recent_orders.slice().reverse()
    : []
  if (!orders.length) return []
  const lastDate = dates[dates.length - 1]
  const areas = []
  let openStart = null
  let openQty = 0
  for (const o of orders) {
    if (o.side === 'BUY') {
      if (!openStart) openStart = o.trade_date
      openQty += Number(o.quantity || 0)
    } else if (o.side === 'SELL') {
      openQty -= Number(o.quantity || 0)
      if (openQty <= 0 && openStart) {
        // 区间结束于该卖单日;若 SELL 日没有 K线(节假日),延伸到下一根 K线
        const endDate = dates.includes(o.trade_date)
          ? o.trade_date
          : (dates.find((d) => d >= o.trade_date) || o.trade_date)
        areas.push([
          { xAxis: openStart, name: '持仓' },
          { xAxis: endDate },
        ])
        openStart = null
        openQty = 0
      }
    }
  }
  // 仍持仓(未平仓) → 延伸到最后一根 K线
  if (openStart && openQty > 0) {
    areas.push([
      { xAxis: openStart, name: '持仓中' },
      { xAxis: lastDate },
    ])
  }
  return areas
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

  // 对照指数:rebased 到与个股同一基期(训练开始日前一日)
  // 这样图上指数与个股可以直接比较相对涨跌,而不是绝对价位
  let benchSeries = []
  if (benchCode.value && benchBars.value.length) {
    // 找个股最左那根 date 在指数 bars 中的位置作为基准 100
    const firstStock = dates[0]
    const sortedBench = benchBars.value.slice().sort((a, b) => a.trade_date.localeCompare(b.trade_date))
    // 选训练开始日之前最近一日(更稳),找不到就退回指数第一根
    const startIdx = (() => {
      let i = 0
      for (let j = 0; j < sortedBench.length; j++) {
        if (sortedBench[j].trade_date <= firstStock) i = j
        else break
      }
      return i
    })()
    const baseClose = Number(sortedBench[startIdx]?.close) || 1
    // 按个股的 dates 对齐;有的留空 (-)
    const aligned = dates.map((d) => {
      const hit = sortedBench.find((b) => b.trade_date === d)
      if (!hit) return '-'
      return +(((Number(hit.close) / baseClose) - 1) * 100).toFixed(2)
    })
    benchSeries = [{
      name: `对照(${benchCode.value})%`,
      type: 'line',
      data: aligned,
      // 对照指数画在主图(grid[0])上方,使用 xAxis[0] + yAxis[1](左侧 0~100% 范围)
      xAxisIndex: 0,
      yAxisIndex: 1,
      smooth: true,
      showSymbol: false,
      lineStyle: { width: 1, color: '#ffd700', type: 'dashed' },
      itemStyle: { color: '#ffd700' },
      tooltip: { show: true, valueFormatter: (v) => (v === '-' || v == null ? '-' : `${v >= 0 ? '+' : ''}${v}%`) },
    }]
  }

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
          <div><span style="color:#888;">开</span> <b style="color:#fff;">${Number(bar.open).toFixed(2)}</b>
            &nbsp;<span style="color:#888;">收</span> <b style="color:${chgColor};">${Number(bar.close).toFixed(2)}</b></div>
          <div><span style="color:#888;">高</span> <b style="color:#ef232a;">${Number(bar.high).toFixed(2)}</b>
            &nbsp;<span style="color:#888;">低</span> <b style="color:#14b066;">${Number(bar.low).toFixed(2)}</b></div>
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
      data: ['K线', 'MA5', 'MA10', 'MA20', 'MA30', 'MA60'].concat(
        benchCode.value ? [`对照(${benchCode.value})%`] : []
      ),
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
          color: '#aaa', fontSize: 10, rotate: 0,
          interval: 'auto',
          hideOverlap: true,
          formatter: (val) => {
            // 不同周期显示不同精度的日期
            //  dail y: 正常只显示日;月初显示 MM-DD
            //  weekly: 显示周首日 MM-DD
            //  monthly: 显示 YYYY-MM
            const cur = period.value
            if (cur === 'monthly') {
              // 形如 2025-08,展示 YYYY-MM
              return val && val.length >= 7 ? val.slice(0, 7) : val
            }
            if (cur === 'weekly') {
              // 周聚合的 trade_date 是桶内首日(YYYY-MM-DD),展示 MM-DD
              return val && val.length >= 10 ? val.slice(5) : val
            }
            // daily
            try {
              const d = new Date(val)
              if (val && val.length >= 10 && d.getDate() <= 3) return val.slice(5)
            } catch {}
            return val && val.length >= 10 ? val.slice(8) : val
          },
        },
      },
    ],
    yAxis: [
      {
        // 主图 Y 轴(价格)
        scale: true, gridIndex: 0,
        position: 'right',
        axisLine: { lineStyle: { color: '#555' } },
        axisLabel: {
          color: '#aaa', fontSize: 10,
          formatter: (v) => Number(v).toFixed(2),
        },
        splitLine: { lineStyle: { color: '#1f2937', type: 'dashed' } },
      },
      {
        // 对照指数的 % (rebased),主图叠加
        scale: true, gridIndex: 0,
        position: 'right', offset: 48,
        axisLine: { lineStyle: { color: '#665' } },
        axisLabel: {
          color: '#ffd700', fontSize: 9,
          formatter: (v) => `${v >= 0 ? '+' : ''}${v}%`,
        },
        splitLine: { show: false },
        show: !!benchCode.value,
      },
      {
        // 成交量 Y 轴,子图 grid[1]
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
        xAxisIndex: 0, yAxisIndex: 0,
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
          // K线上的买/卖标记:红色向上三角=买入,绿色向下三角=卖出
          // 数字显示在 marker 右侧
          symbol: 'triangle',
          symbolSize: 14,
          symbolOffset: [0, -2],
          data: buildTradeMarks(dates, lastDate, lastClose, lastUp),
        },
        markArea: {
          // 持仓区间:浅黄绿色半透明背景,标记 BUY->SELL 期间
          silent: true,
          itemStyle: {
            color: 'rgba(251, 191, 36, 0.10)',
            borderColor: 'rgba(251, 191, 36, 0.35)',
            borderWidth: 1,
            borderType: 'dashed',
          },
          data: buildTradeAreas(dates),
        },
      },
      { name: 'MA5',  type: 'line', data: ma5,  smooth: true, lineStyle: { width: 1, color: '#ff9800' }, showSymbol: false },
      { name: 'MA10', type: 'line', data: ma10, smooth: true, lineStyle: { width: 1, color: '#ff5722' }, showSymbol: false },
      { name: 'MA20', type: 'line', data: ma20, smooth: true, lineStyle: { width: 1, color: '#2196f3' }, showSymbol: false },
      { name: 'MA30', type: 'line', data: ma30, smooth: true, lineStyle: { width: 1, color: '#9c27b0' }, showSymbol: false },
      { name: 'MA60', type: 'line', data: ma60, smooth: true, lineStyle: { width: 1, color: '#ffc107' }, showSymbol: false },
      { name: '成交量', type: 'bar', data: volumes, xAxisIndex: 1, yAxisIndex: 2 },
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
    auth.refreshWallet()
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
    const qty = Math.max(100, Math.round((buyForm.quantity || 0) / 100) * 100)
    if (qty < 100) {
      return ElMessage.warning('请输入有效买入股数 (100 整数倍)')
    }
    try {
      await ElMessageBox.confirm(
        `买入 <b>${qty}</b> 股 @ ¥ ${currentPrice.value.toFixed(2)},扣手续费 ¥ ${money(estimateFees('buy'))} 元,确认?`,
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
      ? { side: 'BUY', quantity: buyForm.quantity, price: buyForm.price || undefined }
      : { side: 'SELL', quantity: sellForm.quantity, price: sellForm.price || undefined }
    session.value = await trainApi.trade(id.value, payload)
    ElMessage.success(`${side === 'BUY' ? '买入' : '卖出'}成功`)
    buyPreset.value = ''
    sellPreset.value = ''
    await loadKline()
    await loadEquity()
    auth.refreshWallet()
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

let _chartRO = null

onMounted(async () => {
  klineChart = echarts.init(klineChartEl.value)
  equityChart = echarts.init(equityChartEl.value)
  window.addEventListener('resize', resize)
  window.addEventListener('keydown', onKeydown)
  // 监听 K线容器自身尺寸变化(响应式布局时 panel 宽度变了,window resize 不会触发)
  if (typeof ResizeObserver !== 'undefined') {
    _chartRO = new ResizeObserver(() => {
      try { klineChart && klineChart.resize() } catch {}
      try { equityChart && equityChart.resize() } catch {}
    })
    if (klineChartEl.value) _chartRO.observe(klineChartEl.value)
    if (equityChartEl.value) _chartRO.observe(equityChartEl.value)
  }
  await loadSession()
  await Promise.all([loadKline(), loadEquity(), loadBenchmarkList()])
  // 数据就绪后再 resize 一次,确保拿到正确的容器尺寸
  setTimeout(resize, 0)
})

onUnmounted(() => {
  window.removeEventListener('resize', resize)
  window.removeEventListener('keydown', onKeydown)
  if (_chartRO) { _chartRO.disconnect(); _chartRO = null }
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
.trade { padding: 0 4px; max-width: 1920px; margin: 0 auto; }
.metric-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.m-block.m-actions { flex: 0 0 auto; min-width: 180px; }
.actions-row { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.actions-row :deep(.el-button) { padding: 5px 10px; }
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
/* 中国市场习惯:涨红跌绿 */
.m-block .val.green { color: #ef232a; }   /* 浮盈/总盈=红 */
.m-block .val.red { color: #14b066; }     /* 浮亏/总亏=绿 */
.m-block .meta { font-size: 12px; color: #909399; }
.m-block .meta .green { color: #ef232a; }
.m-block .meta .red { color: #14b066; }
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
              margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.chart-head .t { font-size: 14px; color: #303133; font-weight: bold; }
.chart-head .hint { font-size: 12px; color: #909399; }
.bench-pick { display: flex; align-items: center; gap: 6px; }
.kline-chart {
  width: 100%;
  height: clamp(360px, 55vh, 520px);   /* 响应式高度 */
  background: #0a0e1a;
  border-radius: 6px;
  padding: 4px 0;
  box-shadow: inset 0 0 12px rgba(0,0,0,.5);
}
.equity-chart { width: 100%; height: 220px; }
.chart-empty { padding: 60px 0; text-align: center; }
.empty-hint { font-size: 12px; color: #909399; margin-top: 8px; line-height: 1.8; }
/* 中国市场习惯:涨红跌绿 */
.green { color: #ef232a; }
.red { color: #14b066; }
.muted { color: #b4bcd0; }
.estimated-qty { margin-top: 4px; font-size: 12px; color: #606266; }
.preset-hint { font-size: 11px; color: #909399; margin-top: 4px; }

/* ============ 响应式适配 ============ */
/* ============ 训练主区:布局相关 ============ */
.trade-top, .trade-bottom { margin-top: 16px; }
.trade-top > .el-col, .trade-bottom > .el-col { margin-bottom: 12px; }
.trade-top > .el-col:last-child, .trade-bottom > .el-col:last-child { margin-bottom: 0; }

/* K线图头部 */
.chart-head-left { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.period-group { margin-left: 4px; }
.bench-pick { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.bench-select { width: 180px; max-width: 100%; }

/* 时间推进 */
.advance-row { display: flex; gap: 8px; flex-wrap: wrap; }
.advance-row .advance-btn { flex: 1; min-width: 90px; }
.advance-extra { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }

/* 下单(右侧卡内,买入/卖出按股并排) */
.trade-pane {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  align-items: start;
}
/* 紧凑模式:右侧栏(下单)较窄(<480px)时改为上下堆叠,避免字段挤压 */
@media (max-width: 1399.98px) {
  .trade-pane { grid-template-columns: 1fr; }
}
.trade-pane-col {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 12px 14px;
  background: #fafbfc;
}
.trade-pane-buy { border-color: rgba(239,35,42,.25); background: linear-gradient(180deg, #fff5f5 0%, #fafbfc 50%); }
.trade-pane-sell { border-color: rgba(20,176,102,.25); background: linear-gradient(180deg, #f0fbf5 0%, #fafbfc 50%); }
.trade-pane-header {
  display: flex; align-items: center; gap: 6px;
  font-weight: 600; font-size: 15px;
  margin-bottom: 10px; padding-bottom: 8px;
  border-bottom: 1px dashed #e4e7ed;
}
.trade-form :deep(.el-form-item) { margin-bottom: 12px; }
.trade-form :deep(.el-form-item__label) { font-size: 12px; color: #606266; }
.preset-radio { display: flex; flex-wrap: wrap; gap: 4px; }
.preset-radio :deep(.el-radio-button) { margin-right: 0 !important; }
.custom-row { display: flex; align-items: center; gap: 8px; margin-top: 8px; flex-wrap: wrap; }
.custom-shares { width: 180px; max-width: 100%; }
.custom-hint { color: #909399; font-size: 12px; }
.trade-action { margin-top: 8px; }
.full-width { width: 100%; }

/* ============ 响应式适配 ============ */
/* 平板(<992px):下单改为上下堆叠,周期按钮和对照指数换行 */
@media (max-width: 991.98px) {
  .metric-row-1 .m-block { min-width: 45%; padding: 4px 8px; }
  .metric-row-2 { flex-direction: column; align-items: stretch; }
  .progress-block { min-width: 100%; padding: 0; margin-bottom: 8px; }
  .action-block { justify-content: flex-start; }
  .action-block .el-button-group { display: flex; flex: 1; }
  .action-block .el-button-group .el-button { flex: 1; padding: 8px 4px; font-size: 12px; }
  .trade-pane { grid-template-columns: 1fr !important; }
  .bench-select { width: 160px; }
}

/* 手机(<768px):所有表格/图表/按钮全宽 */
@media (max-width: 767.98px) {
  .trade { padding: 0; }
  .metric-bar { padding: 10px 12px; }
  .metric-row-1 .m-block { min-width: 47%; border-right: none; padding: 4px 6px; }
  .metric-row-1 .m-block.profit { min-width: 100%; }
  .m-block .val { font-size: 16px; }
  .m-block.profit .val { font-size: 18px; }
  .page-card { padding: 8px 10px; border-radius: 4px; }
  .chart-head { gap: 6px; }
  .chart-head .t { font-size: 13px; }
  .chart-head .hint { font-size: 11px; }
  .kline-chart { height: 60vh; min-height: 320px; }
  .progress-text { font-size: 11px; flex-wrap: wrap; gap: 4px; }
  .progress-hint { font-size: 11px; }
  .trade-pane-col { padding: 10px 12px; }
  .trade-pane-header { font-size: 14px; }
  .preset-radio :deep(.el-radio-button__inner) { padding: 6px 8px; font-size: 12px; }
  .bench-select { width: 100%; }
  /* 表格在窄屏允许横向滚动 */
  .page-card :deep(.el-table) { font-size: 12px; }
  .page-card :deep(.el-table .cell) { padding: 0 4px; }
}

/* 大屏优化(>=1600px) */
@media (min-width: 1600px) {
  .kline-chart { height: 540px; }
  .equity-chart { height: 240px; }
}
</style>
