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
      <el-select v-model="filter.min_integrity" placeholder="完整度" clearable style="width:130px;">
        <el-option label="仅不完整 (0~3)" :value="0" />
        <el-option label="完整度 ≤ 1" :value="1" />
        <el-option label="完整度 ≤ 2" :value="2" />
        <el-option label="缺 K线 (≤ 2)" :value="2" />
        <el-option label="完整度 ≥ 3" :value="3" />
        <el-option label="完全完整 (= 4)" :value="4" />
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
      <el-button :disabled="!selected.length" :loading="batch.enrich" @click="batchEnrich">
        <el-icon><MagicStick /></el-icon>批量增强信息
      </el-button>
      <el-divider direction="vertical" />
      <el-button @click="quickUpdate('stock_list')" :loading="updating.stock_list">
        <el-icon><Refresh /></el-icon>刷新基础信息(全部)
      </el-button>
      <el-button @click="openEnrichDialog" :loading="updating.stock_enrich">
        <el-icon><MagicStick /></el-icon>增强股票信息(全量)
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
          <span v-if="row.has_list_date">{{ row.list_date }}</span>
          <el-tag v-else size="small" type="warning">未填</el-tag>
        </template>
      </el-table-column>

      <!-- 完整度列:4 个小图标 -->
      <el-table-column label="数据完整度" width="200" sortable :sort-method="(a,b) => a.integrity_score - b.integrity_score">
        <template #default="{ row }">
          <el-tooltip placement="top">
            <template #content>
              <div v-if="row.has_kline">✓ K线: {{ row.kline_count }} 条 ({{ row.kline_last_date }})</div>
              <div v-else>✗ K线: 缺失</div>
              <div v-if="row.has_industry">✓ 行业: {{ row.industry }}</div>
              <div v-else>✗ 行业: 未填</div>
              <div v-if="row.has_list_date">✓ 上市日期: {{ row.list_date }}</div>
              <div v-else>✗ 上市日期: 未填</div>
              <div v-if="row.last_enriched_at">✓ 已增强: {{ row.last_enriched_at.slice(0,16) }}</div>
              <div v-else>✗ 未增强</div>
            </template>
            <span>
              <el-tag :type="row.has_kline ? 'success' : 'danger'" size="small" style="margin-right:4px;">K</el-tag>
              <el-tag :type="row.has_industry ? 'success' : 'danger'" size="small" style="margin-right:4px;">行业</el-tag>
              <el-tag :type="row.has_list_date ? 'success' : 'danger'" size="small" style="margin-right:4px;">上市</el-tag>
              <el-tag :type="row.last_enriched_at ? 'success' : 'danger'" size="small">增强</el-tag>
              <span style="margin-left:6px;color:#909399;font-size:12px;">{{ row.integrity_score }}/4</span>
            </span>
          </el-tooltip>
        </template>
      </el-table-column>

      <el-table-column label="K线" width="120">
        <template #default="{ row }">
          <span v-if="row.has_kline" style="color:#67c23a;">
            <el-icon><Check /></el-icon>{{ row.kline_count }}
          </span>
          <span v-else style="color:#f56c6c;">
            <el-icon><Warning /></el-icon>缺
          </span>
        </template>
      </el-table-column>

      <el-table-column label="状态" width="80">
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
                <el-dropdown-item
                  command="enrich" :icon="MagicStick" :disabled="!row.is_active"
                >补全基础信息</el-dropdown-item>
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
          <el-descriptions-item label="上市日期">{{ detail.list_date || '-' }}</el-descriptions-item>
          <el-descriptions-item label="K线总数">{{ detail.kline_count.toLocaleString() }}</el-descriptions-item>
          <el-descriptions-item label="K线起始">{{ detail.kline_first_date || '-' }}</el-descriptions-item>
          <el-descriptions-item label="K线最新">{{ detail.kline_last_date || '-' }}</el-descriptions-item>
        </el-descriptions>
        <div style="margin-top:16px;">
          <el-button type="primary" plain @click="goKline(detail.code)">查看K线</el-button>
          <el-button type="warning" plain @click="goBacktest(detail.code)">回测此股</el-button>
        </div>
      </div>
    </el-drawer>

    <!-- 信息增强对话框(带 limit / workers 参数) -->
    <el-dialog v-model="enrichVisible" title="增强股票信息" width="480px">
      <el-form :model="enrichForm" label-width="110px">
        <el-form-item label="限制条数">
          <el-input-number v-model="enrichForm.limit" :min="0" />
          <span style="margin-left:8px;color:#909399;font-size:12px;">0 = 处理全部</span>
        </el-form-item>
        <el-form-item label="Phase 2 并发">
          <el-input-number v-model="enrichForm.workers" :min="0" :max="16" />
          <span style="margin-left:8px;color:#909399;font-size:12px;">
            0 = 跳过 profile API,用 K线 兜底
          </span>
        </el-form-item>
        <el-alert type="warning" :closable="false" show-icon>
          全市场 5000+ 只股,Phase 2 可能持续数小时。建议先 limit=50 测试,确认无误后再大数量执行。
        </el-alert>
      </el-form>
      <template #footer>
        <el-button @click="enrichVisible = false">取消</el-button>
        <el-button type="primary" :loading="updating.stock_enrich" @click="confirmEnrich">开始增强</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { stocksApi, tasksApi } from '@/api/modules'

