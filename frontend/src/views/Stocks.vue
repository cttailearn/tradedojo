<template>
  <div class="page-card">
    <div class="toolbar">
      <el-input v-model="filter.keyword" placeholder="代码 / 名称" clearable style="width:200px;" @keyup.enter="load(1)" />
      <el-select v-model="filter.market" placeholder="市场" clearable style="width:100px;">
        <el-option label="沪市 SH" value="sh" />
        <el-option label="深市 SZ" value="sz" />
        <el-option label="北交所 BJ" value="bj" />
      </el-select>
      <el-select v-model="filter.industry" placeholder="行业" clearable filterable style="width:150px;">
        <el-option
          v-for="i in industries" :key="i.industry"
          :label="i.industry + ' (' + i.count + ')'" :value="i.industry"
        />
      </el-select>
      <el-select v-model="filter.is_active" style="width:100px;">
        <el-option label="在市" :value="1" />
        <el-option label="退市" :value="0" />
        <el-option label="全部" :value="null" />
      </el-select>
      <el-select v-model="filter.min_integrity" placeholder="数据完整度" clearable style="width:160px;">
        <el-option label="全部(0~4)" :value="0" />
        <el-option label="至少 2 项" :value="2" />
        <el-option label="至少 3 项" :value="3" />
        <el-option label="完全齐全(4/4)" :value="4" />
      </el-select>
      <el-button type="primary" @click="load(1)"><el-icon><Search /></el-icon>查询</el-button>
      <el-button @click="reset">重置</el-button>
      <span class="grow"></span>
      <el-button @click="exportCsv" :disabled="!list.length">
        <el-icon><Download /></el-icon>导出 CSV
      </el-button>
      <el-button @click="load()"><el-icon><RefreshRight /></el-icon>刷新</el-button>
    </div>

    <!-- 批量操作工具条(选中行时显示) -->
    <el-divider style="margin: 12px 0 8px 0;" />
    <div class="toolbar">
      <span style="color:#606266;font-size:13px;">
        <el-icon><Operation /></el-icon> <b>操作</b>
      </span>
      <span class="grow"></span>
      <span v-if="selected.length" style="color:#909399;font-size:12px;margin-right:8px;">
        已选 {{ selected.length }} 只
      </span>
      <el-button :disabled="!selected.length" :loading="batch.kline" @click="batchUpdateKline">
        <el-icon><DataLine /></el-icon>批量补 K线
      </el-button>
    </div>

    <el-table
      :data="list" stripe v-loading="loading"
      @row-click="openDetail" @selection-change="onSelectChange"
    >
      <el-table-column type="selection" width="46" />
      <el-table-column prop="code" label="代码" width="100" sortable />
      <el-table-column prop="name" label="名称" width="140" sortable />
      <el-table-column prop="market" label="市场" width="80">
        <template #default="{ row }">
          <el-tag size="small" :type="row.market === 'sh' ? 'danger' : (row.market === 'sz' ? 'warning' : 'info')">
            {{ (row.market || '').toUpperCase() }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="industry" label="行业" sortable>
        <template #default="{ row }">
          <span v-if="row.has_industry">{{ row.industry }}</span>
          <el-tag v-else size="small" type="warning">未填</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="list_date" label="上市日期" width="110" sortable>
        <template #default="{ row }">
          <span v-if="row.has_list_date">{{ formatDate(row.list_date) }}</span>
          <el-tag v-else size="small" type="warning">未填</el-tag>
        </template>
      </el-table-column>

      <!-- 数据完整度列:4 个维度 -->
      <el-table-column label="数据完整度" width="230" sortable :sort-method="(a,b) => a.integrity_score - b.integrity_score">
        <template #default="{ row }">
          <el-tooltip placement="top">
            <template #content>
              <div style="line-height:1.8;">
                <div>✓ 基础信息: {{ row.name }} / {{ row.market }}</div>
                <div v-if="row.has_industry">✓ 行业: {{ row.industry }}</div>
                <div v-else>✗ 行业: <span style="color:#f56c6c;">缺失</span></div>
                <div v-if="row.has_list_date">✓ 上市日期: {{ formatDate(row.list_date) }}</div>
                <div v-else>✗ 上市日期: <span style="color:#f56c6c;">缺失</span></div>
                <div v-if="row.has_kline">
                  ✓ K线: {{ row.kline_count }} 条,最新 {{ row.kline_last_date }}<br/>
                  &nbsp;&nbsp;<span :style="{color: row.kline_volume_ok ? '#67c23a' : '#e6a23c'}">·成交量 {{ row.kline_volume_ok ? '✓' : '部分缺失'}}</span><br/>
                  &nbsp;&nbsp;<span :style="{color: row.kline_turnover_ok ? '#67c23a' : '#e6a23c'}">·换手率 {{ row.kline_turnover_ok ? '✓' : '部分缺失'}}</span>
                </div>
                <div v-else>✗ K线: <span style="color:#f56c6c;">未拉取</span></div>
              </div>
            </template>
            <span class="integrity-tags">
              <el-tag :type="row.has_basic ? 'success' : 'danger'" size="small" effect="dark">基础</el-tag>
              <el-tag :type="row.has_industry ? 'success' : 'danger'" size="small" effect="dark">行业</el-tag>
              <el-tag :type="row.has_list_date ? 'success' : 'danger'" size="small" effect="dark">上市</el-tag>
              <el-tag :type="row.has_kline ? 'success' : 'danger'" size="small" effect="dark">K线</el-tag>
              <span class="integrity-score">{{ row.integrity_score }}/4</span>
            </span>
          </el-tooltip>
        </template>
      </el-table-column>

      <el-table-column label="K线" width="140">
        <template #default="{ row }">
          <span v-if="row.has_kline">
            <el-icon style="color:#67c23a;"><Check /></el-icon>
            {{ row.kline_count }}
            <span style="color:#909399; font-size:11px;">({{ row.kline_last_date || '-' }})</span>
          </span>
          <span v-else style="color:#f56c6c;">
            <el-icon><Warning /></el-icon>未拉取
          </span>
        </template>
      </el-table-column>

      <el-table-column label="上市情况" width="90">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
            {{ row.is_active ? '在市' : '退市' }}
          </el-tag>
        </template>
      </el-table-column>

      <!-- 单股操作菜单 -->
      <el-table-column label="操作" width="100" fixed="right">
        <template #default="{ row }">
          <el-dropdown @command="(c) => rowAction(c, row)">
            <el-button size="small" plain @click.stop>
              <el-icon><Operation /></el-icon>操作
              <el-icon><ArrowDown /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="detail" :icon="View">查看详情</el-dropdown-item>
                <el-dropdown-item command="view-kline" :icon="DataLine">查看K线</el-dropdown-item>
                <el-dropdown-item divided
                  command="kline" :icon="DataLine" :disabled="!row.is_active"
                >补全 K线</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      style="margin-top:16px; justify-content:flex-end; display:flex;"
      v-model:current-page="filter.page"
      v-model:page-size="filter.page_size"
      :total="total"
      :page-sizes="[20, 50, 100, 200]"
      layout="total, sizes, prev, pager, next, jumper"
      @current-change="load()"
      @size-change="load(1)"
    />

    <el-drawer
      v-model="detailVisible"
      :title="detail && (detail.code + ' ' + detail.name)"
      size="500"
    >
      <div v-if="detail">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="代码">{{ detail.code }}</el-descriptions-item>
          <el-descriptions-item label="名称">{{ detail.name }}</el-descriptions-item>
          <el-descriptions-item label="完整代码">{{ detail.full_code }}</el-descriptions-item>
          <el-descriptions-item label="市场">{{ (detail.market || '').toUpperCase() }}</el-descriptions-item>
          <el-descriptions-item label="行业">{{ detail.industry || '-' }}</el-descriptions-item>
          <el-descriptions-item label="上市日期">{{ formatDate(detail.list_date) || '-' }}</el-descriptions-item>
          <el-descriptions-item label="K线总数">{{ detail.kline_count.toLocaleString() }}</el-descriptions-item>
          <el-descriptions-item label="K线起始">{{ detail.kline_first_date || '-' }}</el-descriptions-item>
          <el-descriptions-item label="K线最新">{{ detail.kline_last_date || '-' }}</el-descriptions-item>
        </el-descriptions>
        <div style="margin-top:16px;">
          <el-button type="primary" plain @click="goKline(detail.code, detail.name)">查看K线</el-button>
          <el-button type="warning" plain @click="goBacktest(detail.code)">回测此股</el-button>
        </div>
      </div>
    </el-drawer>

    <!-- 信息增强对话框(带 limit / workers 参数) -->

    <!-- K线查看对话框(原 K线查询 功能内嵌) -->
    <el-dialog
      v-model="klineVisible"
      :title="klineTitle"
      width="980px"
      top="5vh"
      @opened="onKlineOpened"
      @closed="onKlineClosed"
    >
      <div class="toolbar" style="margin-bottom: 8px;">
        <el-select v-model="klineForm.period" style="width:110px;" @change="loadKline(1)">
          <el-option label="日K" :value="240" />
          <el-option label="60分钟" :value="60" />
          <el-option label="30分钟" :value="30" />
          <el-option label="周K" :value="10080" />
          <el-option label="月K" :value="43200" />
        </el-select>
        <el-select v-if="klineForm.period === 240" v-model="klineForm.adjust" style="width:100px;" @change="loadKline(1)">
          <el-option label="前复权" value="qfq" />
          <el-option label="后复权" value="hfq" />
        </el-select>
        <el-date-picker v-model="klineForm.start" type="date" value-format="YYYY-MM-DD" placeholder="起始日期" style="width:140px;" @change="loadKline(1)" />
        <el-date-picker v-model="klineForm.end" type="date" value-format="YYYY-MM-DD" placeholder="结束日期" style="width:140px;" @change="loadKline(1)" />
        <el-button type="primary" @click="loadKline(1)"><el-icon><Search /></el-icon>查询</el-button>
        <el-button @click="exportKlineCsv" :disabled="!klineList.length">
          <el-icon><Download /></el-icon>导出 CSV
        </el-button>
        <span class="grow"></span>
        <el-tag size="small">{{ klineTotal }} 条</el-tag>
      </div>

      <div class="kline-chart-wrapper" v-loading="klineLoading">
        <div ref="klineChartRef" class="kline-chart"></div>
        <div v-if="!klineLoading && !klineList.length" class="kline-empty">
          <el-icon size="32" color="#c0c4cc"><DocumentRemove /></el-icon>
          <p>暂无 K 线数据</p>
          <p class="kline-empty-tip">
            可能原因:1) 该股票尚未拉取 K线;
            2) 拉取任务失败或未完成。<br/>
            请到「任务管理」执行增量同步或拉取数据。
          </p>
          <el-button type="primary" plain size="small" :loading="fetchingOne" @click="triggerFetchOne">
            <el-icon><Download /></el-icon>{{ fetchingOne ? fetchProgressText : '立即拉取此股 K线' }}
          </el-button>
        </div>
      </div>

      <el-table :data="klineList" stripe height="320" style="margin-top:8px;">
        <el-table-column :prop="klineForm.period === 240 ? 'trade_date' : 'trade_time'" :label="klineForm.period === 240 ? '日期' : '日期/时间'" width="140" fixed sortable>
          <template #default="{ row }">
            {{ klineTimeLabel(row) }}
          </template>
        </el-table-column>
        <el-table-column prop="open" label="开盘" align="right" :formatter="kFmt2" />
        <el-table-column prop="high" label="最高" align="right" :formatter="kFmt2" />
        <el-table-column prop="low" label="最低" align="right" :formatter="kFmt2" />
        <el-table-column prop="close" label="收盘" align="right" :formatter="kFmt2" />
        <el-table-column v-if="klineForm.period === 240" prop="pre_close" label="昨收" align="right" :formatter="kFmt2" />
        <el-table-column v-if="klineForm.period === 240" prop="change_amount" label="涨跌额" align="right">
          <template #default="{ row }">
            <span :class="(row.change_amount || 0) >= 0 ? 'up' : 'down'">
              {{ kFmt2(null, null, row.change_amount) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column v-if="klineForm.period === 240" label="涨跌幅" align="right" sortable :sort-method="(a, b) => Number(a.pct_change || 0) - Number(b.pct_change || 0)">
          <template #default="{ row }">
            <span :class="Number(row.pct_change || 0) >= 0 ? 'up' : 'down'">
              {{ Number(row.pct_change || 0).toFixed(2) }}%
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="volume" label="成交量(手)" align="right" :formatter="kFmtInt" sortable />
        <el-table-column prop="amount" label="成交额(元)" align="right" :formatter="kFmtAmt" sortable />
        <el-table-column v-if="klineForm.period === 240" prop="turnover_rate" label="换手率%" align="right" :formatter="kFmt2" sortable />
      </el-table>
      <div style="margin-top:8px; text-align:right;">
        <el-pagination
          v-model:current-page="klineForm.page"
          v-model:page-size="klineForm.limit"
          :total="klineTotal"
          :page-sizes="[100, 200, 500, 1000]"
          layout="total, sizes, prev, pager, next, jumper"
          @current-change="loadKline()"
          @size-change="loadKline(1)"
        />
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as echarts from 'echarts'
import { stocksApi, tasksApi, klineApi } from '@/api/modules'

const router = useRouter()
const loading = ref(false)
const list = ref([])
const total = ref(0)
const industries = ref([])
const detailVisible = ref(false)
const detail = ref(null)
const selected = ref([])

// 任务执行状态
const batch = reactive({ kline: false })

const filter = reactive({
  keyword: '', market: '', industry: '', is_active: 1,
  min_integrity: null,
  page: 1, page_size: 20,
})

// K线查看对话框状态
const klineVisible = ref(false)
const klineForm = reactive({
  code: '',
  name: '',
  adjust: 'qfq',
  period: 240,
  start: '',
  end: '',
  page: 1,
  limit: 200,
})
const klineList = ref([])
const klineTotal = ref(0)
const klineLoading = ref(false)
const fetchingOne = ref(false)
const fetchProgressText = ref('正在拉取...')
const klineChartRef = ref(null)
let klineChart = null
const klineTitle = computed(() => klineForm.code
  ? `${klineForm.code}${klineForm.name ? ' ' + klineForm.name : ''} · K线`
  : 'K线')

async function load(page) {
  if (page) filter.page = page
  loading.value = true
  try {
    const params = { ...filter }
    if (params.is_active === null) delete params.is_active
    if (params.min_integrity === null) delete params.min_integrity
    const data = await stocksApi.list(params)
    list.value = data.items
    total.value = data.total
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function loadIndustries() {
  try {
    const r = await stocksApi.industries()
    industries.value = r.items
  } catch {}
}

function reset() {
  Object.assign(filter, {
    keyword: '', market: '', industry: '', is_active: 1,
    min_integrity: null,
    page: 1, page_size: 20,
  })
  load(1)
}

function onSelectChange(rows) {
  selected.value = rows.filter(r => r.is_active)
}

async function openDetail(row) {
  detail.value = null
  detailVisible.value = true
  try {
    detail.value = await stocksApi.detail(row.code)
  } catch (e) {
    ElMessage.error(e.message)
    detailVisible.value = false
  }
}

function goKline(code, name) {
  detailVisible.value = false
  // 重置表单(避免上次打开的残留导致 race condition)
  klineForm.code = code
  klineForm.name = name || ''
  klineForm.adjust = 'qfq'
  klineForm.period = 240
  klineForm.start = ''
  klineForm.end = ''
  klineForm.page = 1
  klineForm.limit = 200
  klineList.value = []
  klineTotal.value = 0
  klineLoading.value = false
  // 先 dispose 上一次的 chart 实例(避免内存泄漏 / 复用旧 DOM)
  if (klineChart) {
    try { klineChart.dispose() } catch {}
    klineChart = null
  }
  klineVisible.value = true
}

// 在 K线 dialog 里直接触发单股拉取(走新的 sync_latest 入口)
let _fetchPollToken = 0
const wait = (ms) => new Promise(resolve => setTimeout(resolve, ms))

async function pollFetchTask(taskId, token) {
  const deadline = Date.now() + 5 * 60 * 1000
  while (token === _fetchPollToken && Date.now() < deadline) {
    await wait(1500)
    if (token !== _fetchPollToken) return null
    const task = await tasksApi.status(taskId)
    if (task.status === 'success') return task
    if (task.status === 'failed') {
      throw new Error(task.message || 'K线拉取任务失败')
    }
    const stage = task.progress?.stage
    fetchProgressText.value = stage === 'stock_list' ? '正在同步股票列表...'
      : stage === 'kline_daily' ? '正在拉取K线...'
        : stage === 'index_daily' ? '正在同步指数...'
          : '正在准备拉取...'
  }
  if (token === _fetchPollToken) throw new Error('K线拉取超时，请到数据任务页面查看任务状态')
  return null
}

async function triggerFetchOne() {
  if (!klineForm.code || fetchingOne.value) return
  const code = klineForm.code
  const token = ++_fetchPollToken
  fetchingOne.value = true
  fetchProgressText.value = '正在提交...'
  try {
    const result = await tasksApi.trigger({
      task: 'sync_latest',
      params: {
        days_back: 120,
        adjust: klineForm.adjust,
        workers: 2,
        codes: [code],
        update_stock_list: false,
        since_list_date: true,
      },
    })
    fetchProgressText.value = '正在准备拉取...'
    ElMessage.success(`已提交 ${code} 的 K线拉取任务`)
    const task = await pollFetchTask(result.task_id, token)
    if (task && token === _fetchPollToken) {
      await loadKline(1)
      ElMessage.success(`${code} 的 K线已更新`)
      load()
    }
  } catch (e) {
    if (token === _fetchPollToken) ElMessage.error(e.message || 'K线拉取失败')
  } finally {
    if (token === _fetchPollToken) fetchingOne.value = false
  }
}

async function loadKline(page) {
  if (!klineForm.code) return
  if (page) klineForm.page = page
  klineLoading.value = true
  try {
    const data = await klineApi.query({
      code: klineForm.code,
      period: klineForm.period,
      adjust: klineForm.adjust,
      start: klineForm.start,
      end: klineForm.end,
      limit: klineForm.limit,
      offset: (klineForm.page - 1) * klineForm.limit,
    })
    klineList.value = data.items
    klineTotal.value = data.total
  } catch (e) {
    ElMessage.error(e.message)
    klineList.value = []
    klineTotal.value = 0
  } finally {
    klineLoading.value = false
    // 不论成功失败,都尝试渲染 chart(空数据也会 clear)
    await nextTick()
    renderKlineChart()
  }
}

/** dialog 完全打开后触发 - 等待动画完成再初始化 chart */
function onKlineOpened() {
  // 给 dialog 打开动画 100ms 缓冲,防止容器尺寸为 0 时 init
  setTimeout(() => {
    if (!klineChart && klineChartRef.value) {
      try {
        klineChart = echarts.init(klineChartRef.value)
        klineChart.resize()
      } catch (e) {
        console.error('[Kline] echarts init failed:', e)
      }
    }
    loadKline(1)
  }, 100)
}

let _rendering = false

function renderKlineChart() {
  if (!klineChart) return
  // 防抖:上一次 setOption 还未完成,跳过本次调用
  if (_rendering) return
  // 防御:容器未挂载或尺寸为 0,跳过渲染避免 ECharts 死循环
  const el = klineChartRef.value
  if (!el || el.clientWidth === 0 || el.clientHeight === 0) {
    return
  }
  if (!klineList.value.length) {
    klineChart.clear()
    return
  }
  _rendering = true
  try {
    // 防御:任何字段为 null/undefined 都会让 echarts 抛错,做归一化
  // 防御:任何字段为 null/undefined 都会让 echarts 抛错,做归一化
  const safe = (v, d = null) => (v == null || (typeof v === 'number' && isNaN(v)) ? d : v)
  const dates = klineList.value.map((r) => klineTimeLabel(r)).filter(Boolean)
  if (!dates.length) {
    klineChart.clear()
    return
  }
  const ohlc = klineList.value.map((r) => [
    safe(r.open), safe(r.close), safe(r.low), safe(r.high),
  ])
  const volumes = klineList.value.map((r) => ({
    value: safe(r.volume, 0),
    itemStyle: { color: (r.close ?? 0) >= (r.open ?? 0) ? '#ef232a' : '#14b066' },
  }))
  const closes = klineList.value.map((r) => Number(safe(r.close, 0)))
  const calcMA = (n) =>
    closes.map((_, i) => {
      if (i < n - 1) return '-'
      let s = 0
      for (let k = i - n + 1; k <= i; k++) s += closes[k]
      return +(s / n).toFixed(2)
    })
  const ma5 = calcMA(5), ma10 = calcMA(10), ma20 = calcMA(20)
  klineChart.setOption({
    title: { text: `${klineForm.code} ${klinePeriodLabel()}`, left: 'center' },
    legend: { data: ['K线', 'MA5', 'MA10', 'MA20', '成交量'], top: 30 },
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross', link: [{ xAxisIndex: 'all' }] } },
    grid: [
      { left: 60, right: 30, top: 70, height: '60%' },
      { left: 60, right: 30, top: '78%', height: '16%' },
    ],
    xAxis: [
      { type: 'category', data: dates, scale: true, boundaryGap: false,
        axisLine: { onZero: false }, splitLine: { show: false }, axisLabel: { show: false } },
      { type: 'category', data: dates, gridIndex: 1, axisLabel: { show: false } },
    ],
    yAxis: [
      { scale: true, splitArea: { show: true } },
      { scale: true, gridIndex: 1, splitNumber: 2,
        axisLabel: { show: false }, axisLine: { show: false }, splitLine: { show: false } },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], start: 50, end: 100 },
      { show: true, xAxisIndex: [0, 1], type: 'slider', bottom: 10, start: 50, end: 100 },
    ],
    series: [
      { name: 'K线', type: 'candlestick', data: ohlc,
        itemStyle: { color: '#ef232a', color0: '#14b066', borderColor: '#ef232a', borderColor0: '#14b066' } },
      { name: 'MA5',  type: 'line', data: ma5,  smooth: true, lineStyle: { width: 1, color: '#ff9800' }, showSymbol: false },
      { name: 'MA10', type: 'line', data: ma10, smooth: true, lineStyle: { width: 1, color: '#2196f3' }, showSymbol: false },
      { name: 'MA20', type: 'line', data: ma20, smooth: true, lineStyle: { width: 1, color: '#9c27b0' }, showSymbol: false },
      { name: '成交量', type: 'bar', data: volumes, xAxisIndex: 1, yAxisIndex: 1 },
    ],
    })
    // 渲染后立即 resize 一次,确保容器尺寸正确
    try { klineChart.resize() } catch {}
  } finally {
    _rendering = false
  }
}

function kFmt2(_r, _c, v) {
  if (v == null) return '-'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function kFmtInt(_r, _c, v) {
  if (v == null) return '-'
  return Math.round(Number(v)).toLocaleString('zh-CN')
}
function kFmtAmt(_r, _c, v) {
  if (v == null) return '-'
  const n = Number(v)
  if (n >= 1e8) return (n / 1e8).toFixed(2) + ' 亿'
  if (n >= 1e4) return (n / 1e4).toFixed(2) + ' 万'
  return n.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

/** 把 YYYYMMDD / YYYY-MM-DD 统一格式化成 YYYY-MM-DD */
function formatDate(s) {
  if (!s) return ''
  const str = String(s).trim()
  if (/^\d{8}$/.test(str)) return `${str.slice(0, 4)}-${str.slice(4, 6)}-${str.slice(6, 8)}`
  if (/^\d{4}-\d{2}-\d{2}$/.test(str)) return str
  return str
}

const PERIOD_LABELS = { 240: '日K', 60: '60分钟', 30: '30分钟', 10080: '周K', 43200: '月K' }

/** 当前周期名称 */
function klinePeriodLabel() {
  if (klineForm.period === 240) {
    return klineForm.adjust === 'qfq' ? '前复权' : '后复权'
  }
  return PERIOD_LABELS[klineForm.period] || '日K'
}

/** K线时间标签:日线用 trade_date,分钟线用 trade_time(带时分秒),周/月截取日期前 10 位 */
function klineTimeLabel(r) {
  if (klineForm.period === 240) return r.trade_date
  const t = r.trade_time || ''
  return klineForm.period >= 10080 ? t.slice(0, 10) : t
}

function exportKlineCsv() {
  if (!klineList.value.length) return
  const isDaily = klineForm.period === 240
  const headers = isDaily
    ? ['日期', '开盘', '最高', '最低', '收盘', '昨收', '涨跌额', '涨跌幅%', '成交量(手)', '成交额(元)', '换手率%']
    : ['日期/时间', '开盘', '最高', '最低', '收盘', '成交量(手)', '成交额(元)']
  const rows = klineList.value.map((r) => {
    const cols = [isDaily ? r.trade_date : klineTimeLabel(r), r.open, r.high, r.low, r.close]
    if (isDaily) cols.push(r.pre_close, r.change_amount, r.pct_change)
    cols.push(r.volume, r.amount)
    if (isDaily) cols.push(r.turnover_rate)
    return cols
  })
  const csv = [headers, ...rows].map((cols) => cols.join(',')).join('\n')
  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${klineForm.code}_${klinePeriodLabel()}_${klineForm.start || 'all'}_${klineForm.end || 'now'}.csv`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('已导出 CSV')
}

function onKlineClosed() {
  _fetchPollToken += 1
  fetchingOne.value = false
  if (klineChart) {
    klineChart.dispose()
    klineChart = null
  }
  klineList.value = []
  klineTotal.value = 0
}

function goBacktest(code) {
  detailVisible.value = false
  router.push({ path: '/backtest', query: { code } })
}

function exportCsv() {
  if (!list.value.length) return
  const headers = ['代码', '名称', '市场', '行业', '上市日期', 'K线数', 'K线最新', '完整度', '状态']
  const rows = list.value.map((r) => [
    r.code, r.name, (r.market || '').toUpperCase(),
    r.industry || '-', r.list_date || '-',
    r.kline_count, r.kline_last_date || '-',
    `${r.integrity_score}/4`,
    r.is_active ? '在市' : '退市',
  ])
  const csv = [headers, ...rows].map((cols) => cols.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(',')).join('\n')
  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `stocks_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('已导出 CSV')
}

// ============== 操作 ==============
// 单股操作
async function rowAction(cmd, row) {
  if (cmd === 'detail') { openDetail(row); return }
  if (cmd === 'view-kline') { goKline(row.code, row.name); return }
  // 补全 K线(单股)
  try {
    await ElMessageBox.confirm(
      `将拉取 [${row.code} ${row.name}] 的日 K线(可与现有数据合并),确定?`,
      '单股更新', { type: 'info' },
    )
  } catch { return }
  batch.kline = true
  try {
    await tasksApi.trigger({
      task: 'sync_latest',
      params: {
        days_back: 120, adjust: 'qfq',
        workers: 2, codes: [row.code],
        since_list_date: true,
      },
    })
    ElMessage.success(`已提交 [${row.code}] K线更新任务`)
    load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    batch.kline = false
  }
}

// 批量更新
async function batchUpdateKline() {
  const codes = selected.value.map(r => r.code)
  try {
    await ElMessageBox.confirm(
      `将批量拉取选中 ${codes.length} 只股的日 K线,继续?`,
      '批量更新', { type: 'warning' },
    )
  } catch { return }
  batch.kline = true
  try {
    await tasksApi.trigger({
      task: 'sync_latest',
      params: {
        days_back: 120, adjust: 'qfq',
        workers: 4, codes,
        since_list_date: true,
      },
    })
    ElMessage.success(`已提交批量 K线更新 (${codes.length} 只)`)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    batch.kline = false
  }
}

onMounted(() => {
  load(1)
  loadIndustries()
  window.addEventListener('resize', klineResize)
})

// 完整度筛选变化时立即重查
watch(() => filter.min_integrity, () => load(1))

function klineResize() {
  // chart 已 dispose 时直接跳过,避免报错
  if (klineChart && klineChart.getDom && klineChart.getDom().isConnected) {
    try { klineChart.resize() } catch {}
  }
}

onUnmounted(() => {
  window.removeEventListener('resize', klineResize)
  _fetchPollToken += 1
  if (klineChart) {
    try { klineChart.dispose() } catch {}
    klineChart = null
  }
})
</script>

<style scoped>
.kline-chart-wrapper {
  width: 100%;
  height: 360px;
  position: relative;
}
.kline-chart {
  width: 100%;
  height: 100%;
}
.kline-empty {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #909399;
}
.kline-empty p { margin: 0; font-size: 14px; }
.kline-empty-tip { font-size: 12px; color: #c0c4cc; text-align: center; line-height: 1.6; }

/* 数据完整度标签 */
.integrity-tags {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.integrity-tags .el-tag {
  margin: 0;
}
.integrity-score {
  margin-left: 6px;
  color: #909399;
  font-size: 12px;
  white-space: nowrap;
}
</style>