<template>
  <div class="report">
    <NavBar :title="'诊断报告'" show-back>
      <template #right>
        <button class="navbar__btn" @click="goTrade" aria-label="返回训练">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 12a9 9 0 1 1-9-9"/><path d="M21 3v6h-6"/>
          </svg>
        </button>
      </template>
    </NavBar>

    <div class="report__body" v-loading="loading">
      <template v-if="session">
        <!-- 训练概况 -->
        <section class="card">
          <h3 class="card__title">训练概况</h3>
          <div class="overview">
            <div class="overview__item">
              <span class="overview__lbl">股票</span>
              <span class="overview__val">
                {{ session.name }} <small>({{ session.code }})</small>
              </span>
            </div>
            <div class="overview__item">
              <span class="overview__lbl">训练区间</span>
              <span class="overview__val">{{ session.start_date?.slice(0,10) }} → {{ session.end_date?.slice(0,10) }}</span>
            </div>
            <div class="overview__item">
              <span class="overview__lbl">初始资金</span>
              <span class="overview__val num">¥ {{ money(session.initial_cash) }}</span>
            </div>
            <div class="overview__item" :class="totalPnl >= 0 ? 'up' : 'down'">
              <span class="overview__lbl">总盈亏</span>
              <span class="overview__val num">
                {{ totalPnl >= 0 ? '+' : '' }}¥ {{ money(totalPnl) }}
                ({{ pct(totalPnlPct) }})
              </span>
            </div>
            <div class="overview__item">
              <span class="overview__lbl">训练状态</span>
              <span class="tag" :class="session.status === 'finished' ? '' : 'tag--success'">
                {{ session.status === 'finished' ? '已结束' : '进行中' }}
              </span>
            </div>
            <div class="overview__item">
              <span class="overview__lbl">总交易次数</span>
              <span class="overview__val">{{ stats.totalTrades }}</span>
            </div>
          </div>
        </section>

        <!-- 核心指标 -->
        <section class="card" v-if="stats.totalTrades > 0">
          <h3 class="card__title">核心指标</h3>
          <div class="metrics">
            <div class="metric-tile">
              <div class="metric-tile__lbl">胜率</div>
              <div class="metric-tile__val" :class="stats.winRate >= 50 ? 'up' : 'down'">
                {{ stats.winRate.toFixed(1) }}%
              </div>
              <div class="metric-tile__sub">{{ stats.winCount }}胜 / {{ stats.lossCount }}负</div>
            </div>
            <div class="metric-tile">
              <div class="metric-tile__lbl">盈亏比</div>
              <div class="metric-tile__val" :class="stats.profitFactor >= 1 ? 'up' : 'down'">
                {{ stats.profitFactor.toFixed(2) }}
              </div>
              <div class="metric-tile__sub">
                {{ stats.profitFactor >= 2 ? '优秀' : (stats.profitFactor >= 1 ? '一般' : '需改进') }}
              </div>
            </div>
            <div class="metric-tile">
              <div class="metric-tile__lbl">总交易</div>
              <div class="metric-tile__val">{{ stats.totalTrades }}</div>
              <div class="metric-tile__sub">{{ stats.buyCount }}买 / {{ stats.sellCount }}卖</div>
            </div>
            <div class="metric-tile">
              <div class="metric-tile__lbl">总手续费</div>
              <div class="metric-tile__val num">¥ {{ money(stats.totalFee) }}</div>
              <div class="metric-tile__sub">含佣金+印花税+过户费</div>
            </div>
          </div>
        </section>

        <!-- 空状态 -->
        <section class="card" v-if="stats.totalTrades === 0 && !loading">
          <div class="empty">
            <div class="empty__icon">📋</div>
            <div class="empty__text">暂无交易记录</div>
            <button class="btn btn--primary" style="margin-top: var(--sp-4xl);" @click="goTrade">
              返回训练
            </button>
          </div>
        </section>

        <template v-if="stats.totalTrades > 0">
          <!-- 交易分析 -->
          <section class="card">
            <h3 class="card__title">交易分析</h3>
            <div class="kv-list">
              <div class="kv"><span>买入次数</span><span>{{ stats.buyCount }}</span></div>
              <div class="kv"><span>卖出次数</span><span>{{ stats.sellCount }}</span></div>
              <div class="kv">
                <span>胜率</span>
                <span :class="stats.winRate >= 50 ? 'up' : 'down'">{{ stats.winRate.toFixed(1) }}%</span>
              </div>
              <div class="kv"><span>盈利次数</span><span class="up">{{ stats.winCount }}</span></div>
              <div class="kv"><span>亏损次数</span><span class="down">{{ stats.lossCount }}</span></div>
              <div class="kv">
                <span>盈亏比</span>
                <span :class="stats.profitFactor >= 1 ? 'up' : 'down'">{{ stats.profitFactor.toFixed(2) }}</span>
              </div>
              <div class="kv">
                <span>最大单笔盈利</span>
                <span class="up">+¥ {{ money(stats.maxWin) }}</span>
              </div>
              <div class="kv">
                <span>最大单笔亏损</span>
                <span class="down">-¥ {{ money(Math.abs(stats.maxLoss)) }}</span>
              </div>
              <div class="kv">
                <span>总手续费</span>
                <span>¥ {{ money(stats.totalFee) }}</span>
              </div>
            </div>
          </section>

          <!-- 交易明细 -->
          <section class="card">
            <h3 class="card__title">交易明细</h3>
            <ul class="list" v-if="stats.tradeDetails.length">
              <li v-for="(row, i) in stats.tradeDetails" :key="i" class="list-item trade-row">
                <div class="list-item__body">
                  <div class="list-item__title">
                    <span class="tag" :class="row.side.toUpperCase() === 'BUY' ? 'tag--up' : 'tag--down'">
                      {{ row.side.toUpperCase() === 'BUY' ? '买' : '卖' }}
                    </span>
                    {{ row.date?.slice(0,10) }} · {{ row.qty }}股 @ ¥ {{ price(row.price) }}
                  </div>
                  <div class="list-item__sub">金额 ¥ {{ money(row.amount) }} · 费 ¥ {{ money(row.fee) }}</div>
                </div>
                <div class="list-item__aside">
                  <template v-if="row.realized_pnl != null && row.side.toUpperCase() === 'SELL'">
                    <span :class="(row.realized_pnl||0) >= 0 ? 'up' : 'down'">
                      {{ (row.realized_pnl||0) >= 0 ? '+' : '' }}{{ money(row.realized_pnl) }}
                    </span>
                  </template>
                  <span v-else class="muted">-</span>
                </div>
              </li>
            </ul>
            <div class="empty" v-else>
              <div class="empty__text">暂无明细</div>
            </div>
          </section>

          <!-- 行为诊断 -->
          <section class="card">
            <h3 class="card__title">行为诊断</h3>
            <div class="diag-list">
              <div v-for="(d, i) in diagnosis" :key="i"
                   class="diag-item"
                   :class="d.level === 'good' ? 'is-good' : (d.level === 'warn' ? 'is-warn' : 'is-info')">
                <div class="diag-item__title">{{ d.title }}</div>
                <div class="diag-item__desc">{{ d.desc }}</div>
              </div>
            </div>
          </section>

          <!-- 改进建议 -->
          <section class="card">
            <h3 class="card__title">改进建议</h3>
            <div class="suggest-list">
              <div v-for="(s, i) in suggestions" :key="i" class="suggest-item">
                <span class="suggest-item__num">{{ i + 1 }}</span>
                <div>
                  <div class="suggest-item__title">{{ s.title }}</div>
                  <div class="suggest-item__desc">{{ s.desc }}</div>
                </div>
              </div>
            </div>
          </section>
        </template>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showToast } from 'vant'
