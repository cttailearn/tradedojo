<template>
  <div>
    <div class="page-card">
      <el-tabs v-model="mode">
        <el-tab-pane label="单股回测" name="single" />
        <el-tab-pane label="组合回测" name="portfolio" />
      </el-tabs>

      <!-- 单股回测表单 -->
      <el-form v-if="mode === 'single'" :model="form" label-width="100px">
        <el-row :gutter="16">
          <el-col :span="8"><el-form-item label="股票代码"><el-input v-model="form.code" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="策略">
            <el-select v-model="form.strategy">
              <el-option label="SMA 双均线" value="sma" />
              <el-option label="动量策略" value="momentum" />
              <el-option label="买入持有" value="buy_hold" />
            </el-select>
          </el-form-item></el-col>
          <el-col :span="8"><el-form-item label="初始资金">
            <el-input-number v-model="form.cash" :min="10000" :step="10000" />
          </el-form-item></el-col>
          <el-col :span="8"><el-form-item label="起始日期">
            <el-date-picker v-model="form.start" type="date" value-format="YYYY-MM-DD" />
          </el-form-item></el-col>
          <el-col :span="8"><el-form-item label="结束日期">
            <el-date-picker v-model="form.end" type="date" value-format="YYYY-MM-DD" />
          </el-form-item></el-col>
          <el-col :span="8"><el-form-item label="复权方式">
            <el-radio-group v-model="form.adjust">
              <el-radio-button value="qfq">前复权</el-radio-button>
              <el-radio-button value="hfq">后复权</el-radio-button>
            </el-radio-group>
          </el-form-item></el-col>
          <template v-if="form.strategy === 'sma'">
            <el-col :span="8"><el-form-item label="快线">
              <el-input-number v-model="form.fast" :min="2" :max="60" />
            </el-form-item></el-col>
            <el-col :span="8"><el-form-item label="慢线">
              <el-input-number v-model="form.slow" :min="5" :max="250" />
            </el-form-item></el-col>
          </template>
          <template v-if="form.strategy === 'momentum'">
            <el-col :span="8"><el-form-item label="回看期">
              <el-input-number v-model="form.lookback" :min="5" :max="120" />
            </el-form-item></el-col>
            <el-col :span="8"><el-form-item label="动量阈值">
              <el-input-number v-model="form.thresh" :min="0.01" :max="0.5" :step="0.01" :precision="2" />
            </el-form-item></el-col>
            <el-col :span="8"><el-form-item label="止损">
              <el-input-number v-model="form.stop_loss" :min="0.01" :max="0.5" :step="0.01" :precision="2" />
            </el-form-item></el-col>
            <el-col :span="8"><el-form-item label="止盈">
              <el-input-number v-model="form.take_profit" :min="0.05" :max="1.0" :step="0.05" :precision="2" />
            </el-form-item></el-col>
          </template>
        </el-row>
        <el-form-item>
          <el-button type="primary" :loading="running" @click="runSingle">
            <el-icon><VideoPlay /></el-icon>开始回测
          </el-button>
        </el-form-item>
      </el-form>

      <!-- 组合回测表单 -->
      <el-form v-else :model="pfForm" label-width="100px">
        <el-form-item label="股票代码">
          <el-input v-model="pfForm.codes" placeholder="逗号分隔,如 000001,600000,600519" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="8"><el-form-item label="策略">
            <el-select v-model="pfForm.strategy">
              <el-option label="SMA 双均线" value="sma" />
              <el-option label="动量策略" value="momentum" />
            </el-select>
          </el-form-item></el-col>
          <el-col :span="8"><el-form-item label="起始日期">
            <el-date-picker v-model="pfForm.start" type="date" value-format="YYYY-MM-DD" />
          </el-form-item></el-col>
          <el-col :span="8"><el-form-item label="结束日期">
            <el-date-picker v-model="pfForm.end" type="date" value-format="YYYY-MM-DD" />
          </el-form-item></el-col>
          <el-col :span="8"><el-form-item label="初始资金">
            <el-input-number v-model="pfForm.cash" :min="10000" :step="10000" />
          </el-form-item></el-col>
          <el-col :span="8"><el-form-item label="快线">
            <el-input-number v-model="pfForm.fast" :min="2" :max="60" />
          </el-form-item></el-col>
          <el-col :span="8"><el-form-item label="慢线">
            <el-input-number v-model="pfForm.slow" :min="5" :max="250" />
          </el-form-item></el-col>
        </el-row>
        <el-form-item>
          <el-button type="primary" :loading="running" @click="runPortfolio">
            <el-icon><VideoPlay /></el-icon>开始组合回测
          </el-button>
        </el-form-item>
      </el-form>
    </div>

    <div class="page-card" v-if="result">
      <h3 class="page-title">回测结果</h3>
      <div class="metric-grid">
        <div class="metric-item">
          <div class="label">期末资金</div>
          <div class="value">{{ fmtMoney(result.final_value) }}</div>
        </div>
        <div class="metric-item" :class="result.pnl >= 0 ? 'green' : 'red'">
          <div class="label">总盈亏</div>
          <div class="value">{{ fmtMoney(result.pnl) }} ({{ result.pnl_pct.toFixed(2) }}%)</div>
        </div>
        <div class="metric-item" :class="result.annual_return >= 0 ? 'green' : 'red'">
          <div class="label">年化收益</div>
          <div class="value">{{ result.annual_return.toFixed(2) }}%</div>
        </div>
        <div class="metric-item orange">
          <div class="label">最大回撤</div>
          <div class="value">{{ result.max_drawdown.toFixed(2) }}%</div>
        </div>
        <div class="metric-item">
          <div class="label">夏普比率</div>
          <div class="value">{{ (result.sharpe || 0).toFixed(3) }}</div>
        </div>
        <div class="metric-item">
          <div class="label">SQN</div>
          <div class="value">{{ (result.sqn || 0).toFixed(2) }}</div>
        </div>
      </div>
    </div>

    <div class="page-card" v-if="portfolioItems.length">
      <h3 class="page-title">组合汇总 ({{ portfolioItems.length }} 只)</h3>
      <el-table :data="portfolioItems" stripe>
        <el-table-column prop="code" label="代码" width="100" />
        <el-table-column label="收益率" align="right">
          <template #default="{ row }">
            <span :class="(row.pnl_pct || 0) >= 0 ? 'up' : 'down'">
              {{ (row.pnl_pct || 0).toFixed(2) }}%
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="annual_return" label="年化%" align="right" />
        <el-table-column prop="max_drawdown" label="最大回撤%" align="right" />
        <el-table-column prop="sharpe" label="夏普" align="right" />
        <el-table-column prop="final_value" label="期末资金" align="right" />
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { backtestApi } from '@/api/modules'

