<template>
  <div>
    <div class="page-card">
      <div class="toolbar">
        <el-input v-model="form.code" placeholder="股票代码,如 000001" style="width:180px;" @keyup.enter="load(1)" />
        <el-select v-model="form.adjust" style="width:100px;">
          <el-option label="前复权" value="qfq" />
          <el-option label="后复权" value="hfq" />
        </el-select>
        <el-date-picker v-model="form.start" type="date" value-format="YYYY-MM-DD" placeholder="起始日期" style="width:140px;" />
        <el-date-picker v-model="form.end" type="date" value-format="YYYY-MM-DD" placeholder="结束日期" style="width:140px;" />
        <el-button type="primary" @click="load(1)"><el-icon><Search /></el-icon>查询</el-button>
        <span class="grow"></span>
        <el-tag size="small">{{ total }} 条</el-tag>
      </div>

      <div ref="chartRef" class="kline-chart"></div>
    </div>

    <div class="page-card">
      <h3 class="page-title">数据明细</h3>
      <el-table :data="list" stripe height="380">
        <el-table-column prop="trade_date" label="日期" width="110" fixed />
        <el-table-column prop="open" label="开盘" align="right" />
        <el-table-column prop="high" label="最高" align="right" />
        <el-table-column prop="low" label="最低" align="right" />
        <el-table-column prop="close" label="收盘" align="right" />
        <el-table-column prop="pre_close" label="昨收" align="right" />
        <el-table-column prop="change_amount" label="涨跌额" align="right" />
        <el-table-column label="涨跌幅" align="right">
          <template #default="{ row }">
            <span :class="(row.pct_change || 0) >= 0 ? 'up' : 'down'">
              {{ (row.pct_change || 0).toFixed(2) }}%
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="volume" label="成交量(手)" align="right" />
        <el-table-column prop="amount" label="成交额(元)" align="right" />
        <el-table-column prop="turnover_rate" label="换手率%" align="right" />
      </el-table>
      <div style="margin-top:12px; text-align:right;">
        <el-pagination
          v-model:current-page="form.page"
          v-model:page-size="form.limit"
          :total="total"
          :page-sizes="[100, 200, 500, 1000]"
          layout="total, sizes, prev, pager, next"
          @current-change="load()"
          @size-change="load(1)"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import { klineApi } from '@/api/modules'

const route = useRoute()
const chartRef = ref(null)
let chart = null

const form = reactive({
  code: '000001', adjust: 'qfq', start: '', end: '',
  page: 1, limit: 200,
})
const list = ref([])
const total = ref(0)

async function load(page) {
  if (page) form.page = page
  try {
    const data = await klineApi.query({
      code: form.code, adjust: form.adjust,
      start: form.start, end: form.end,
      limit: form.limit, offset: (form.page - 1) * form.limit,
    })
    list.value = data.items
    total.value = data.total
    await nextTick()
    renderChart()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

function renderChart() {
  if (!chart) return
  if (!list.value.length) {
    chart.clear()
    return
  }
  const dates = list.value.map((r) => r.trade_date)
  const ohlc = list.value.map((r) => [r.open, r.close, r.low, r.high])
  const volumes = list.value.map((r) => ({
    value: r.volume,
    itemStyle: { color: r.close >= r.open ? '#f56c6c' : '#67c23a' },
  }))

  chart.setOption({
    title: { text: `${form.code} ${form.adjust === 'qfq' ? '前复权' : '后复权'}`, left: 'center' },
    legend: { data: ['K线', '成交量'], top: 30 },
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    grid: [
      { left: 60, right: 30, top: 70, height: '60%' },
      { left: 60, right: 30, top: '78%', height: '18%' },
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
        itemStyle: { color: '#f56c6c', color0: '#67c23a', borderColor: '#f56c6c', borderColor0: '#67c23a' } },
      { name: '成交量', type: 'bar', data: volumes, xAxisIndex: 1, yAxisIndex: 1 },
    ],
  })
}

onMounted(async () => {
  if (route.query.code) form.code = route.query.code
  chart = echarts.init(chartRef.value)
  window.addEventListener('resize', resize)
  await load(1)
})

onUnmounted(() => {
  window.removeEventListener('resize', resize)
  if (chart) chart.dispose()
})

function resize() { chart && chart.resize() }
</script>