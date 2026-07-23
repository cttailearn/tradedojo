<template>
  <div class="page-card">
    <div class="toolbar">
      <el-input v-model="filter.keyword" placeholder="代码 / 名称" clearable style="width:220px;" @keyup.enter="load(1)" />
      <el-select v-model="filter.market" placeholder="市场" clearable style="width:110px;">
        <el-option label="沪市 SH" value="sh" />
        <el-option label="深市 SZ" value="sz" />
        <el-option label="北交所 BJ" value="bj" />
      </el-select>
      <el-select v-model="filter.industry" placeholder="行业" clearable filterable style="width:160px;">
        <el-option
          v-for="i in industries" :key="i.industry"
          :label="i.industry + ' (' + i.count + ')'" :value="i.industry"
        />
      </el-select>
      <el-select v-model="filter.is_active" style="width:110px;">
        <el-option label="在市" :value="1" />
        <el-option label="退市" :value="0" />
        <el-option label="全部" :value="null" />
      </el-select>
      <el-button type="primary" @click="load(1)"><el-icon><Search /></el-icon>查询</el-button>
      <el-button @click="reset">重置</el-button>
      <span class="grow"></span>
      <el-button @click="load()"><el-icon><RefreshRight /></el-icon>刷新</el-button>
    </div>

    <el-table :data="list" stripe v-loading="loading" @row-click="openDetail">
      <el-table-column prop="code" label="代码" width="100" />
      <el-table-column prop="name" label="名称" width="140" />
      <el-table-column prop="market" label="市场" width="80">
        <template #default="{ row }">
          <el-tag size="small" :type="row.market === 'sh' ? 'danger' : (row.market === 'sz' ? 'warning' : 'info')">
            {{ (row.market || '').toUpperCase() }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="industry" label="行业" />
      <el-table-column prop="list_date" label="上市日期" width="120" />
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
            {{ row.is_active ? '在市' : '退市' }}
          </el-tag>
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
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { stocksApi } from '@/api/modules'

const router = useRouter()
const loading = ref(false)
const list = ref([])
const total = ref(0)
const industries = ref([])
const detailVisible = ref(false)
const detail = ref(null)

const filter = reactive({
  keyword: '', market: '', industry: '', is_active: 1,
  page: 1, page_size: 20,
})

async function load(page) {
  if (page) filter.page = page
  loading.value = true
  try {
    const params = { ...filter }
    if (params.is_active === null) delete params.is_active
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
    page: 1, page_size: 20,
  })
  load(1)
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

onMounted(() => {
  load(1)
  loadIndustries()
})
</script>