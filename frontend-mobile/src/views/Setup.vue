<template>
  <div class="setup page page--no-navbar" :style="{ paddingTop: 'var(--navbar-h)' }">
    <div class="setup__intro">
      <h2>发起新训练</h2>
      <p>设置参数后,系统会从已有 A 股中随机抽取一只符合条件的历史股票。</p>
    </div>

    <!-- 时间窗 -->
    <section class="card">
      <h3 class="card__title">⏱ 时间窗</h3>
      <van-tabs v-model:active="rangePreset" type="card" shrink @change="applyRangePreset">
        <van-tab title="1 年内" name="1y" />
        <van-tab title="3 年内" name="3y" />
        <van-tab title="5 年内" name="5y" />
      </van-tabs>

      <label class="field field--inline" style="margin-top: var(--sp-3xl);">
        <span class="field__label">训练开始日</span>
        <input
          type="date"
          class="field__input"
          v-model="form.start_date"
          style="max-width: 3.50rem;"
        />
      </label>
      <label class="field field--inline">
        <span class="field__label">数据结束日</span>
        <input
          type="date"
          class="field__input"
          v-model="form.end_date"
          style="max-width: 3.50rem;"
        />
      </label>
      <label class="field">
        <span class="field__label">
          训练前可见 {{ form.lookback_months }} 个月回看数据
        </span>
        <van-stepper v-model="form.lookback_months" :min="1" :max="36" />
      </label>
    </section>

    <!-- 资金 & 规则 -->
    <section class="card">
      <h3 class="card__title">💰 资金 & 交易规则</h3>
      <label class="field">
        <span class="field__label">初始资金 (元)</span>
        <van-stepper
          v-model="form.initial_cash"
          :min="10000"
          :step="10000"
          input-width="2.5rem"
        />
      </label>
      <label class="field">
        <span class="field__label">每次买入金额 (元)</span>
        <van-stepper
          v-model="form.per_trade_amount"
          :min="1000"
          :step="10000"
          input-width="2.5rem"
        />
      </label>
      <label class="field">
        <span class="field__label">分仓数 (最大持仓数)</span>
        <van-stepper v-model="form.max_positions" :min="1" :max="20" input-width="2.5rem" />
      </label>
    </section>

    <!-- 手续费 -->
    <section class="card">
      <h3 class="card__title">📊 手续费设置 (按交易所默认)</h3>
      <div class="fee-grid">
        <label class="field">
          <span class="field__label">佣金率(万几)</span>
          <input
            v-model.number="form.commission_rate"
            type="number" class="field__input"
            step="0.0001" min="0" max="0.01"
          />
        </label>
        <label class="field">
          <span class="field__label">最低佣金(元)</span>
          <input
            v-model.number="form.min_commission"
            type="number" class="field__input"
            step="1" min="0"
          />
        </label>
        <label class="field">
          <span class="field__label">印花税(千几,卖出)</span>
          <input
            v-model.number="form.stamp_tax"
            type="number" class="field__input"
            step="0.0001" min="0" max="0.05"
          />
        </label>
        <label class="field">
          <span class="field__label">过户费(万几)</span>
          <input
            v-model.number="form.transfer_fee"
            type="number" class="field__input"
            step="0.00001" min="0" max="0.01"
          />
        </label>
      </div>
    </section>

    <!-- 股票范围 -->
    <section class="card">
      <h3 class="card__title">🎯 股票范围</h3>
      <label class="field field--inline">
        <span class="field__label">允许分仓</span>
        <van-switch v-model="form.allow_split" />
      </label>
      <label class="field field--inline">
        <span class="field__label">允许创业板 (30x)</span>
        <van-switch v-model="form.allow_chinext" />
      </label>
      <label class="field field--inline">
        <span class="field__label">允许科创板 (688)</span>
        <van-switch v-model="form.allow_kcb" />
      </label>
      <label class="field field--inline">
        <span class="field__label">允许北交所</span>
        <van-switch v-model="form.allow_bj" />
      </label>
      <label class="field field--inline">
        <span class="field__label">允许 ST 股</span>
        <van-switch v-model="form.allow_st" />
      </label>
      <label class="field">
        <span class="field__label">行业 (可选)</span>
        <select v-model="form.industry" class="field__select">
          <option :value="null">不限</option>
          <option v-for="i in options.industries" :key="i" :value="i">{{ i }}</option>
        </select>
      </label>
      <label class="field">
        <span class="field__label">市场 (可选)</span>
        <select v-model="form.market" class="field__select">
          <option :value="null">不限</option>
          <option value="SH">上海 SH</option>
          <option value="SZ">深圳 SZ</option>
          <option value="BJ">北京 BJ</option>
        </select>
      </label>
      <label class="field">
        <span class="field__label">关键字 (代码/名称)</span>
        <input
          v-model="form.keyword"
          class="field__input"
          type="text"
          placeholder="如 银 行 / 600519"
        />
      </label>
    </section>

    <!-- 费用预估 + 操作 -->
    <section class="card">
      <h3 class="card__title">💸 费用预估</h3>
      <div class="cost">
        <div class="cost__main">
          <span class="cost__lbl">本次训练消耗</span>
          <span class="cost__value num">¥ {{ sessionCost.toFixed(2) }} 元</span>
        </div>
        <div class="cost__sub" v-if="auth.wallet.balance < sessionCost">
          余额不足 (¥ {{ money(auth.wallet.balance) }})
        </div>
        <div class="cost__sub" v-else>
          扣费后余额 ¥ {{ money(auth.wallet.balance - sessionCost) }}
        </div>
      </div>
      <button
        class="btn btn--primary btn--block btn--lg"
        :disabled="starting || auth.wallet.balance < sessionCost || !formValid"
        @click="start"
      >
        <span v-if="starting">选股中…</span>
        <span v-else>随机选股并开始训练</span>
      </button>
      <button class="btn btn--plain btn--block" style="margin-top: var(--sp-2xl);" @click="reset">
        恢复默认
      </button>
    </section>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { showToast, showSuccessToast } from 'vant'
