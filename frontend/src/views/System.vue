<template>
  <div>
    <div class="page-card">
      <div class="toolbar">
        <el-button type="primary" @click="loadAll"><el-icon><Refresh /></el-icon>刷新全部</el-button>
        <el-button @click="runCheck"><el-icon><Search /></el-icon>执行缺失检查</el-button>
        <span class="grow"></span>
        <el-tag>{{ now }}</el-tag>
      </div>

      <h3 class="page-title">表行数</h3>
      <el-table :data="tableRows" stripe>
        <el-table-column prop="name" label="表名" />
        <el-table-column prop="count" label="行数" align="right">
          <template #default="{ row }">{{ row.count.toLocaleString() }}</template>
        </el-table-column>
      </el-table>
    </div>

    <div class="page-card" v-if="checkReport">
      <h3 class="page-title">数据缺失报告</h3>
      <el-row :gutter="16">
        <el-col :span="12">
          <el-statistic title="股票列表 - 新增" :value="checkReport.stock_list?.new_count || 0" />
          <el-statistic title="股票列表 - 退市" :value="checkReport.stock_list?.delisted_count || 0" />
          <el-statistic title="日K - 缺失股票" :value="(checkReport.kline_daily?.missing_stocks || []).length" />
          <el-statistic title="日K - 过期股票" :value="(checkReport.kline_daily?.outdated_stocks || []).length" />
        </el-col>
        <el-col :span="12">
          <el-statistic title="指数 - 缺失" :value="(checkReport.index_daily?.missing || []).length" />
          <el-statistic title="指数 - 过期" :value="(checkReport.index_daily?.outdated || []).length" />
        </el-col>
      </el-row>
    </div>

    <div class="page-card">
      <div class="toolbar">
        <h3 class="page-title" style="margin:0;">日志查看</h3>
        <span class="grow"></span>
        <el-select v-model="selectedLog" placeholder="选择日志文件" style="width:280px;" @change="loadLog">
          <el-option
            v-for="l in logFiles" :key="l.name"
            :label="l.name + ' (' + Math.round(l.size / 1024) + 'KB)'"
            :value="l.name"
          />
        </el-select>
        <el-input-number v-model="logLines" :min="50" :max="2000" :step="50" @change="loadLog" />
      </div>
      <pre class="task-log" style="height:420px;">{{ logContent || '请选择日志文件' }}</pre>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { systemApi } from '@/api/modules'

const now = ref(new Date().toLocaleString('zh-CN'))
const status = ref({ tables: {} })
const tableRows = ref([])
const checkReport = ref(null)
const logFiles = ref([])
const selectedLog = ref('')
const logLines = ref(200)
const logContent = ref('')
let timer = null

async function loadAll() {
  try {
    const s = await systemApi.status()
    status.value = s
    now.value = s.now || now.value
    tableRows.value = Object.entries(s.tables || {}).map(
      ([name, count]) => ({ name, count }),
    )
  } catch (e) { ElMessage.error(e.message) }
}

async function runCheck() {
  try {
    checkReport.value = await systemApi.check()
    ElMessage.success('检查完成')
  } catch (e) { ElMessage.error(e.message) }
}

async function loadLogFiles() {
  try {
    const r = await systemApi.logs()
    logFiles.value = r.items
    if (r.items.length) {
      selectedLog.value = r.items[0].name
      loadLog()
    }
  } catch {}
}

async function loadLog() {
  if (!selectedLog.value) return
  try {
    const r = await systemApi.tailLog(selectedLog.value, logLines.value)
    logContent.value = r.lines
  } catch (e) { ElMessage.error(e.message) }
}

onMounted(() => {
  loadAll()
  loadLogFiles()
  timer = setInterval(() => {
    now.value = new Date().toLocaleString('zh-CN')
  }, 1000)
})

onUnmounted(() => { if (timer) clearInterval(timer) })
</script>