import { trainApi } from '@/api/modules'
import { money, pct, price } from '@/utils/trainFee'
import NavBar from '@/components/NavBar.vue'

const route = useRoute()
const router = useRouter()
const sessionId = route.params.id
const loading = ref(false)
const session = ref(null)
const trades = ref([])
const equity = ref([])

const totalPnl = computed(() => session.value?.total_pnl || 0)
const totalPnlPct = computed(() => session.value?.total_pnl_pct || 0)

const stats = computed(() => {
  const list = trades.value || []
  const sellTrades = list.filter((t) => t.side?.toLowerCase() === 'sell' && t.realized_pnl != null)
  const wins = sellTrades.filter((t) => t.realized_pnl > 0)
  const losses = sellTrades.filter((t) => t.realized_pnl < 0)

  const totalWin = wins.reduce((a, b) => a + (b.realized_pnl || 0), 0)
  const totalLoss = Math.abs(losses.reduce((a, b) => a + (b.realized_pnl || 0), 0))
  const totalFee = list.reduce((a, b) => a + (b.fee || 0), 0)

  return {
    totalTrades: list.length,
    buyCount: list.filter((t) => t.side?.toLowerCase() === 'buy').length,
    sellCount: sellTrades.length,
    winCount: wins.length,
    lossCount: losses.length,
    winRate: sellTrades.length > 0 ? (wins.length / sellTrades.length * 100) : 0,
    maxWin: wins.length > 0 ? Math.max(...wins.map((t) => t.realized_pnl || 0)) : 0,
    maxLoss: losses.length > 0 ? Math.min(...losses.map((t) => t.realized_pnl || 0)) : 0,
    profitFactor: totalLoss > 0 ? totalWin / totalLoss : (totalWin > 0 ? 999 : 0),
    totalFee,
    tradeDetails: [...list].sort((a, b) => (a.date || '').localeCompare(b.date || '')),
  }
})

