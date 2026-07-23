<template>
  <div class="setup">
    <div class="page-card">
      <h3 class="page-title">发起一次 K 线交易训练</h3>
      <p class="muted">
        设置下面的参数,系统会从已有 A 股中随机挑一只符合条件的历史股票,
        并把 <b>你设定的 "训练开始日" 之前的 {{ form.lookback_months }} 个月数据</b>全部展示出来供你分析,
        此后只能逐日推进,体验真实交易。
      </p>

      <el-form :model="form" label-width="160px" label-position="right" v-loading="loadingOptions">
        <el-divider content-position="left">时间窗</el-divider>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="训练开始日">
              <el-date-picker v-model="form.start_date" type="date"
                              value-format="YYYY-MM-DD" style="width: 100%"
                              placeholder="选择历史中的一天" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="数据结束日">
              <el-date-picker v-model="form.end_date" type="date"
                              value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="提供历史回看月数">
              <el-input-number v-model="form.lookback_months" :min="1" :max="36" />
              <span class="hint">展示训练开始日之前 N 个月的数据</span>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="快捷选择时间段">
              <el-select v-model="rangePreset" @change="applyRangePreset"
                         placeholder="预设时段" style="width: 100%;">
                <el-option label="2020-2021 牛市" value="2020-2021" />
                <el-option label="2021-2022 大跌" value="2021-2022" />
                <el-option label="2023-2024 筑底" value="2023-2024" />
                <el-option label="2024-2025 反弹" value="2024-2025" />
                <el-option label="最近一年 (近 12 个月)" value="recent12m" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider content-position="left">资金 & 交易规则</el-divider>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="初始资金">
              <el-input-number v-model="form.initial_cash" :min="10000" :step="10000" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="每次买入金额">
              <el-input-number v-model="form.per_trade_amount" :min="1000" :step="10000" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="分仓 (仓位最大数)">
              <el-input-number v-model="form.max_positions" :min="1" :max="20" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider content-position="left">手续费设置</el-divider>
        <el-row :gutter="16">
          <el-col :span="6">
            <el-form-item label="佣金率 (万几)">
              <el-input-number v-model="form.commission_rate" :min="0" :max="0.01"
                               :step="0.0001" :precision="5" />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="最低佣金 (元)">
              <el-input-number v-model="form.min_commission" :min="0" :step="1" />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="印花税 (千几,卖出)">
              <el-input-number v-model="form.stamp_tax" :min="0" :max="0.05"
                               :step="0.0001" :precision="4" />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="过户费 (万几)">
              <el-input-number v-model="form.transfer_fee" :min="0" :max="0.01"
                               :step="0.00001" :precision="6" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider content-position="left">股票范围</el-divider>
        <el-row :gutter="16">
          <el-col :span="6">
            <el-form-item label="允许分仓">
              <el-switch v-model="form.allow_split" />
              <span class="hint">开启后允许持仓多只股票</span>
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="允许创业板 (30x)">
              <el-switch v-model="form.allow_chinext" />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="允许科创板 (688)">
              <el-switch v-model="form.allow_kcb" />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="允许北交所">
              <el-switch v-model="form.allow_bj" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="允许 ST 股">
              <el-switch v-model="form.allow_st" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="行业 (可选)">
              <el-select v-model="form.industry" clearable filterable placeholder="不限"
                         style="width: 100%">
                <el-option v-for="i in options.industries" :key="i" :label="i" :value="i" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="市场 (可选)">
              <el-select v-model="form.market" clearable placeholder="不限"
                         style="width: 100%">
                <el-option label="上海 SH" value="SH" />
                <el-option label="深圳 SZ" value="SZ" />
                <el-option label="北京 BJ" value="BJ" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="关键字 (代码/名称)">
              <el-input v-model="form.keyword" placeholder="如 银 行 / 600519" clearable />
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider content-position="left">费用预估</el-divider>
        <el-row :gutter="16">
          <el-col :span="24">
            <el-alert type="info" :closable="false" show-icon>
              本次训练消耗训练资金 <b>¥ {{ sessionCost.toFixed(2) }}</b> 元 (按初始资金的 1% 起步,5 ~ 50 元封顶)。
              <span v-if="wallet.balance < sessionCost" style="color: #f56c6c;">
                余额不足 (当前余额 ¥ {{ money(wallet.balance) }}),
                <el-link type="warning" @click="$router.push('/train/wallet')">去充值</el-link>
              </span>
              <span v-else style="margin-left: 8px;">扣费后余额 ¥ {{ money(wallet.balance - sessionCost) }}</span>
            </el-alert>
          </el-col>
        </el-row>

        <el-form-item>
          <el-button type="primary" size="large" :loading="starting"
                     :disabled="wallet.balance < sessionCost || !formValid"
                     @click="start">
            <el-icon><VideoPlay /></el-icon>随机选股并开始训练
          </el-button>
          <el-button @click="reset">恢复默认</el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { trainApi, stocksApi } from '@/api/modules'