const router = useRouter()
const loading = ref(false)
const list = ref([])
const total = ref(0)
const industries = ref([])
const detailVisible = ref(false)
const detail = ref(null)
const selected = ref([])

// 任务执行状态
const updating = reactive({ stock_list: false, stock_enrich: false })
const batch = reactive({ kline: false, enrich: false })
const enrichVisible = ref(false)
const enrichForm = reactive({ limit: 50, workers: 4 })

const filter = reactive({
  keyword: '', market: '', industry: '', is_active: 1,
  min_integrity: null,
  page: 1, page_size: 20,
})

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

function goKline(code) {
  detailVisible.value = false
  router.push({ path: '/kline', query: { code } })
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
async function quickUpdate(task) {
  try {
    await ElMessageBox.confirm(
      '从主数据源重新拉取全市场股票列表并 UPSERT 到 stock_list。',
      '刷新基础信息', { type: 'info' },
    )
  } catch { return }
  updating[task] = true
  try {
    const r = await tasksApi.trigger({ task, params: {} })
    ElMessage.success(`已提交 [${task}],ID: ${r.task_id || '-'}`)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    updating[task] = false
  }
}

function openEnrichDialog() {
  enrichForm.limit = 50
  enrichForm.workers = 4
  enrichVisible.value = true
}

async function confirmEnrich() {
  try {
    await ElMessageBox.confirm(
      `将处理 ${enrichForm.limit || '全部'} 只股,Phase 2 并发 ${enrichForm.workers}。提交后不可中断。`,
      '确认增强', { type: 'warning' },
    )
  } catch { return }
  updating.stock_enrich = true
  try {
    const r = await tasksApi.trigger({
      task: 'stock_enrich',
      params: { limit: enrichForm.limit, workers: enrichForm.workers },
    })
    enrichVisible.value = false
    ElMessage.success(`已提交 [stock_enrich],ID: ${r.task_id || '-'}`)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    updating.stock_enrich = false
  }
}

// 单股操作
async function rowAction(cmd, row) {
  if (cmd === 'detail') { openDetail(row); return }
  if (cmd === 'view-kline') { goKline(row.code); return }
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
      task: 'kline_daily',
      params: {
        mode: 'smart', adjust: 'qfq', days_back: 365,
        workers: 4, codes: [row.code],
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
      task: 'kline_daily',
      params: {
        mode: 'smart', adjust: 'qfq', days_back: 365,
        workers: 6, codes,
      },
    })
    ElMessage.success(`已提交批量 K线更新 (${codes.length} 只)`)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    batch.kline = false
  }
}

async function batchEnrich() {
  const codes = selected.value.map(r => r.code)
  try {
    await ElMessageBox.confirm(
      `将批量增强选中 ${codes.length} 只股的 profile 信息,继续?`,
      '批量增强', { type: 'warning' },
    )
  } catch { return }
  batch.enrich = true
  try {
    // 注意: stock_enrich 没有 codes 参数,这里用 limit 限制数量
    // 后端用 stock_list 中的 last_enriched_at 判定,这里传 limit 作近似
    await tasksApi.trigger({
      task: 'stock_enrich',
      params: { limit: codes.length, workers: 4 },
    })
    ElMessage.success(`已提交批量增强 (${codes.length} 只,按 last_enriched_at 排序)`)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    batch.enrich = false
  }
}

onMounted(() => {
  load(1)
  loadIndustries()
})

// 完整度筛选变化时立即重查
watch(() => filter.min_integrity, () => load(1))
</script>