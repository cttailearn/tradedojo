<template>
  <div class="stats page page--no-navbar" :style="{ paddingTop: 'var(--navbar-h)' }">
    <div class="stats__intro">
      <h2>交割单统计</h2>
      <p>基于所有训练记录自动分析(数据越多越准确)</p>
    </div>

    <!-- 交易画像 -->
    <section class="card" v-if="data?.style_tags?.length">
      <h3 class="card__title">🧬 你的交易画像</h3>
      <div class="tags">
        <span v-for="(t, i) in data.style_tags" :key="i"
              class="tag"
              :class="`tag--${t.level === 'good' ? 'success' : (t.level === 'warn' ? 'warning' : 'info')}`">
          {{ t.tag }}
        </span>
      </div>
      <ul class="tag-descs">
        <li v-for="(t, i) in data.style_tags" :key="'d'+i">{{ t.desc }}</li>
      </ul>
    </section>

    <!-- KPI 4 块 -->
    <section class="card kpi-card" v-if="data?.summary">
      <h3 class="card__title">核心数据</h3>
      <div class="kpi">
        <div class="kpi__item">
          <div class="kpi__lbl">总回合数</div>
          <div class="kpi__val num">{{ data.summary.total_round_trips }} <small>笔</small></div>
          <div class="kpi__sub">
            <span class="up">{{ data.summary.win_count }} 胜</span> ·
            <span class="down">{{ data.summary.loss_count }} 负</span>
          </div>
        </div>
        <div class="kpi__item">
          <div class="kpi__lbl">胜率</div>
          <div class="kpi__val num"
               :class="data.summary.win_rate >= 50 ? 'up' : 'down'">
            {{ data.summary.win_rate }}%
          </div>
          <div class="kpi__sub">
            盈亏因子 <b>{{ data.summary.profit_factor ?? '∞' }}</b>
          </div>
        </div>
        <div class="kpi__item">
          <div class="kpi__lbl">累计实现盈亏</div>
          <div class="kpi__val num"
               :class="data.summary.total_realized_pnl >= 0 ? 'up' : 'down'">
            {{ data.summary.total_realized_pnl >= 0 ? '+' : '' }}{{ money(data.summary.total_realized_pnl) }}
          </div>
          <div class="kpi__sub">手续费 ¥ {{ money(data.summary.total_fees_paid) }}</div>
        </div>
        <div class="kpi__item">
          <div class="kpi__lbl">平均持仓</div>
          <div class="kpi__val num">{{ data.summary.avg_holding_days }} <small>天</small></div>
          <div class="kpi__sub">中位数 {{ data.summary.median_holding_days }} 天</div>
        </div>
      </div>
    </section>

    <!-- 高级指标 -->
    <section class="card" v-if="data?.summary">
      <h3 class="card__title">深度指标</h3>
      <div class="kv-list">
        <div class="kv">
          <span>平均盈利 / 平均亏损</span>
          <span>
            <span class="up">+{{ money(data.summary.avg_win) }}</span>
            <span class="muted"> / </span>
            <span class="down">{{ money(data.summary.avg_loss) }}</span>
          </span>
        </div>
        <div class="kv">
          <span>最大连胜 / 最大连败</span>
          <span>
            <span class="up">{{ data.summary.max_consecutive_win }} 连胜</span>
            <span class="muted"> / </span>
            <span class="down">{{ data.summary.max_consecutive_loss }} 连败</span>
          </span>
        </div>
        <div class="kv">
          <span>训练场次</span>
          <span>{{ data.summary.total_sessions }} 场
            <span class="muted"> · {{ data.summary.finished_sessions }} 已完结</span>
          </span>
        </div>
      </div>
    </section>

    <!-- 分布 -->
    <section class="card" v-if="data">
      <h3 class="card__title">📊 持仓时长分布</h3>
      <div ref="holdingChart" class="dist-chart" />
      <ul class="list" v-if="data.holding_distribution?.length">
        <li v-for="(row, i) in data.holding_distribution" :key="i" class="list-item">
          <div class="list-item__body">
            <div class="list-item__title">{{ row.bucket }}</div>
            <div class="list-item__sub">{{ row.count }} 回合</div>
          </div>
          <div class="list-item__aside" style="text-align: right;">
            <div :class="row.win_rate >= 50 ? 'up' : 'down'" style="font-weight:600;">胜率 {{ row.win_rate }}%</div>
            <div :class="row.avg_pnl >= 0 ? 'up' : 'down'" style="font-size: 0.22rem;">
              {{ row.avg_pnl >= 0 ? '+' : '' }}{{ money(row.avg_pnl) }}
            </div>
          </div>
        </li>
      </ul>
    </section>

    <section class="card" v-if="data">
      <h3 class="card__title">💰 仓位偏好</h3>
      <div ref="positionChart" class="dist-chart" />
      <ul class="list" v-if="data.position_distribution?.length">
        <li v-for="(row, i) in data.position_distribution" :key="i" class="list-item">
          <div class="list-item__body">
            <div class="list-item__title">{{ row.bucket }}</div>
            <div class="list-item__sub">{{ row.count }} 笔</div>
          </div>
          <div class="list-item__aside" style="text-align: right;">
            <div :class="row.win_rate >= 50 ? 'up' : 'down'" style="font-weight:600;">胜率 {{ row.win_rate }}%</div>
            <div :class="row.avg_pnl >= 0 ? 'up' : 'down'" style="font-size: 0.22rem;">
              {{ row.avg_pnl >= 0 ? '+' : '' }}{{ money(row.avg_pnl) }}
            </div>
          </div>
        </li>
      </ul>
    </section>

    <div class="empty" v-if="!data || !data.summary">
      <div class="empty__icon">📈</div>
      <div class="empty__text">完成训练后这里显示你的交割单统计</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import echarts from '@/plugins/echarts'