const route = useRoute()
const mode = ref('single')
const running = ref(false)
const result = ref(null)
const portfolioItems = ref([])

const form = reactive({
  code: '000001', strategy: 'sma', cash: 100000,
  start: '2022-01-01', end: '2024-12-31', adjust: 'qfq',
  fast: 5, slow: 20, lookback: 20, thresh: 0.05, stop_loss: 0.08, take_profit: 0.20,
})

const pfForm = reactive({
  codes: '000001,600000,600519', strategy: 'sma', cash: 100000,
  start: '2022-01-01', end: '2024-12-31', adjust: 'qfq',
  fast: 5, slow: 20, lookback: 20,
})

function fmtMoney(v) {
  if (v == null) return '-'
  return Number(v).toLocaleString('zh-CN', {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  })
}

async function runSingle() {
  running.value = true
  result.value = null
  portfolioItems.value = []
  try {
    const r = await backtestApi.single(form)
    result.value = r.data
    ElMessage.success('回测完成')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    running.value = false
  }
}

async function runPortfolio() {
  running.value = true
  result.value = null
  portfolioItems.value = []
  try {
    const r = await backtestApi.portfolio(pfForm)
    portfolioItems.value = r.data.items || []
    ElMessage.success(`完成 ${portfolioItems.value.length} 只股票回测`)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    running.value = false
  }
}

onMounted(() => {
  if (route.query.code) form.code = route.query.code
})
</script>