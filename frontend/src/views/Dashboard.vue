<template>
  <div>
    <el-row :gutter="16">
      <el-col v-for="s in stats" :key="s.label" :span="6">
        <div class="stat-card">
          <div class="stat-icon" :class="s.color">
            <el-icon><component :is="s.icon" /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-label">{{ s.label }}</div>
            <div class="stat-value">{{ formatNum(s.value) }}</div>
            <div class="stat-sub" v-if="s.sub">{{ s.sub }}</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <div class="page-card">
      <h3 class="page-title">K线数据(按复权类型)</h3>
      <el-table :data="status.kline_by_adjust || []" stripe>
        <el-table-column prop="adjust_type" label="复权方式" width="120" />
        <el-table-column prop="count" label="条数" align="right">
          <template #default="{ row }">{{ row.count.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column prop="first_date" label="起始日期" />
        <el-table-column prop="last_date" label="最新日期" />
      </el-table>
    </div>

    <div class="page-card">
      <h3 class="page-title">最近更新日志</h3>
      <el-table :data="status.recent_logs || []" stripe>
        <el-table-column prop="start_time" label="开始时间" width="180" />
        <el-table-column prop="task_name" label="任务" width="140" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="affected_rows" label="影响行数" align="right" />
        <el-table-column prop="message" label="消息" />
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { systemApi } from '@/api/modules'

const status = ref({ tables: {}, kline_by_adjust: [], recent_logs: [] })

const stats = computed(() => {
  const t = status.value.tables || {}
  const klineTotal = (status.value.kline_by_adjust || []).reduce(
    (a, b) => a + b.count, 0,
  )
  return [
    { label: '股票总数', value: t.stock_list || 0, color: 'blue', icon: 'Box', sub: '含退市' },
    { label: '日K线总条数', value: klineTotal, color: 'green', icon: 'DataLine' },
    { label: '指数记录', value: t.index_daily || 0, color: 'orange', icon: 'TrendCharts' },
    { label: '管理员账号', value: t.admin_user || 0, color: 'purple', icon: 'UserFilled' },
  ]
})

function formatNum(v) { return Number(v || 0).toLocaleString() }

async function load() {
  try { status.value = await systemApi.status() }
  catch (e) { ElMessage.error(e.message) }
}

onMounted(load)
</script>