const diagnosis = computed(() => {
  const s = stats.value
  const diag = []
  if (s.sellCount > 0) {
    if (s.winRate >= 60) diag.push({ level: 'good', title: '胜率优秀', desc: `胜率达到 ${s.winRate.toFixed(1)}%,选股和择时能力较强。` })
    else if (s.winRate >= 40) diag.push({ level: 'info', title: '胜率中等', desc: `胜率 ${s.winRate.toFixed(1)}%,可尝试提高入场标准。` })
    else diag.push({ level: 'warn', title: '胜率偏低', desc: `胜率仅 ${s.winRate.toFixed(1)}%,建议减少追高操作。` })
  }
  if (s.sellCount > 0) {
    if (s.profitFactor >= 2) diag.push({ level: 'good', title: '盈亏比优秀', desc: '盈利远超亏损,风险控制能力较强。' })
    else if (s.profitFactor >= 1) diag.push({ level: 'info', title: '盈亏比一般', desc: '建议设置更严格的止盈止损纪律。' })
    else diag.push({ level: 'warn', title: '盈亏比不足', desc: '亏损大于盈利,需要严格止损。' })
  }
  const md = computeMaxDrawdown()
  if (md > 20) diag.push({ level: 'warn', title: '回撤过大', desc: `最大回撤 ${md.toFixed(1)}%,建议控制单笔仓位。` })
  else if (md > 10) diag.push({ level: 'info', title: '回撤可控', desc: `最大回撤 ${md.toFixed(1)}%,在可接受范围内。` })
  else if (s.sellCount > 0) diag.push({ level: 'good', title: '回撤控制良好', desc: `最大回撤 ${md.toFixed(1)}%。` })
  if (s.totalTrades > 50) diag.push({ level: 'warn', title: '交易过于频繁', desc: `${s.totalTrades} 次交易,手续费 ¥ ${money(s.totalFee)},频繁交易损耗收益。` })
  if (diag.length === 0) diag.push({ level: 'info', title: '数据不足', desc: '交易次数较少,完成更多交易后再来查看。' })
  return diag
})

const suggestions = computed(() => {
  const s = stats.value
  const diag = diagnosis.value
  const sugs = []
  if (diag.some((d) => d.title.includes('胜率偏低') || d.title.includes('回撤过大'))) {
    sugs.push({ title: '严格设置止损位', desc: '每笔交易入场前设定止损价,建议不超过入场价的 5-8%。' })
  }
  if (diag.some((d) => d.title.includes('交易过于频繁'))) {
    sugs.push({ title: '减少无意义交易', desc: '提高入场标准,减少交易频率可以显著降低手续费损耗。' })
  }
  if (diag.some((d) => d.title.includes('盈亏比'))) {
    sugs.push({ title: '优化盈亏比', desc: '让利润奔跑,截断亏损。目标盈亏比 > 2。' })
  }
  if (s.maxLoss < 0 && Math.abs(s.maxLoss) > (session.value?.initial_cash || 100000) * 0.1) {
    sugs.push({ title: '控制单笔风险', desc: `最大单笔亏损 ¥ ${money(Math.abs(s.maxLoss))},超过初始资金 10%。建议单笔仓位 ≤ 20%。` })
  }
  sugs.push({ title: '坚持记录交易日志', desc: '记录每笔交易的理由和情绪,复盘是最好的老师。' })
  return sugs
})