const router = useRouter()
const loadingOptions = ref(false)
const starting = ref(false)
const wallet = ref({ balance: 0 })
const rangePreset = ref('')
const options = reactive({ industries: [] })

const DEFAULT_DATES = (() => {
  const today = new Date()
  const oneYearAgo = new Date(today)
  oneYearAgo.setFullYear(today.getFullYear() - 1)
  const twoYearAgo = new Date(today)
  twoYearAgo.setFullYear(today.getFullYear() - 2)
  const fmt = (d) => d.toISOString().slice(0, 10)
  return {
    start: fmt(oneYearAgo),
    end: fmt(today),
  }
})()

const form = reactive({
  start_date: DEFAULT_DATES.start,
  end_date: DEFAULT_DATES.end,
  lookback_months: 6,
  initial_cash: 1_000_000,
  per_trade_amount: 100_000,
  max_positions: 5,
  commission_rate: 0.0003,
  min_commission: 5,
  stamp_tax: 0.001,
  transfer_fee: 0.00001,
  allow_split: true,
  allow_chinext: false,
  allow_kcb: false,
  allow_bj: false,
  allow_st: false,
  industry: null,
  market: null,
  keyword: '',
})

const sessionCost = computed(() => {
  const v = Math.max(form.initial_cash * 0.01, 5)
  return Math.min(v, 50)
})

const formValid = computed(() => {
  if (!form.start_date || !form.end_date) return false
  if (form.start_date >= form.end_date) return false
  if (form.initial_cash < 10_000) return false
  return true
})

function money(v) {
  return Number(v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function loadOptions() {
  loadingOptions.value = true
  try {
    const [ind, w] = await Promise.all([
      stocksApi.industries().catch(() => ({ items: [] })),
      trainApi.wallet().catch(() => ({ balance: 0 })),
    ])
    options.industries = ind?.items?.map((i) => i.industry) || []
    wallet.value = w || {}
  } catch {
    /* silent */
  } finally {
    loadingOptions.value = false
  }
}

function applyRangePreset(v) {
  if (!v) return
  const presets = {
    '2020-2021': { start: '2020-01-01', end: '2021-12-31' },
    '2021-2022': { start: '2021-01-01', end: '2022-12-31' },
    '2023-2024': { start: '2023-01-01', end: '2024-12-31' },
    '2024-2025': { start: '2024-01-01', end: '2025-12-31' },
    'recent12m':  {
      start: new Date(Date.now() - 365 * 86400000).toISOString().slice(0, 10),
      end:   new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10),
    },
  }
  if (presets[v]) {
    form.start_date = presets[v].start
    form.end_date = presets[v].end
  }
  rangePreset.value = ''
}

function reset() {
  rangePreset.value = ''
  Object.assign(form, {
    start_date: DEFAULT_DATES.start,
    end_date: DEFAULT_DATES.end,
    lookback_months: 6,
    initial_cash: 1_000_000,
    per_trade_amount: 100_000,
    max_positions: 5,
    commission_rate: 0.0003,
    min_commission: 5,
    stamp_tax: 0.001,
    transfer_fee: 0.00001,
    allow_split: true,
    allow_chinext: false,
    allow_kcb: false,
    allow_bj: false,
    allow_st: false,
    industry: null,
    market: null,
    keyword: '',
  })
}

async function start() {
  if (!formValid.value) {
    return ElMessage.warning('日期/资金无效,请检查参数')
  }
  starting.value = true
  try {
    const payload = { ...form }
    const res = await trainApi.startSession(payload)
    ElMessage.success(`已随机选中 ${res.name} (${res.code}),开始训练!`)
    router.push(`/train/trade/${res.id}`)
  } catch (e) {
    ElMessage.error(e.message || '发起训练失败')
  } finally {
    starting.value = false
  }
}

onMounted(loadOptions)
</script>

<style scoped>
.muted { color: var(--text-secondary); }
.hint { margin-left: var(--space-sm); color: var(--text-secondary); font-size: var(--text-xs); }
.page-card { background: var(--bg-card); padding: var(--space-2xl); border-radius: var(--radius-lg);
             border: 1px solid var(--border-color-light); }
.page-card h3 { margin-top: 0; }
</style>