import { showToast } from 'vant'
import { trainApi } from '@/api/modules'
import { money } from '@/utils/trainFee'

const data = ref(null)
const holdingChart = ref(null)
const positionChart = ref(null)

let holdingChartInst = null
let positionChartInst = null

async function load() {
  try {
    data.value = await trainApi.statsOverview()
    await nextTick()
    renderCharts()
  } catch (e) {
    showToast({ type: 'fail', message: e.message })
  }
}

function renderCharts() {
  if (data.value?.holding_distribution?.length && holdingChart.value) {
    holdingChartInst = holdingChartInst || echarts.init(holdingChart.value)
    holdingChartInst.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 30, right: 16, top: 16, bottom: 28 },
      xAxis: {
        type: 'category',
        data: data.value.holding_distribution.map((d) => d.bucket),
        axisLabel: { fontSize: 10 },
      },
      yAxis: { type: 'value', axisLabel: { fontSize: 10 } },
      series: [{
        type: 'bar',
        data: data.value.holding_distribution.map((d) => d.count),
        itemStyle: { color: '#3b82f6', borderRadius: [4, 4, 0, 0] },
        barWidth: '50%',
      }],
    }, true)
  }
  if (data.value?.position_distribution?.length && positionChart.value) {
    positionChartInst = positionChartInst || echarts.init(positionChart.value)
    positionChartInst.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 30, right: 16, top: 16, bottom: 28 },
      xAxis: {
        type: 'category',
        data: data.value.position_distribution.map((d) => d.bucket),
        axisLabel: { fontSize: 10 },
      },
      yAxis: { type: 'value', axisLabel: { fontSize: 10 } },
      series: [{
        type: 'bar',
        data: data.value.position_distribution.map((d) => d.count),
        itemStyle: { color: '#f59e0b', borderRadius: [4, 4, 0, 0] },
        barWidth: '50%',
      }],
    }, true)
  }
}

onMounted(load)
</script>

<style scoped>
.stats__intro { padding: var(--sp-4xl) var(--sp-4xl) var(--sp-2xl); }
.stats__intro h2 { margin: 0 0 var(--sp-sm); font-size: 0.40rem; font-weight: 700; }
.stats__intro p { margin: 0; color: var(--text-secondary); font-size: 0.26rem; }

.tags { display: flex; flex-wrap: wrap; gap: var(--sp-2xl); margin-bottom: var(--sp-3xl); }
.tag-descs { padding-left: var(--sp-5xl); margin: 0; color: var(--text-secondary); font-size: 0.24rem; line-height: 1.8; }

.kpi-card .kpi {
  display: grid; grid-template-columns: 1fr 1fr; gap: var(--sp-3xl);
}
.kpi__item {
  background: var(--bg-muted);
  border-radius: var(--radius-md);
  padding: var(--sp-3xl);
}
.kpi__lbl { font-size: 0.22rem; color: var(--text-placeholder); }
.kpi__val {
  font-size: 0.42rem;
  font-weight: 700;
  line-height: 1.2;
  margin: var(--sp-sm) 0;
}
.kpi__val small { font-size: 0.24rem; color: var(--text-secondary); font-weight: 400; }
.kpi__sub { font-size: 0.22rem; color: var(--text-secondary); }

.kv-list { display: flex; flex-direction: column; }
.kv {
  display: flex; justify-content: space-between; align-items: center;
  padding: var(--sp-3xl) 0;
  border-bottom: 1px solid var(--border-color-light);
  font-size: 0.26rem;
}
.kv:last-child { border-bottom: none; }
.kv span:first-child { color: var(--text-secondary); }
.muted { color: var(--text-placeholder); }

.dist-chart { width: 100%; height: 3.00rem; margin-bottom: var(--sp-3xl); }

.up   { color: var(--color-up); }
.down { color: var(--color-down); }
</style>
