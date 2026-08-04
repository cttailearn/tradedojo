<template>
  <div class="setup">
    <div class="page-card">
      <h3 class="page-title">发起一次 K 线交易训练</h3>
      <p class="muted">
        设置下面的参数,系统会从已有 A 股中<b>随机挑一只</b>符合条件的历史股票,
        并把<b>训练开始日</b>之前的 {{ form.lookback_months }} 个月数据全部展示出来供你分析,
        此后只能逐日推进,体验真实交易。
      </p>

      <el-form :model="form" label-width="160px" label-position="right" v-loading="loadingOptions">
        <el-divider content-position="left">时间窗</el-divider>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="时间窗长度">
              <el-radio-group v-model="form.range_years" size="default">
                <el-radio-button :value="1">1 年内</el-radio-button>
                <el-radio-button :value="3">3 年内</el-radio-button>
                <el-radio-button :value="5">5 年内</el-radio-button>
              </el-radio-group>
              <div class="hint" style="margin-top:6px;">
                系统将在此时间窗内<b>随机</b>挑一天作为训练开始日(提交时确定),结束日固定为今天
              </div>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="提供历史回看月数">
              <el-input-number v-model="form.lookback_months" :min="1" :max="36" />
              <span class="hint">展示训练开始日之前 N 个月的数据(默认 6)</span>
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider content-position="left">资金 & 交易规则</el-divider>
        <el-row :gutter="16">
          <el-col :span="24">
            <el-form-item label="初始资金 (元)">
              <el-input-number
                v-model="form.initial_cash"
                :min="1000"
                :step="10000"
                :max="maxInitialCash"
                style="max-width: 240px;"
              />
              <span class="hint">
                可调整,上限 = 钱包余额(2026-07-31 起训练免费)·
                当前上限 <b>¥ {{ money(maxInitialCash) }}</b>
              </span>
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
              <div style="line-height:1.8;">
                <div>
                  <b>本次训练固定扣 ¥ {{ sessionCost.toFixed(2) }}</b> 元
                  <span style="color:#909399;font-size:12px;margin-left:8px;">
                    (统一价,与时间窗、初始资金无关)
                  </span>
                </div>
                <div v-if="wallet.balance < sessionCost" style="color: #f56c6c;">
                  余额不足 (当前余额 ¥ {{ money(wallet.balance) }}),
                  <el-link type="warning" @click="$router.push('/train/wallet')">去充值</el-link>
                </div>
                <div v-else style="color:#67c23a;">
                  扣费后余额 ¥ {{ money(wallet.balance - sessionCost) }}
                </div>
              </div>
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
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { trainApi } from '@/api/modules'
import { calcSessionCost } from '@/utils/trainFee'

const router = useRouter()
const loadingOptions = ref(false)
const starting = ref(false)
const wallet = ref({ balance: 0 })
const options = reactive({ industries: [] })

// 用本地时区格式化,避免 toISOString UTC 跨天
function fmtLocal(d) {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

// 在 [start, end] 区间内随机选一天(包含两端)
function randomDateBetween(startStr, endStr) {
  const sd = new Date(startStr).getTime()
  const ed = new Date(endStr).getTime()
  if (!isFinite(sd) || !isFinite(ed) || ed <= sd) return startStr
  const r = sd + Math.floor(Math.random() * (ed - sd + 86400000))
  const d = new Date(Math.min(r, ed))
  return fmtLocal(d)
}

// 在 [end - years, end] 区间内随机生成 start_date
function rollRandomStart(years, endStr) {
  const end = new Date(endStr)
  const earliest = new Date(end)
  earliest.setFullYear(end.getFullYear() - years)
  // 起点:最早可训练开始日 = end - years;终点:end 本身(包含今天)
  return randomDateBetween(fmtLocal(earliest), endStr)
}

// 固定 end_date = 今天(每次刷新页面更新一次)
function todayLocal() {
  return fmtLocal(new Date())
}

const form = reactive({
  // 时间窗控制:由用户选择窗口长度,start_date 提交时再随机
  range_years: 1,
  start_date: '',   // 提交时随机生成(写入 session)
  end_date: todayLocal(),
  // 与后端 TrainingSetupRequest 默认值保持一致:6 (后端 Field(6, ...))
  lookback_months: 6,
  initial_cash: 0,  // 由 wallet.balance - sessionCost 注入(后端同样会替换)
  commission_rate: 0.0003,
  min_commission: 5,
  stamp_tax: 0.001,
  transfer_fee: 0.00001,
  allow_chinext: false,
  allow_kcb: false,
  allow_bj: false,
  allow_st: false,
  industry: null,
  market: null,
  keyword: '',
})

// 当前随机 start_date(不再展示给用户,提交时直接用 + 刷新)
const previewStartDate = ref(rollRandomStart(form.range_years, form.end_date))

// 监听 range_years 变化 → 立即重新随机,提交时也会再随机一次
watch(() => form.range_years, () => {
  previewStartDate.value = rollRandomStart(form.range_years, form.end_date)
})

// 训练费:已取消(2026-07-31 起,utils/trainFee.js 与后端共享,恒为 0)
const sessionCost = computed(() => calcSessionCost())

// 上限 = 钱包余额(2026-07-31 起训练免费,不再保留训练费余量)
const maxInitialCash = computed(() => {
  const w = Number(wallet.value?.balance || 0)
  return Math.max(0, w)
})

// 表单 initial_cash 默认填到上限
watch(maxInitialCash, (v) => {
  if (!form.initial_cash || form.initial_cash > v) {
    form.initial_cash = v
  }
}, { immediate: true })

const formValid = computed(() => {
  if (!form.range_years || form.range_years < 1) return false
  if (form.initial_cash < 1000 || form.initial_cash > maxInitialCash.value) return false
  return true
})

function money(v) {
  return Number(v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function loadOptions() {
  loadingOptions.value = true
  try {
    const [ind, w] = await Promise.all([
      // 2026-08-04 P0-3 修复: 改用 train 端 industries 端点。
      // 旧版 stocksApi.industries() 强制 require_admin, 训练用户没 admin token
      // → 401 → 前端 axios 拦截器误判为 train auth 失败 → 用户被踢回登录页。
      trainApi.industries().catch(() => ({ items: [] })),
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

function reset() {
  Object.assign(form, {
    range_years: 1,
    end_date: todayLocal(),
    lookback_months: 6,
    initial_cash: 0,
    commission_rate: 0.0003,
    min_commission: 5,
    stamp_tax: 0.001,
    transfer_fee: 0.00001,
    allow_chinext: false,
    allow_kcb: false,
    allow_bj: false,
    allow_st: false,
    industry: null,
    market: null,
    keyword: '',
  })
  previewStartDate.value = rollRandomStart(form.range_years, form.end_date)
}

async function start() {
  if (!formValid.value) {
    return ElMessage.warning('参数无效,请检查')
  }
  // 提交时再次随机 start_date,并把随机结果回填到 preview(用户能看到最终选了哪天)
  const finalStart = rollRandomStart(form.range_years, form.end_date)
  previewStartDate.value = finalStart

  starting.value = true
  try {
    const payload = {
      ...form,
      // 初始资金 = 用户编辑值(受 wallet-10 上限限制);后端会再次校验
      initial_cash: Number(form.initial_cash || maxInitialCash.value),
      start_date: finalStart,
      end_date: form.end_date,
    }
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