import { trainApi, stocksApi } from '@/api/modules'
import { useTrainAuthStore } from '@/stores/trainAuth'
import { calcSessionCost, money } from '@/utils/trainFee'

const router = useRouter()
const auth = useTrainAuthStore()

const rangePreset = ref('1y')
const starting = ref(false)
const options = reactive({ industries: [] })

function fmtLocal(d) {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

const today = new Date()
const oneYearAgo = new Date(today)
oneYearAgo.setFullYear(today.getFullYear() - 1)

const form = reactive({
  start_date: fmtLocal(oneYearAgo),
  end_date: fmtLocal(today),
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

const sessionCost = computed(() =>
  calcSessionCost(form.start_date, form.end_date, form.initial_cash)
)

const formValid = computed(() => {
  if (!form.start_date || !form.end_date) return false
  if (form.start_date >= form.end_date) return false
  if (form.initial_cash < 10_000) return false
  return true
})

function applyRangePreset(v) {
  if (!v) return
  const years = { '1y': 1, '3y': 3, '5y': 5 }[v] || 1
  const end = new Date()
  const start = new Date(end)
  start.setFullYear(end.getFullYear() - years)
  form.start_date = fmtLocal(start)
  form.end_date = fmtLocal(end)
}

function reset() {
  rangePreset.value = '1y'
  Object.assign(form, {
    start_date: fmtLocal(oneYearAgo),
    end_date: fmtLocal(today),
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

async function loadOptions() {
  try {
    const [ind, w] = await Promise.all([
      stocksApi.industries().catch(() => ({ items: [] })),
      trainApi.wallet().catch(() => ({ balance: 0 })),
    ])
    options.industries = ind?.items?.map((i) => i.industry) || []
    auth.setWallet(w || {})
  } catch { /* silent */ }
}

async function start() {
  if (!formValid.value) {
    return showToast('日期/资金无效')
  }
  starting.value = true
  try {
    const res = await trainApi.startSession({ ...form })
    showSuccessToast(`已选中 ${res.name} (${res.code})`)
    router.replace(`/trade/${res.id}`)
  } catch (e) {
    showToast({ type: 'fail', message: e.message || '发起训练失败' })
  } finally {
    starting.value = false
  }
}

onMounted(loadOptions)
</script>

<style scoped>
.setup__intro { padding: var(--sp-4xl) var(--sp-4xl) var(--sp-3xl); }
.setup__intro h2 {
  margin: 0 0 var(--sp-2xl);
  font-size: 0.40rem;
  font-weight: 700;
}
.setup__intro p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 0.26rem;
  line-height: 1.5;
}

.fee-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  column-gap: var(--sp-3xl);
  row-gap: 0;
}
.field--inline .field__label { flex: 1; }

.cost {
  background: var(--color-primary-lighter);
  border-radius: var(--radius-md);
  padding: var(--sp-3xl) var(--sp-4xl);
  margin-bottom: var(--sp-4xl);
}
.cost__main {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: var(--sp-2xl);
}
.cost__lbl { font-size: 0.26rem; color: var(--text-secondary); }
.cost__value { font-size: 0.36rem; font-weight: 700; color: var(--color-primary); }
.cost__sub { font-size: 0.22rem; color: var(--text-secondary); }
</style>