function computeMaxDrawdown() {
  const eq = equity.value || []
  if (eq.length === 0) return 0
  let peak = eq[0].total_equity || eq[0].value || eq[0]
  let maxDd = 0
  for (const point of eq) {
    const v = point.total_equity || point.value || point
    if (typeof v !== 'number') continue
    if (v > peak) peak = v
    const dd = (peak - v) / peak * 100
    if (dd > maxDd) maxDd = dd
  }
  return maxDd
}

function goTrade() { router.replace(`/trade/${sessionId}`) }

async function load() {
  loading.value = true
  try {
    const [sess, eqData] = await Promise.all([
      trainApi.session(sessionId),
      trainApi.equity(sessionId).catch(() => []),
    ])
    session.value = sess
    if (sess.trades) trades.value = sess.trades
    if (Array.isArray(eqData)) equity.value = eqData
    else if (eqData?.equity) equity.value = eqData.equity
  } catch (e) {
    showToast({ type: 'fail', message: e.message || '加载失败' })
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.report { background: var(--bg-page); min-height: 100vh; min-height: 100dvh; padding-top: var(--navbar-h); }
.report__body { padding: var(--sp-3xl) 0 calc(var(--safe-bottom) + var(--sp-5xl)); }

.overview {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--sp-4xl) var(--sp-3xl);
}
.overview__item { display: flex; flex-direction: column; gap: var(--sp-sm); }
.overview__lbl { font-size: 0.22rem; color: var(--text-placeholder); }
.overview__val { font-size: 0.28rem; color: var(--text-primary); font-weight: 500; }
.overview__val small { font-size: 0.22rem; color: var(--text-secondary); font-weight: 400; }

.metrics {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--sp-3xl);
}
.metric-tile {
  background: var(--bg-muted);
  border-radius: var(--radius-md);
  padding: var(--sp-3xl);
}
.metric-tile__lbl { font-size: 0.22rem; color: var(--text-placeholder); }
.metric-tile__val {
  font-size: 0.40rem;
  font-weight: 700;
  line-height: 1.2;
  margin: var(--sp-sm) 0;
}
.metric-tile__sub { font-size: 0.20rem; color: var(--text-secondary); }

.kv-list {
  display: flex;
  flex-direction: column;
}
.kv {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--sp-3xl) 0;
  border-bottom: 1px solid var(--border-color-light);
  font-size: 0.26rem;
}
.kv:last-child { border-bottom: none; }
.kv span:first-child { color: var(--text-secondary); }

.trade-row .list-item__title { font-size: 0.26rem; }
.tag--up   { background: var(--color-up-bg);   color: var(--color-up); }
.tag--down { background: var(--color-down-bg); color: var(--color-down); }

.diag-list, .suggest-list {
  display: flex; flex-direction: column;
  gap: var(--sp-3xl);
}
.diag-item {
  border-radius: var(--radius-md);
  padding: var(--sp-3xl) var(--sp-4xl);
}
.diag-item.is-good { background: #d1fae5; }
.diag-item.is-warn { background: #fef3c7; }
.diag-item.is-info { background: #e0e7ff; }
.diag-item__title { font-weight: 600; font-size: 0.28rem; margin-bottom: var(--sp-sm); }
.diag-item__desc { font-size: 0.24rem; color: var(--text-regular); line-height: 1.6; }

.suggest-item { display: flex; gap: var(--sp-3xl); }
.suggest-item__num {
  flex-shrink: 0;
  width: 0.48rem; height: 0.48rem; border-radius: var(--radius-full);
  background: var(--color-primary); color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 0.24rem; font-weight: 700;
}
.suggest-item__title { font-size: 0.28rem; font-weight: 600; margin-bottom: var(--sp-sm); }
.suggest-item__desc { font-size: 0.24rem; color: var(--text-secondary); line-height: 1.6; }

.up   { color: var(--color-up); }
.down { color: var(--color-down); }
.muted { color: var(--text-placeholder); }
</style>
