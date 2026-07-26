<template>
  <div>
    <!-- 数据覆盖卡(按数据类型) -->
    <div class="page-card">
      <div class="toolbar">
        <h3 class="page-title" style="margin:0;">
          <el-icon><DataAnalysis /></el-icon>
          数据覆盖(按数据类型)
        </h3>
        <span class="grow"></span>
        <el-button :loading="checking" @click="runCheck">
          <el-icon><Search /></el-icon>执行缺失检查
        </el-button>
      </div>

      <el-row :gutter="16" v-if="checkReport">
        <!-- 股票列表 -->
        <el-col :span="6">
          <div class="coverage-card">
            <div class="coverage-title">
              <el-icon><List /></el-icon> 股票基础信息
            </div>
            <div class="coverage-stats">
              <div class="coverage-stat">
                <div class="num">{{ tableByName('stock_list')?.count?.toLocaleString() || 0 }}</div>
                <div class="label">总条数</div>
              </div>
              <div class="coverage-stat warn">
                <div class="num">{{ checkReport.stock_list?.new_count || 0 }}</div>
                <div class="label">新增</div>
              </div>
              <div class="coverage-stat danger">
                <div class="num">{{ checkReport.stock_list?.delisted_count || 0 }}</div>
                <div class="label">退市</div>
              </div>
            </div>
          </div>
        </el-col>

        <!-- 主要指数 -->
        <el-col :span="6">
          <div class="coverage-card">
            <div class="coverage-title">
              <el-icon><TrendCharts /></el-icon> 主要指数
            </div>
            <div class="coverage-stats">
              <div class="coverage-stat">
                <div class="num">{{ tableByName('index_daily')?.count?.toLocaleString() || 0 }}</div>
                <div class="label">条数</div>
              </div>
              <div class="coverage-stat warn">
                <div class="num">{{ (checkReport.index_daily?.missing || []).length }}</div>
                <div class="label">缺失</div>
              </div>
              <div class="coverage-stat danger">
                <div class="num">{{ (checkReport.index_daily?.outdated || []).length }}</div>
                <div class="label">过期</div>
              </div>
            </div>
          </div>
        </el-col>

        <!-- 日 K 线 -->
        <el-col :span="6">
          <div class="coverage-card">
            <div class="coverage-title">
              <el-icon><DataLine /></el-icon> 日 K 线
            </div>
            <div class="coverage-stats">
              <div class="coverage-stat">
                <div class="num">{{ tableByName('kline_daily')?.count?.toLocaleString() || 0 }}</div>
                <div class="label">条数</div>
              </div>
              <div class="coverage-stat warn">
                <div class="num">{{ (checkReport.kline_daily?.missing_stocks || []).length }}</div>
                <div class="label">缺失股</div>
              </div>
              <div class="coverage-stat danger">
                <div class="num">{{ (checkReport.kline_daily?.outdated_stocks || []).length }}</div>
                <div class="label">过期股</div>
              </div>
            </div>
          </div>
        </el-col>

        <!-- 信息增强 -->
        <el-col :span="6">
          <div class="coverage-card">
            <div class="coverage-title">
              <el-icon><MagicStick /></el-icon> 信息增强
            </div>
            <div class="coverage-stats">
              <div class="coverage-stat">
                <div class="num">{{ enrichedCount.toLocaleString() }}</div>
                <div class="label">已增强</div>
              </div>
              <div class="coverage-stat warn">
                <div class="num">{{ unenrichedCount.toLocaleString() }}</div>
                <div class="label">未增强</div>
              </div>
              <div class="coverage-stat">
                <div class="num" style="font-size:14px;">{{ enrichedRate }}%</div>
                <div class="label">完成率</div>
              </div>
            </div>
          </div>
        </el-col>
      </el-row>

      <el-empty v-else-if="!checking" description="尚未执行缺失检查" :image-size="60" />
    </div>

    <!-- 表行数 + 日志(原有) -->
    <div class="page-card">
      <div class="toolbar">
        <h3 class="page-title" style="margin:0;">表行数</h3>
        <span class="grow"></span>
        <el-button @click="loadAll"><el-icon><Refresh /></el-icon>刷新全部</el-button>
        <el-tag>{{ now }}</el-tag>
      </div>

      <el-table :data="tableRows" stripe>
        <el-table-column prop="name" label="表名" />
        <el-table-column prop="count" label="行数" align="right">
          <template #default="{ row }">{{ row.count.toLocaleString() }}</template>
        </el-table-column>
      </el-table>
    </div>

    <div class="page-card" v-if="checkReport">
      <h3 class="page-title">缺失详情</h3>
      <el-row :gutter="16">
        <el-col :span="12">
          <h4 style="margin:8px 0;">日 K 缺失股票 ({{ (checkReport.kline_daily?.missing_stocks || []).length }})</h4>
          <div class="code-list">
            <el-tag
              v-for="s in (checkReport.kline_daily?.missing_stocks || []).slice(0, 80)" :key="s"
              type="warning" size="small" style="margin:2px;"
            >{{ s }}</el-tag>
            <span v-if="(checkReport.kline_daily?.missing_stocks || []).length > 80" style="color:#909399;font-size:12px;">
              等 {{ (checkReport.kline_daily?.missing_stocks || []).length }} 只...
            </span>
          </div>
          <h4 style="margin:12px 0 8px 0;">日 K 过期股票 ({{ (checkReport.kline_daily?.outdated_stocks || []).length }})</h4>
          <div class="code-list">
            <el-tag
              v-for="s in (checkReport.kline_daily?.outdated_stocks || []).slice(0, 80)" :key="s"
              type="danger" size="small" style="margin:2px;"
            >{{ s }}</el-tag>
            <span v-if="(checkReport.kline_daily?.outdated_stocks || []).length > 80" style="color:#909399;font-size:12px;">
              等 {{ (checkReport.kline_daily?.outdated_stocks || []).length }} 只...
            </span>
          </div>
        </el-col>
        <el-col :span="12">
          <h4 style="margin:8px 0;">指数缺失 ({{ (checkReport.index_daily?.missing || []).length }})</h4>
          <div class="code-list">
            <el-tag
              v-for="s in (checkReport.index_daily?.missing || [])" :key="s"
              type="warning" size="small" style="margin:2px;"
            >{{ s }}</el-tag>
            <span v-if="(checkReport.index_daily?.missing || []).length === 0" style="color:#909399;font-size:12px;">无</span>
          </div>
          <h4 style="margin:12px 0 8px 0;">指数过期 ({{ (checkReport.index_daily?.outdated || []).length }})</h4>
          <div class="code-list">
            <el-tag
              v-for="s in (checkReport.index_daily?.outdated || [])" :key="s"
              type="danger" size="small" style="margin:2px;"
            >{{ s }}</el-tag>
            <span v-if="(checkReport.index_daily?.outdated || []).length === 0" style="color:#909399;font-size:12px;">无</span>
          </div>
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
import { ref, onMounted, onUnmounted, computed } from 'vue'
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
const checking = ref(false)
let timer = null

