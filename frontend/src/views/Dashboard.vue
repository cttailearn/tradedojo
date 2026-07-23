<template>
  <div>
    <div class="page-header">
      <h2>仪表盘</h2>
      <el-button @click="load" :loading="loading" size="small" text>
        <el-icon><RefreshRight /></el-icon>刷新
      </el-button>
    </div>

    <!-- 骨架屏 -->
    <el-row v-if="loading && !loaded" :gutter="16">
      <el-col v-for="i in 4" :key="i" :span="6">
        <div class="skeleton skeleton-card"></div>
      </el-col>
    </el-row>

    <!-- 统计卡片 -->
    <el-row v-else :gutter="16">
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

    <!-- K线数据表 -->
    <div v-if="loading && !loaded" class="page-card">
      <div class="skeleton skeleton-title"></div>
      <div class="skeleton skeleton-text" style="width:90%"></div>
      <div class="skeleton skeleton-text" style="width:85%"></div>
      <div class="skeleton skeleton-text" style="width:70%"></div>
    </div>

    <div v-else class="page-card">
      <h3 class="page-title">K线数据(按复权类型)</h3>
      <el-table :data="status.kline_by_adjust || []" :empty-text="'暂无数据'">
        <el-table-column prop="adjust_type" label="复权方式" width="120" />
        <el-table-column prop="count" label="条数" align="right">
          <template #default="{ row }">{{ row.count.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column prop="first_date" label="起始日期" />
        <el-table-column prop="last_date" label="最新日期" />
      </el-table>
    </div>

    <!-- 最近日志 -->
    <div v-if="loading && !loaded" class="page-card">
      <div class="skeleton skeleton-title"></div>
      <div class="skeleton skeleton-text" style="width:92%"></div>
      <div class="skeleton skeleton-text" style="width:80%"></div>
      <div class="skeleton skeleton-text" style="width:65%"></div>
    </div>

    <div v-else class="page-card">
      <h3 class="page-title">最近更新日志</h3>
      <el-table :data="status.recent_logs || []" :empty-text="'暂无日志记录'">
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
        <el-table-column prop="message" label="消息" min-width="200" />
      </el-table>
    </div>

    <!-- 空状态(首次加载后无数据) -->
    <div v-if="!loading && loaded && !stats.length" class="empty-state">
      <div class="icon">📊</div>
      <div class="title">尚未配置数据源</div>
      <div class="desc">请先前往「数据源」页面配置数据来源，然后执行数据更新任务</div>
      <el-button type="primary" @click="$router.push('/admin/tasks')">前往数据更新</el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { systemApi } from '@/api/modules'

const status = ref({ tables: {}, kline_by_adjust: [], recent_logs: [] })
const loading = ref(false)
const loaded = ref(false)

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
  loading.value = true
  try { status.value = await systemApi.status() }
  catch (e) { ElMessage.error(e.message) }
  finally { loading.value = false; loaded.value = true }
}

onMounted(load)
</script>