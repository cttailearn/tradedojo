<template>
  <div class="stats-page">
    <!-- 顶部:交易画像标签(动态生成) -->
    <div class="page-card style-tags-card" v-if="data?.style_tags?.length">
      <div class="head">
        <h3 class="page-title">🧬 你的交易画像</h3>
        <span class="hint">基于所有训练记录自动分析 · 数据越多越准确</span>
      </div>
      <div class="tags">
        <el-tag
          v-for="(t, i) in data.style_tags"
          :key="i"
          :type="tagType(t.level)"
          size="large"
          effect="dark"
          class="tag-item"
        >
          {{ t.tag }}
        </el-tag>
      </div>
      <ul class="tag-descs">
        <li v-for="(t, i) in data.style_tags" :key="'d'+i">{{ t.desc }}</li>
      </ul>
    </div>

    <!-- 顶部 4 块 KPI -->
    <el-row :gutter="12" v-if="data?.summary" class="kpi-row">
      <el-col :span="6">
        <div class="kpi-card">
          <div class="kpi-lbl">总回合数</div>
          <div class="kpi-val">{{ data.summary.total_round_trips }} <small>笔</small></div>
          <div class="kpi-sub">
            <el-tag size="small" type="success">{{ data.summary.win_count }} 胜</el-tag>
            <el-tag size="small" type="danger" style="margin-left: 4px;">{{ data.summary.loss_count }} 负</el-tag>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="kpi-card">
          <div class="kpi-lbl">胜率</div>
          <div class="kpi-val" :class="data.summary.win_rate >= 50 ? 'green' : 'red'">
            {{ data.summary.win_rate }}%
          </div>
          <div class="kpi-sub">
            盈亏因子 <b>{{ data.summary.profit_factor ?? '∞' }}</b>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="kpi-card">
          <div class="kpi-lbl">累计实现盈亏</div>
          <div class="kpi-val" :class="data.summary.total_realized_pnl >= 0 ? 'green' : 'red'">
            {{ data.summary.total_realized_pnl >= 0 ? '+' : '' }}{{ money(data.summary.total_realized_pnl) }}
          </div>
          <div class="kpi-sub">手续费支出 ¥ {{ money(data.summary.total_fees_paid) }}</div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="kpi-card">
          <div class="kpi-lbl">平均持仓</div>
          <div class="kpi-val">{{ data.summary.avg_holding_days }} <small>天</small></div>
          <div class="kpi-sub">中位数 {{ data.summary.median_holding_days }} 天</div>
        </div>
      </el-col>
    </el-row>

    <!-- 高级指标行 -->
    <el-row :gutter="12" v-if="data?.summary" class="kpi-row">
      <el-col :span="8">
        <div class="metric-block">
          <div class="lbl">平均盈利 / 平均亏损</div>
          <div class="vals">
            <span class="green">+{{ money(data.summary.avg_win) }}</span>
            <span class="sep"> / </span>
            <span class="red">{{ money(data.summary.avg_loss) }}</span>
          </div>
          <div class="hint">盈亏比 = 平均盈利 ÷ |平均亏损|,大于 1.5 为优秀</div>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="metric-block">
          <div class="lbl">最大连胜 / 最大连败</div>
          <div class="vals">
            <span class="green">{{ data.summary.max_consecutive_win }} 连胜</span>
            <span class="sep"> / </span>
            <span class="red">{{ data.summary.max_consecutive_loss }} 连败</span>
          </div>
          <div class="hint">连胜时警惕贪婪,连败时警惕报复性交易</div>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="metric-block">
          <div class="lbl">训练场次</div>
          <div class="vals">
            {{ data.summary.total_sessions }} <small>场</small>
            <span class="sep">·</span>
            <el-tag size="small">{{ data.summary.finished_sessions }} 已完结</el-tag>
            <el-tag size="small" type="warning">{{ data.summary.active_sessions }} 进行中</el-tag>
          </div>
          <div class="hint">多训练几只不同类型的股票,样本更具代表性</div>
        </div>
      </el-col>
    </el-row>

    <!-- 分布分析 3 列 -->
    <el-row :gutter="12" v-if="data" class="dist-row">
      <el-col :span="8">
        <div class="page-card dist-card">
          <div class="head"><h3 class="page-title">⏱ 持仓时长分布</h3></div>
          <div ref="holdingChart" class="dist-chart" />
          <el-table :data="data.holding_distribution" size="small" stripe class="dist-table">
            <el-table-column prop="bucket" label="区间" width="80" />
            <el-table-column prop="count" label="回合" width="60" align="right" />
            <el-table-column label="胜率" width="80" align="right">
              <template #default="{ row }">
                <span :class="row.win_rate >= 50 ? 'green' : 'red'">{{ row.win_rate }}%</span>
              </template>
            </el-table-column>
            <el-table-column label="均盈亏" align="right">
              <template #default="{ row }">
                <span :class="row.avg_pnl >= 0 ? 'green' : 'red'">
                  {{ row.avg_pnl >= 0 ? '+' : '' }}{{ money(row.avg_pnl) }}
                </span>
              </template>
            </el-table-column>
          </el-table>
          <div class="insight" v-if="bestHoldingBucket">
            <el-icon color="#67c23a"><Aim /></el-icon>
            你的最佳持仓区间是 <b>{{ bestHoldingBucket.bucket }}</b>(胜率 {{ bestHoldingBucket.win_rate }}%,均盈亏 {{ money(bestHoldingBucket.avg_pnl) }} 元)
          </div>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="page-card dist-card">
          <div class="head"><h3 class="page-title">💰 仓位偏好</h3></div>
          <div ref="positionChart" class="dist-chart" />
          <el-table :data="data.position_distribution" size="small" stripe class="dist-table">
            <el-table-column prop="bucket" label="区间" width="110" />
            <el-table-column prop="count" label="笔数" width="60" align="right" />
            <el-table-column label="胜率" width="80" align="right">
              <template #default="{ row }">
                <span :class="row.win_rate >= 50 ? 'green' : 'red'">{{ row.win_rate }}%</span>
              </template>
            </el-table-column>
            <el-table-column label="均盈亏" align="right">
              <template #default="{ row }">
                <span :class="row.avg_pnl >= 0 ? 'green' : 'red'">
                  {{ row.avg_pnl >= 0 ? '+' : '' }}{{ money(row.avg_pnl) }}
                </span>
              </template>
            </el-table-column>
          </el-table>
          <div class="insight" v-if="bestPositionBucket">
            <el-icon color="#67c23a"><Aim /></el-icon>
            胜率最高的仓位区间是 <b>{{ bestPositionBucket.bucket }}</b>(胜率 {{ bestPositionBucket.win_rate }}%)
          </div>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="page-card dist-card">
          <div class="head"><h3 class="page-title">🎯 买入价位习惯</h3></div>
          <div ref="pricePosChart" class="dist-chart" />
          <el-table :data="data.price_position_distribution" size="small" stripe class="dist-table">
            <el-table-column prop="bucket" label="当日位置" width="100" />
            <el-table-column prop="count" label="笔数" width="60" align="right" />
            <el-table-column label="胜率" width="80" align="right">
              <template #default="{ row }">
                <span :class="row.win_rate >= 50 ? 'green' : 'red'">{{ row.win_rate }}%</span>
              </template>
            </el-table-column>
            <el-table-column label="均盈亏" align="right">
              <template #default="{ row }">
                <span :class="row.avg_pnl >= 0 ? 'green' : 'red'">
                  {{ row.avg_pnl >= 0 ? '+' : '' }}{{ money(row.avg_pnl) }}
                </span>
              </template>
            </el-table-column>
          </el-table>
          <div class="insight" v-if="bestPriceBucket">
            <el-icon color="#67c23a"><Aim /></el-icon>
            你买入价位胜率:低吸 {{ data.price_position_distribution[0].win_rate }}% · 中段 {{ data.price_position_distribution[1].win_rate }}% · 追高 {{ data.price_position_distribution[2].win_rate }}%
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 月度盈亏曲线 -->
    <div class="page-card" v-if="data?.monthly_pnl?.length" style="margin-top: 12px;">
      <div class="head"><h3 class="page-title">📅 月度盈亏走势</h3></div>
      <div ref="monthlyChart" class="monthly-chart" />
    </div>

    <!-- 行业 / 股票偏好 -->
    <el-row :gutter="12" style="margin-top: 12px;" v-if="data">
      <el-col :span="12">
        <div class="page-card">
          <div class="head"><h3 class="page-title">🏭 行业偏好</h3></div>
          <el-table :data="data.industry_ranking" stripe size="small">
            <el-table-column prop="industry" label="行业" />
            <el-table-column prop="count" label="回合" width="80" align="right" />
            <el-table-column label="胜率" width="80" align="right">
              <template #default="{ row }">
                <span :class="row.win_rate >= 50 ? 'green' : 'red'">{{ row.win_rate }}%</span>
              </template>
            </el-table-column>
            <el-table-column label="总盈亏" align="right">
              <template #default="{ row }">
                <span :class="row.total_pnl >= 0 ? 'green' : 'red'">
                  {{ row.total_pnl >= 0 ? '+' : '' }}{{ money(row.total_pnl) }}
                </span>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!data.industry_ranking.length" description="暂无数据" :image-size="60" />
        </div>
      </el-col>
      <el-col :span="12">
        <div class="page-card">
          <div class="head"><h3 class="page-title">⭐ 最熟悉的股票 Top 10</h3></div>
          <el-table :data="data.stock_ranking" stripe size="small">
            <el-table-column label="股票" width="160">
              <template #default="{ row }">
                <b>{{ row.code }}</b> {{ row.name }}
              </template>
            </el-table-column>
            <el-table-column prop="count" label="回合" width="80" align="right" />
            <el-table-column label="胜率" width="80" align="right">
              <template #default="{ row }">
                <span :class="row.win_rate >= 50 ? 'green' : 'red'">{{ row.win_rate }}%</span>
              </template>
            </el-table-column>
            <el-table-column label="总盈亏" align="right">
              <template #default="{ row }">
                <span :class="row.total_pnl >= 0 ? 'green' : 'red'">
                  {{ row.total_pnl >= 0 ? '+' : '' }}{{ money(row.total_pnl) }}
                </span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-col>
    </el-row>

    <!-- 最佳 / 最差单笔 -->
    <el-row :gutter="12" style="margin-top: 12px;" v-if="data?.summary">
      <el-col :span="12">
        <div class="page-card trade-card best">
          <div class="head"><h3 class="page-title">🏆 最佳单笔</h3></div>
          <div v-if="data.summary.best_trade" class="big-pnl">
            <div class="big-val green">+{{ money(data.summary.best_trade.realized_pnl) }}</div>
            <div class="big-meta">
              {{ data.summary.best_trade.name }} ({{ data.summary.best_trade.code }}) ·
              持仓 {{ data.summary.best_trade.holding_days }} 天 ·
              收益 {{ data.summary.best_trade.pnl_pct }}%
            </div>
            <div class="big-detail">
              买入 {{ data.summary.best_trade.buy_date }} → 卖出 {{ data.summary.best_trade.sell_date }}
              · 数量 {{ data.summary.best_trade.quantity }}
            </div>
          </div>
          <el-empty v-else description="暂无数据" :image-size="60" />
        </div>
      </el-col>
      <el-col :span="12">
        <div class="page-card trade-card worst">
          <div class="head"><h3 class="page-title">💔 最差单笔</h3></div>
          <div v-if="data.summary.worst_trade" class="big-pnl">
            <div class="big-val red">{{ money(data.summary.worst_trade.realized_pnl) }}</div>
            <div class="big-meta">
              {{ data.summary.worst_trade.name }} ({{ data.summary.worst_trade.code }}) ·
              持仓 {{ data.summary.worst_trade.holding_days }} 天 ·
              收益 {{ data.summary.worst_trade.pnl_pct }}%
            </div>
            <div class="big-detail">
              买入 {{ data.summary.worst_trade.buy_date }} → 卖出 {{ data.summary.worst_trade.sell_date }}
              · 数量 {{ data.summary.worst_trade.quantity }}
            </div>
          </div>
          <el-empty v-else description="暂无数据" :image-size="60" />
        </div>
      </el-col>
    </el-row>

    <!-- 训练场次列表 -->
    <div class="page-card" style="margin-top: 12px;" v-if="data?.sessions?.length">
      <div class="head">
        <h3 class="page-title">📚 训练场次记录</h3>
        <el-button size="small" @click="exportCsv" :disabled="!data.sessions.length">
          <el-icon><Download /></el-icon>导出 CSV
        </el-button>
      </div>
      <el-table :data="data.sessions" stripe size="small">
        <el-table-column label="股票" width="160">
          <template #default="{ row }">
            <b>{{ row.code }}</b> {{ row.name }}
            <el-tag size="small" v-if="row.industry" style="margin-left: 4px;">{{ row.industry }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === 'finished' ? 'success' : 'warning'">
              {{ row.status === 'finished' ? '已完结' : '进行中' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="trade_count" label="总笔数" width="80" align="right" />
        <el-table-column prop="round_trip_count" label="回合" width="60" align="right" />
        <el-table-column label="总盈亏" align="right">
          <template #default="{ row }">
            <span :class="row.total_pnl >= 0 ? 'green' : 'red'">
              {{ row.total_pnl >= 0 ? '+' : '' }}{{ money(row.total_pnl) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="时间窗口" width="220">
          <template #default="{ row }">
            {{ row.start_date }} → {{ row.end_date }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link @click="viewSession(row.id)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 空状态 -->
    <el-empty v-if="!loading && loaded && !data?.summary?.total_round_trips"
              description="还没有任何交易记录,先发起一次训练吧"
              style="margin-top: 60px;">
      <el-button type="primary" @click="$router.push('/train/setup')">发起训练</el-button>
    </el-empty>

    <!-- 单 session 详细弹窗 -->
    <el-dialog v-model="detailVisible" :title="`场次 ${detailData?.session?.code} ${detailData?.session?.name} 详情`"
               width="900" top="6vh">
      <div v-if="detailData" v-loading="detailLoading">
        <el-row :gutter="12">
          <el-col :span="6"><div class="mini-stat"><div class="lbl">买入</div><div class="val">{{ detailData.stats.total_buy }}</div></div></el-col>
          <el-col :span="6"><div class="mini-stat"><div class="lbl">卖出</div><div class="val">{{ detailData.stats.total_sell }}</div></div></el-col>
          <el-col :span="6"><div class="mini-stat"><div class="lbl">回合</div><div class="val">{{ detailData.stats.round_trip_count }}</div></div></el-col>
          <el-col :span="6"><div class="mini-stat"><div class="lbl">胜率</div><div class="val" :class="detailData.stats.win_rate >= 50 ? 'green' : 'red'">{{ detailData.stats.win_rate }}%</div></div></el-col>
        </el-row>
        <el-row :gutter="12" style="margin-top: 8px;">
          <el-col :span="8"><div class="mini-stat"><div class="lbl">总盈亏</div><div class="val" :class="detailData.stats.total_pnl >= 0 ? 'green' : 'red'">{{ detailData.stats.total_pnl >= 0 ? '+' : '' }}{{ money(detailData.stats.total_pnl) }}</div></div></el-col>
          <el-col :span="8"><div class="mini-stat"><div class="lbl">均持仓</div><div class="val">{{ detailData.stats.avg_holding_days }} 天</div></div></el-col>
          <el-col :span="8"><div class="mini-stat"><div class="lbl">手续费</div><div class="val">¥ {{ money(detailData.stats.total_fees) }}</div></div></el-col>
        </el-row>

        <h4 style="margin: 16px 0 8px;">完整回合(FIFO 配对)</h4>
        <el-table :data="detailData.round_trips" stripe size="small" max-height="260">
          <el-table-column label="买入" width="100">
            <template #default="{ row }">
              <div>{{ row.buy_date }}</div>
              <div class="muted">@{{ row.buy_price }}</div>
            </template>
          </el-table-column>
          <el-table-column label="卖出" width="100">
            <template #default="{ row }">
              <div>{{ row.sell_date }}</div>
              <div class="muted">@{{ row.sell_price }}</div>
            </template>
          </el-table-column>
          <el-table-column prop="quantity" label="数量" width="70" align="right" />
          <el-table-column prop="holding_days" label="持仓" width="60" align="right">
            <template #default="{ row }">{{ row.holding_days }}天</template>
          </el-table-column>
          <el-table-column label="收益%" width="80" align="right">
            <template #default="{ row }">
              <span :class="row.pnl_pct >= 0 ? 'green' : 'red'">{{ row.pnl_pct >= 0 ? '+' : '' }}{{ row.pnl_pct }}%</span>
            </template>
          </el-table-column>
          <el-table-column label="实现盈亏" align="right">
            <template #default="{ row }">
              <span :class="row.realized_pnl >= 0 ? 'green' : 'red'">{{ row.realized_pnl >= 0 ? '+' : '' }}{{ money(row.realized_pnl) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import { trainApi } from '@/api/modules'
import { chartThemeColors } from '@/utils/chartTheme'

const loading = ref(false)
const loaded = ref(false)
const data = ref(null)
const holdingChartEl = ref(null)
const positionChartEl = ref(null)
const pricePosChartEl = ref(null)
const monthlyChartEl = ref(null)
let holdingChart, positionChart, pricePosChart, monthlyChart

const detailVisible = ref(false)
const detailLoading = ref(false)
const detailData = ref(null)

function money(v) {
  if (v == null) return '0'
  const n = Number(v)
  return n.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function tagType(level) {
  return ({success: 'success', warning: 'warning', danger: 'danger', info: 'info'}[level] || 'info')
}

const bestHoldingBucket = computed(() => {
  const buckets = data.value?.holding_distribution || []
  const filled = buckets.filter(b => b.count > 0)
  if (!filled.length) return null
  return filled.reduce((a, b) => (b.win_rate > a.win_rate ? b : a))
})
const bestPositionBucket = computed(() => {
  const buckets = data.value?.position_distribution || []
  const filled = buckets.filter(b => b.count > 0)
  if (!filled.length) return null
  return filled.reduce((a, b) => (b.win_rate > a.win_rate ? b : a))
})
const bestPriceBucket = computed(() => {
  return data.value?.price_position_distribution?.some(b => b.count > 0) || false
})

async function load() {
  loading.value = true
  try {
    data.value = await trainApi.statsOverview()
    loaded.value = true
    await nextTick()
    renderCharts()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

function renderCharts() {
  const T = chartThemeColors()
  if (data.value && holdingChartEl.value) {
    holdingChart = echarts.init(holdingChartEl.value)
    holdingChart.setOption({
      textStyle: { color: T.text },
      tooltip: { trigger: 'axis', backgroundColor: T.tooltipBg, borderColor: T.tooltipBorder, textStyle: { color: T.text } },
      grid: { left: 60, right: 20, top: 20, bottom: 30 },
      xAxis: { type: 'category', data: data.value.holding_distribution.map(d => d.bucket), axisLine: { lineStyle: { color: T.axisLine } }, axisLabel: { color: T.subText } },
      yAxis: [
        { type: 'value', name: '回合数', position: 'left', axisLabel: { color: T.subText }, splitLine: { lineStyle: { color: T.splitLine } } },
        { type: 'value', name: '胜率%', position: 'right', max: 100, axisLabel: { color: T.subText }, splitLine: { show: false } },
      ],
      series: [
        { name: '回合数', type: 'bar', data: data.value.holding_distribution.map(d => d.count), itemStyle: { color: '#409eff' } },
        { name: '胜率%', type: 'line', yAxisIndex: 1, data: data.value.holding_distribution.map(d => d.win_rate), itemStyle: { color: '#67c23a' }, smooth: true },
      ],
    })
  }
  if (data.value && positionChartEl.value) {
    positionChart = echarts.init(positionChartEl.value)
    positionChart.setOption({
      textStyle: { color: T.text },
      tooltip: { trigger: 'axis', backgroundColor: T.tooltipBg, borderColor: T.tooltipBorder, textStyle: { color: T.text } },
      grid: { left: 60, right: 20, top: 20, bottom: 30 },
      xAxis: { type: 'category', data: data.value.position_distribution.map(d => d.bucket), axisLabel: { interval: 0, rotate: 0, fontSize: 10, color: T.subText }, axisLine: { lineStyle: { color: T.axisLine } } },
      yAxis: [
        { type: 'value', name: '笔数', axisLabel: { color: T.subText }, splitLine: { lineStyle: { color: T.splitLine } } },
        { type: 'value', name: '胜率%', position: 'right', max: 100, axisLabel: { color: T.subText }, splitLine: { show: false } },
      ],
      series: [
        { name: '笔数', type: 'bar', data: data.value.position_distribution.map(d => d.count), itemStyle: { color: '#e6a23c' } },
        { name: '胜率%', type: 'line', yAxisIndex: 1, data: data.value.position_distribution.map(d => d.win_rate), itemStyle: { color: '#67c23a' }, smooth: true },
      ],
    })
  }
  if (data.value && pricePosChartEl.value) {
    pricePosChart = echarts.init(pricePosChartEl.value)
    pricePosChart.setOption({
      textStyle: { color: T.text },
      tooltip: { trigger: 'axis', backgroundColor: T.tooltipBg, borderColor: T.tooltipBorder, textStyle: { color: T.text } },
      grid: { left: 60, right: 20, top: 20, bottom: 30 },
      xAxis: { type: 'category', data: data.value.price_position_distribution.map(d => d.bucket), axisLine: { lineStyle: { color: T.axisLine } }, axisLabel: { color: T.subText } },
      yAxis: [
        { type: 'value', name: '笔数', axisLabel: { color: T.subText }, splitLine: { lineStyle: { color: T.splitLine } } },
        { type: 'value', name: '胜率%', position: 'right', max: 100, axisLabel: { color: T.subText }, splitLine: { show: false } },
      ],
      series: [
        { name: '笔数', type: 'bar', data: data.value.price_position_distribution.map(d => d.count), itemStyle: { color: '#909399' } },
        { name: '胜率%', type: 'line', yAxisIndex: 1, data: data.value.price_position_distribution.map(d => d.win_rate), itemStyle: { color: '#67c23a' }, smooth: true },
      ],
    })
  }
  if (data.value && monthlyChartEl.value && data.value.monthly_pnl.length) {
    monthlyChart = echarts.init(monthlyChartEl.value)
    monthlyChart.setOption({
      textStyle: { color: T.text },
      tooltip: { trigger: 'axis', backgroundColor: T.tooltipBg, borderColor: T.tooltipBorder, textStyle: { color: T.text },
        formatter: (params) => {
          const p = params[0]
          return `${p.axisValue}<br/>盈亏 <b style="color:${p.value >= 0 ? '#67c23a' : '#f56c6c'}">${p.value >= 0 ? '+' : ''}${money(p.value)}</b>`
        }
      },
      grid: { left: 60, right: 30, top: 30, bottom: 30 },
      xAxis: { type: 'category', data: data.value.monthly_pnl.map(d => d.month), axisLine: { lineStyle: { color: T.axisLine } }, axisLabel: { color: T.subText } },
      yAxis: { type: 'value', axisLabel: { color: T.subText, formatter: v => v.toLocaleString() }, splitLine: { lineStyle: { color: T.splitLine } } },
      series: [{
        type: 'bar', data: data.value.monthly_pnl.map(d => ({
          value: d.pnl,
          itemStyle: { color: d.pnl >= 0 ? '#ef232a' : '#14b066' },
        })),
        label: { show: true, position: 'top', formatter: (p) => p.value >= 0 ? '+' + money(p.value) : money(p.value), fontSize: 10, color: T.text },
      }],
    })
  }
}

async function viewSession(id) {
  detailVisible.value = true
  detailLoading.value = true
  detailData.value = null
  try {
    detailData.value = await trainApi.sessionStats(id)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    detailLoading.value = false
  }
}

function exportCsv() {
  if (!data.value?.sessions?.length) return
  const headers = ['场次ID', '代码', '名称', '行业', '状态', '总笔数', '回合数', '总盈亏', '起点', '终点']
  const rows = data.value.sessions.map(s => [
    s.id, s.code, s.name, s.industry, s.status,
    s.trade_count, s.round_trip_count, s.total_pnl,
    s.start_date, s.end_date,
  ])
  const csv = [headers, ...rows].map(cols => cols.map(c => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\n')
  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `trade_stats_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('已导出 CSV')
}

function resize() {
  holdingChart?.resize()
  positionChart?.resize()
  pricePosChart?.resize()
  monthlyChart?.resize()
}

onMounted(load)
onUnmounted(() => {
  window.removeEventListener('resize', resize)
  holdingChart?.dispose()
  positionChart?.dispose()
  pricePosChart?.dispose()
  monthlyChart?.dispose()
})
</script>

<style scoped>
.stats-page { padding-bottom: 24px; }

.style-tags-card { padding: 16px 20px; }
.style-tags-card .head { display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px; }
.style-tags-card .head .hint { font-size: 12px; color: #909399; }
.style-tags-card .tags { display: flex; flex-wrap: wrap; gap: 8px; }
.style-tags-card .tag-item { padding: 0 12px; height: 32px; line-height: 32px; font-size: 13px; }
.tag-descs { margin: 12px 0 0; padding-left: 22px; color: #606266; font-size: 12px; line-height: 1.9; }
.tag-descs li::marker { color: #c0c4cc; }

.kpi-row { margin-bottom: 12px; }
.kpi-card { background: var(--bg-card); border-radius: 6px; padding: 16px 18px; box-shadow: var(--shadow-xs); }
.kpi-lbl { font-size: 12px; color: #909399; }
.kpi-val { font-size: 28px; font-weight: bold; margin: 4px 0; line-height: 1.1; color: var(--text-primary); }
.kpi-val small { font-size: 14px; font-weight: normal; color: #909399; margin-left: 4px; }
.kpi-sub { font-size: 12px; color: #909399; }
.kpi-sub b { color: var(--text-primary); }

.metric-block { background: var(--bg-card); border-radius: 6px; padding: 14px 16px; box-shadow: var(--shadow-xs); }
.metric-block .lbl { font-size: 12px; color: #909399; margin-bottom: 4px; }
.metric-block .vals { font-size: 18px; font-weight: bold; }
.metric-block .vals small { font-size: 12px; font-weight: normal; color: #909399; }
.metric-block .vals .sep { color: #c0c4cc; margin: 0 8px; }
.metric-block .hint { font-size: 11px; color: #909399; margin-top: 4px; }

.dist-row { margin-top: 12px; }
.dist-card { padding: 12px 16px; height: 100%; }
.dist-card .head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.dist-card .head .page-title { margin: 0; font-size: 14px; }
.dist-chart { width: 100%; height: 180px; margin-bottom: 8px; }
.dist-table { margin-bottom: 6px; }
.insight {
  font-size: 12px; color: #606266;
  padding: 6px 10px; background: #f0f9eb;
  border-radius: 4px; border-left: 3px solid #67c23a;
  line-height: 1.6;
}
.insight b { color: #67c23a; }

.monthly-chart { width: 100%; height: 240px; }

.trade-card.best { border-left: 4px solid #67c23a; }
.trade-card.worst { border-left: 4px solid #f56c6c; }
.big-pnl { padding: 16px 0; }
.big-val { font-size: 36px; font-weight: bold; line-height: 1.1; }
.big-meta { font-size: 13px; color: #606266; margin-top: 8px; }
.big-detail { font-size: 12px; color: #909399; margin-top: 4px; }

.mini-stat { padding: 8px 12px; background: #fafafa; border-radius: 4px; }
.mini-stat .lbl { font-size: 11px; color: #909399; }
.mini-stat .val { font-size: 18px; font-weight: bold; margin-top: 2px; }

.green { color: #67c23a; }
.red { color: #f56c6c; }
.muted { color: #909399; }
</style>