function tableByName(name) {
  return tableRows.value.find(r => r.name === name)
}

// 计算已增强/未增强股票数(从 stock_list 的 last_enriched_at 字段推断)
// 该数从后端 checkReport 不一定有,这里用总数 - 表中未增强的近似;若后端未提供则退化为 0
const enrichedCount = computed(() => {
  const r = checkReport.value?.stock_enrich
  if (!r) return 0
  return r.enriched_count ?? 0
})
const unenrichedCount = computed(() => {
  const r = checkReport.value?.stock_enrich
  if (!r) return 0
  return r.unenriched_count ?? 0
})
const enrichedRate = computed(() => {
  const r = checkReport.value?.stock_enrich
  if (!r || !r.total) return 0
  return Math.round(((r.enriched_count || 0) / r.total) * 100)
})

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
  checking.value = true
  try {
    checkReport.value = await systemApi.check()
    ElMessage.success('检查完成')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    checking.value = false
  }
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

<style scoped>
.coverage-card {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 12px 14px;
  background: #fafbfc;
}
.coverage-title {
  font-size: 13px;
  color: #606266;
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
}
.coverage-stats {
  display: flex;
  justify-content: space-between;
  gap: 6px;
}
.coverage-stat {
  flex: 1;
  text-align: center;
  padding: 6px 4px;
  background: #fff;
  border-radius: 4px;
}
.coverage-stat .num {
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}
.coverage-stat .label {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
}
.coverage-stat.warn .num { color: #e6a23c; }
.coverage-stat.danger .num { color: #f56c6c; }
.code-list {
  max-height: 180px;
  overflow-y: auto;
  padding: 4px;
  background: #fafbfc;
  border-radius: 4px;
}
</style>