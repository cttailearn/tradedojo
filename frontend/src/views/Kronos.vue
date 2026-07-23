<template>
  <div>
    <!-- 模型状态卡片 -->
    <el-row :gutter="16">
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-icon" :class="status.loaded ? 'green' : 'gray'">
            <el-icon><Cpu /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-label">模型状态</div>
            <div class="stat-value">
              <el-tag :type="status.loaded ? 'success' : 'info'" size="large">
                {{ status.loaded ? '已加载' : '未加载' }}
              </el-tag>
            </div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-icon blue"><el-icon><Box /></el-icon></div>
          <div class="stat-info">
            <div class="stat-label">当前模型</div>
            <div class="stat-value">{{ status.model_name || '-' }}</div>
            <div class="stat-sub">{{ status.device || '-' }}</div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-icon purple"><el-icon><DataLine /></el-icon></div>
          <div class="stat-info">
            <div class="stat-label">预测模式</div>
            <div class="stat-value" style="font-size:16px;">
              {{ mode === 'simple' ? '简单预测' : '回测对比' }}
            </div>
            <div class="stat-sub">{{ mode === 'backtest' ? '对比实际值' : '预测未来' }}</div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-icon orange"><el-icon><Lightning /></el-icon></div>
          <div class="stat-info">
            <div class="stat-label">上次耗时</div>
            <div class="stat-value">{{ lastElapsed ? lastElapsed + ' ms' : '-' }}</div>
            <div class="stat-sub">{{ lastPredLen ? `预测 ${lastPredLen} 天` : '' }}</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 控制面板 -->
    <div class="page-card">
      <h3 class="page-title">
        <el-icon><Setting /></el-icon>预测参数
        <el-radio-group v-model="mode" style="margin-left:auto;">
          <el-radio-button value="simple">简单预测</el-radio-button>
          <el-radio-button value="backtest">回测对比</el-radio-button>
        </el-radio-group>
      </h3>

      <el-form :model="form" label-width="120px" style="max-width:880px;">
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="股票代码">
              <el-input v-model="form.code" placeholder="如 000001" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="复权方式">
              <el-radio-group v-model="form.adjust">
                <el-radio-button value="qfq">前复权</el-radio-button>
                <el-radio-button value="hfq">后复权</el-radio-button>
              </el-radio-group>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="模型">
              <el-select v-model="form.model" style="width:160px;">
                <el-option v-for="m in status.models" :key="m" :label="m" :value="m" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="历史窗口(天)">
              <el-input-number v-model="form.lookback" :min="30" :max="512" :step="30" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="预测长度(天)">
              <el-input-number v-model="form.pred_len" :min="1" :max="120" :step="5" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="温度">
              <el-input-number v-model="form.temperature" :min="0.1" :max="2.0" :step="0.1" :precision="1" />
            </el-form-item>
          </el-col>
        </el-row>

        <!-- 回测模式专属参数 -->
        <template v-if="mode === 'backtest'">
          <el-divider content-position="left">
            <el-icon><Aim /></el-icon> 回测时间切分
          </el-divider>
          <el-alert type="info" :closable="false" show-icon style="margin-bottom:12px;">
            <template #title>回测说明</template>
            使用「训练截止日」之前的数据预测之后 M 天,与数据库中的真实 K 线对比,计算准确率。
          </el-alert>
          <el-row :gutter="16">
            <el-col :span="8">
              <el-form-item label="训练截止日">
                <el-date-picker v-model="form.train_end" type="date" value-format="YYYY-MM-DD"
                                placeholder="选择历史截止日" style="width:100%;" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="对比实际值">
                <el-switch v-model="form.compare_actual"
                           active-text="开启" inactive-text="关闭" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="采样次数">
                <el-input-number v-model="form.sample_count" :min="1" :max="10" />
                <span style="margin-left:8px; color:#909399; font-size:12px;">多次取均值</span>
              </el-form-item>
            </el-col>
          </el-row>
          <el-row>
            <el-col :span="8">
              <el-form-item label="top_p">
                <el-input-number v-model="form.top_p" :min="0.0" :max="1.0" :step="0.05" :precision="2" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-button :loading="loadingDates" @click="useRecentPreset" plain>
                <el-icon><RefreshRight /></el-icon>
                推荐:用最近 1 个月数据
              </el-button>
            </el-col>
          </el-row>
        </template>

        <el-form-item>
          <el-button v-if="!status.loaded" type="warning" :loading="loading" @click="loadModel">
            <el-icon><Download /></el-icon>加载模型
          </el-button>
          <el-button v-else type="danger" plain :loading="loading" @click="unloadModel">
            <el-icon><Unlock /></el-icon>卸载模型
          </el-button>

          <el-button type="primary" :loading="predicting" :disabled="!status.loaded" @click="runPredict">
            <el-icon><MagicStick /></el-icon>{{ mode === 'backtest' ? '运行回测' : '开始预测' }}
          </el-button>

          <el-button @click="loadStatus">
            <el-icon><Refresh /></el-icon>刷新状态
          </el-button>
        </el-form-item>
      </el-form>

      <el-alert v-if="!status.available" type="warning" :closable="false" show-icon style="margin-top:12px;">
        <template #title>Kronos 不可用</template>
        <div>{{ status.error || '请检查 torch / vendor/Kronos 是否就绪' }}</div>
      </el-alert>
    </div>

    <!-- 预测回测准确率 -->
    <div class="page-card" v-if="result && result.metrics">
      <h3 class="page-title">
        <el-icon><DataAnalysis /></el-icon>回测准确率
        <el-tag style="margin-left:12px;" type="success">对比 {{ result.metrics.compared_days }} 个交易日</el-tag>
        <span style="margin-left:auto; color:#909399; font-size:12px;">
          {{ result.metrics.pred_start }} → {{ result.metrics.pred_end }}
        </span>
      </h3>
      <el-row :gutter="16">
        <el-col :span="6">
          <div class="metric-item" :class="result.metrics.direction_accuracy >= 55 ? 'green' : result.metrics.direction_accuracy >= 45 ? 'orange' : 'red'">
            <div class="label">方向正确率</div>
            <div class="value">{{ result.metrics.direction_accuracy }}%</div>
            <div style="font-size:12px;color:#909399;margin-top:4px;">涨/跌方向命中</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="metric-item">
            <div class="label">MAE(平均绝对误差)</div>
            <div class="value">{{ result.metrics.mae.toFixed(3) }}</div>
            <div style="font-size:12px;color:#909399;margin-top:4px;">close 误差(元)</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="metric-item" :class="result.metrics.mape <= 3 ? 'green' : result.metrics.mape <= 6 ? 'orange' : 'red'">
            <div class="label">MAPE(平均百分比误差)</div>
            <div class="value">{{ result.metrics.mape.toFixed(2) }}%</div>
            <div style="font-size:12px;color:#909399;margin-top:4px;">相对误差</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="metric-item">
            <div class="label">对比天数</div>
            <div class="value">{{ result.metrics.compared_days }}</div>
            <div style="font-size:12px;color:#909399;margin-top:4px;">共同交易日</div>
          </div>
        </el-col>
      </el-row>
    </div>

    <!-- 预测结果图表(始终渲染,只是内容变化) -->
    <div class="page-card" v-show="result">
      <h3 class="page-title">
        <el-icon><TrendCharts /></el-icon>
        {{ result?.mode === 'backtest' ? '回测结果(预测 vs 实际)' : '预测结果' }}
        <el-tag v-if="result" style="margin-left:12px;">
          {{ result.code }} · 预测 {{ result.pred_len }} 天
        </el-tag>
        <span v-if="result" style="margin-left:auto; font-size:12px; color:#909399;">
          模型: {{ result.model }} · 设备: {{ result.device }} · 耗时: {{ result.elapsed_ms }} ms
        </span>
      </h3>

      <div ref="chartRef" class="kline-chart" style="height:500px;"></div>

      <!-- 简单模式的统计 -->
      <el-row :gutter="16" style="margin-top:16px;" v-if="result && result.mode === 'simple'">
        <el-col :span="6">
          <div class="metric-item">
            <div class="label">历史最近收盘</div>
            <div class="value">{{ stats.lastClose }}</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="metric-item" :class="parseFloat(stats.predChange) >= 0 ? 'green' : 'red'">
            <div class="label">预测期间涨跌幅</div>
            <div class="value">{{ stats.predChange }}%</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="metric-item">
            <div class="label">预测最高</div>
            <div class="value">{{ stats.predHigh }}</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="metric-item">
            <div class="label">预测最低</div>
            <div class="value">{{ stats.predLow }}</div>
          </div>
        </el-col>
      </el-row>
    </div>

    <!-- 数据明细(回测模式显示对比表) -->
    <div class="page-card" v-if="result && result.mode === 'backtest' && result.actual && result.actual.length">
      <h3 class="page-title">回测数据明细(预测 vs 实际)</h3>
      <el-table :data="backtestRows" stripe max-height="420">
        <el-table-column prop="trade_date" label="日期" width="120" fixed />
        <el-table-column label="预测 收盘" align="right">
          <template #default="{ row }">{{ Number(row.close_pred).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="实际 收盘" align="right">
          <template #default="{ row }">{{ Number(row.close_actual).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="误差(元)" align="right">
          <template #default="{ row }">
            <span :class="Math.abs(row.error) < 0.3 ? 'up' : 'down'">
              {{ row.error > 0 ? '+' : '' }}{{ row.error.toFixed(3) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="误差 %" align="right">
          <template #default="{ row }">
            <span :class="Math.abs(row.error_pct) < 3 ? 'up' : 'down'">
              {{ row.error_pct > 0 ? '+' : '' }}{{ row.error_pct.toFixed(2) }}%
            </span>
          </template>
        </el-table-column>
        <el-table-column label="预测方向" align="center">
          <template #default="{ row }">
            <el-tag :type="row.dir_pred === 1 ? 'danger' : (row.dir_pred === -1 ? 'success' : 'info')" size="small">
              {{ row.dir_pred === 1 ? '↑ 涨' : row.dir_pred === -1 ? '↓ 跌' : '— 平' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="实际方向" align="center">
          <template #default="{ row }">
            <el-tag :type="row.dir_actual === 1 ? 'danger' : (row.dir_actual === -1 ? 'success' : 'info')" size="small">
              {{ row.dir_actual === 1 ? '↑ 涨' : row.dir_actual === -1 ? '↓ 跌' : '— 平' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="方向命中" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.hit" type="success" size="small">✓</el-tag>
            <el-tag v-else type="danger" size="small">✗</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 简单模式: 预测明细表 -->
    <div class="page-card" v-if="result && result.mode === 'simple' && result.prediction.length">
      <h3 class="page-title">预测数据明细</h3>
      <el-table :data="result.prediction" stripe max-height="380">
        <el-table-column prop="trade_date" label="日期" width="120" fixed />
        <el-table-column label="开盘" align="right">
          <template #default="{ row }">{{ Number(row.open).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="最高" align="right">
          <template #default="{ row }">{{ Number(row.high).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="最低" align="right">
          <template #default="{ row }">{{ Number(row.low).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="收盘" align="right">
          <template #default="{ row }">{{ Number(row.close).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="成交量" align="right">
          <template #default="{ row }">{{ Number(row.volume).toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="vs 首日" align="right">
          <template #default="{ row }">
            <span :class="(row.close - result.prediction[0].close) >= 0 ? 'up' : 'down'">
              {{ (((row.close - result.prediction[0].close) / result.prediction[0].close) * 100).toFixed(2) }}%
            </span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 说明 -->
    <div class="page-card">
      <h3 class="page-title"><el-icon><InfoFilled /></el-icon>关于 Kronos + 回测</h3>
      <el-alert type="info" :closable="false" show-icon>
        <template #title>开源金融时序大模型</template>
        <div style="line-height:1.8;">
          <strong>Kronos</strong> 是首个面向金融 K 线的开源基础模型,来自
          <a href="https://github.com/shiyu-coder/Kronos" target="_blank">shiyu-coder/Kronos</a>。<br>
          • <strong>简单预测</strong>:用最近 N 天历史,预测未来 M 天(无对比基准)<br>
          • <strong>回测对比</strong>:选定历史截止日,用截止日之前的数据预测之后 M 天,与真实 K 线对比算准确率<br>
          • 准确率指标:<strong>方向正确率</strong>(>55% 较优)、<strong>MAE</strong>(越小越好)、<strong>MAPE</strong>(<3% 优秀)<br>
          • 预测结果<strong>仅供参考</strong>,不构成投资建议
        </div>
      </el-alert>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as echarts from 'echarts'
import { kronosApi } from '@/api/modules'

const status = ref({
  available: false, loaded: false,
  model_name: null, device: null,
  models: [], default: 'kronos-mini',
})
const result = ref(null)
const lastElapsed = ref(0)
const lastPredLen = ref(0)
const loading = ref(false)
const loadingDates = ref(false)
const predicting = ref(false)
const mode = ref('backtest')  // 默认回测模式
const chartRef = ref(null)
let chart = null

const form = reactive({
  code: '000001',
  adjust: 'qfq',
  model: 'kronos-base',
  lookback: 200,
  pred_len: 20,
  temperature: 1.0,
  top_p: 0.9,
  sample_count: 1,
  train_end: '',
  compare_actual: true,
})

const stats = ref({
  lastClose: '-', predChange: '-', predHigh: '-', predLow: '-',
})

const backtestRows = computed(() => {
  if (!result.value || !result.value.actual || !result.value.prediction) return []
  const predMap = {}
  for (const p of result.value.prediction) {
    predMap[p.trade_date] = p
  }
  const rows = []
  let prevPred = null, prevActual = null
  for (const a of result.value.actual) {
    const p = predMap[a.trade_date]
    if (!p) continue
    const cp = Number(p.close)
    const ca = Number(a.close)
    const error = cp - ca
    const error_pct = (error / ca) * 100
    const dir_pred = prevPred == null ? 0 : (cp > prevPred ? 1 : (cp < prevPred ? -1 : 0))
    const dir_actual = prevActual == null ? 0 : (ca > prevActual ? 1 : (ca < prevActual ? -1 : 0))
    rows.push({
      trade_date: a.trade_date,
      close_pred: cp, close_actual: ca,
      error, error_pct, dir_pred, dir_actual,
      hit: dir_pred !== 0 && dir_pred === dir_actual,
    })
    prevPred = cp
    prevActual = ca
  }
  return rows
})

// 安全地初始化/重置图表(图表 DOM 永远存在,只是 v-show 隐藏)
function ensureChart() {
  if (chart) return chart
  if (!chartRef.value) return null
  chart = echarts.init(chartRef.value)
  window.addEventListener('resize', resize)
  return chart
}

function resize() { chart && chart.resize() }

async function loadStatus() {
  try { status.value = await kronosApi.status() }
  catch (e) { ElMessage.error(e.message) }
}

async function loadModel() {
  loading.value = true
  try {
    ElMessage.info('开始加载模型...')
    const s = await kronosApi.load(form.model)
    status.value = s
    ElMessage.success(`模型 ${s.model_name} 已加载`)
  } catch (e) {
    ElMessage.error(e.message)
  } finally { loading.value = false }
}

async function unloadModel() {
  loading.value = true
  try {
    await kronosApi.unload()
    await loadStatus()
    ElMessage.success('已卸载')
  } catch (e) { ElMessage.error(e.message) }
  finally { loading.value = false }
}

function useRecentPreset() {
  loadingDates.value = true
  try {
    const now = new Date()
    // 训练截止日 = 1 个月前
    const trainEnd = new Date(now.getFullYear(), now.getMonth() - 1, now.getDate())
    form.train_end = trainEnd.toISOString().slice(0, 10)
    form.compare_actual = true
    ElMessage.success(`已设置:训练截止 ${form.train_end}`)
  } finally {
    loadingDates.value = false
  }
}

async function runPredict() {
  if (!form.code) return ElMessage.warning('请输入股票代码')

  if (mode.value === 'backtest' && !form.train_end) {
    return ElMessage.warning('回测模式必须选择「训练截止日」,或点上方"推荐"按钮自动填')
  }

  predicting.value = true
  try {
    // 只发送 API 真正需要的字段(避免 model 等前端专属字段触发 422)
    const payload = {
      code: form.code,
      lookback: form.lookback,
      pred_len: form.pred_len,
      adjust: form.adjust,
      temperature: form.temperature,
      top_p: form.top_p,
      sample_count: form.sample_count,
    }
    if (mode.value === 'backtest') {
      payload.train_end = form.train_end
      payload.compare_actual = form.compare_actual
    }
    const r = await kronosApi.predict(payload)
    result.value = r
    lastElapsed.value = r.elapsed_ms
    lastPredLen.value = r.pred_len

    // 简单模式统计
    if (r.mode === 'simple' && r.history.length) {
      const last = r.history[r.history.length - 1]
      const first = r.prediction[0]
      const last2 = r.prediction[r.prediction.length - 1]
      const allHigh = Math.max(...r.prediction.map(x => Number(x.high)))
      const allLow = Math.min(...r.prediction.map(x => Number(x.low)))
      stats.value = {
        lastClose: Number(last.close).toFixed(2),
        predChange: (((Number(last2.close) - Number(last.close)) / Number(last.close)) * 100).toFixed(2),
        predHigh: Number(allHigh).toFixed(2),
        predLow: Number(allLow).toFixed(2),
      }
    }

    ElMessage.success(
      r.mode === 'backtest'
        ? `回测完成:方向正确率 ${r.metrics?.direction_accuracy}%`
        : `预测完成`
    )
    await nextTick()
    renderChart()
  } catch (e) {
    ElMessage.error(e.message)
  } finally { predicting.value = false }
}

function renderChart() {
  const c = ensureChart()
  if (!c) return
  if (!result.value) {
    c.clear()
    return
  }
  const isBacktest = result.value.mode === 'backtest'
  const hist = result.value.history || []
  const pred = result.value.prediction || []
  const actual = result.value.actual || []

  const histDates = hist.map(r => r.trade_date)
  const predDates = pred.map(r => r.trade_date)
  const actualDates = actual.map(r => r.trade_date)
  // 合并日期,去重
  const allDatesSet = new Set([...histDates, ...predDates, ...actualDates])
  const allDates = Array.from(allDatesSet).sort()

  // 历史 OHLC
  const histMap = {}; hist.forEach(r => histMap[r.trade_date] = r)
  const histOHLC = allDates.map(d => {
    const r = histMap[d]
    return r ? [Number(r.open), Number(r.close), Number(r.low), Number(r.high)] : '-'
  })

  // 预测 OHLC(虚线显示)
  const predMap = {}; pred.forEach(r => predMap[r.trade_date] = r)
  const predOHLC = allDates.map(d => {
    const r = predMap[d]
    return r ? [Number(r.open), Number(r.close), Number(r.low), Number(r.high)] : '-'
  })

  // 实际值(回测模式)
  const actualMap = {}; actual.forEach(r => actualMap[r.trade_date] = r)
  const actualOHLC = allDates.map(d => {
    const r = actualMap[d]
    return r ? [Number(r.open), Number(r.close), Number(r.low), Number(r.high)] : '-'
  })

  // 收盘价折线
  const histClose = allDates.map(d => {
    const r = histMap[d]
    return r ? Number(r.close) : null
  })
  const predClose = allDates.map(d => {
    const r = predMap[d]
    return r ? Number(r.close) : null
  })
  const actualClose = allDates.map(d => {
    const r = actualMap[d]
    return r ? Number(r.close) : null
  })

  const series = [
    {
      name: '历史K线', type: 'candlestick', data: histOHLC,
      itemStyle: { color: '#f56c6c', color0: '#67c23a', borderColor: '#f56c6c', borderColor0: '#67c23a' },
    },
  ]
  if (isBacktest && actual.length) {
    series.push({
      name: '实际K线', type: 'candlestick', data: actualOHLC,
      itemStyle: { color: '#909399', color0: '#c0c4cc', borderColor: '#606266', borderColor0: '#909399' },
    })
  }
  series.push({
    name: '预测K线', type: 'candlestick', data: predOHLC,
    itemStyle: { color: 'transparent', color0: 'transparent', borderColor: '#E6A23C', borderColor0: '#E6A23C' },
  })
  series.push({
    name: '历史收盘', type: 'line', data: histClose, smooth: true,
    lineStyle: { width: 1.5, color: '#409EFF' }, showSymbol: false,
  })
  if (isBacktest && actual.length) {
    series.push({
      name: '实际收盘', type: 'line', data: actualClose, smooth: true,
      lineStyle: { width: 1.5, color: '#606266', type: 'solid' }, showSymbol: false,
    })
  }
  series.push({
    name: '预测收盘', type: 'line', data: predClose, smooth: true,
    lineStyle: { width: 2, color: '#E6A23C', type: 'dashed' },
    showSymbol: true, symbolSize: 6, itemStyle: { color: '#E6A23C' },
  })

  c.setOption({
    title: {
      text: isBacktest ? `${result.value.code} 回测对比` : `${result.value.code} K线预测`,
      subtext: isBacktest
        ? `训练截止 ${form.train_end} · 预测 ${result.value.pred_len} 天 · 准确率 ${result.value.metrics?.direction_accuracy}%`
        : `历史 ${result.value.lookback} 天 + 预测 ${result.value.pred_len} 天`,
      left: 'center',
    },
    legend: {
      data: isBacktest
        ? ['历史K线', '实际K线', '预测K线', '历史收盘', '实际收盘', '预测收盘']
        : ['历史K线', '预测K线', '历史收盘', '预测收盘'],
      top: 50,
    },
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    grid: [
      { left: 60, right: 30, top: 90, height: '65%' },
      { left: 60, right: 30, top: '78%', height: '15%' },
    ],
    xAxis: [
      { type: 'category', data: allDates, scale: true, boundaryGap: false,
        axisLine: { onZero: false }, splitLine: { show: false }, axisLabel: { show: false } },
      { type: 'category', data: allDates, gridIndex: 1, axisLabel: { show: false } },
    ],
    yAxis: [
      { scale: true, splitArea: { show: true } },
      { scale: true, gridIndex: 1, splitNumber: 2, axisLabel: { show: false },
        axisLine: { show: false }, splitLine: { show: false } },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], start: 60, end: 100 },
      { show: true, xAxisIndex: [0, 1], type: 'slider', bottom: 10, start: 60, end: 100 },
    ],
    series,
  }, true)
}

watch(mode, () => {
  // 切换模式时,如果已有结果,重绘
  if (result.value) {
    nextTick(renderChart)
  }
})

onMounted(async () => {
  await loadStatus()
  await nextTick()  // 等待 DOM 渲染
  ensureChart()     // 提前初始化(图表 div 始终存在,只是 v-show 隐藏)
})

onUnmounted(() => {
  window.removeEventListener('resize', resize)
  if (chart) { chart.dispose(); chart = null }
})
</script>

<style scoped>
.up { color: #f56c6c; }
.down { color: #67c23a; }
</style>