<template>
  <div>
    <div class="page-card">
      <h3 class="page-title">触发更新任务</h3>
      <el-alert type="info" :closable="false" show-icon style="margin-bottom:16px;">
        系统提供两类数据更新:<b>拉取数据</b>(首次/换源)和<b>增量同步</b>(日常)。
        所有拉取任务会写到 <code>data/stock.db</code>,进度可在下方查看。
      </el-alert>

      <div class="task-actions">
        <!-- 任务 1: 全量拉取 -->
        <div class="task-card">
          <div class="task-card-head">
            <el-icon size="22" color="#409EFF"><Download /></el-icon>
            <span class="task-card-title">拉取数据</span>
            <el-tag size="small" type="info">fetch_all</el-tag>
          </div>
          <div class="task-card-desc">
            全量初始化:股票列表 → 行业映射 → 全市场 K线 → 主要指数。<br/>
            适用场景:首次部署、换数据源、长时间未更新。
          </div>
          <el-form :model="fetchForm" label-width="100px" size="small">
            <el-form-item label="K线回溯">
              <el-input-number v-model="fetchForm.days_back" :min="30" :max="3650" />
              <span class="form-hint">天</span>
            </el-form-item>
            <el-form-item label="复权方式">
              <el-radio-group v-model="fetchForm.adjust">
                <el-radio-button value="qfq">前复权</el-radio-button>
                <el-radio-button value="hfq">后复权</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="并发线程">
              <el-input-number v-model="fetchForm.workers" :min="1" :max="16" />
              <span class="form-hint">建议 ≤ 4</span>
            </el-form-item>
            <el-form-item label="增强信息">
              <el-switch v-model="fetchForm.skip_enrich" :active-value="true" :inactive-value="false" />
              <span class="form-hint" style="margin-left:8px;">
                {{ fetchForm.skip_enrich ? '跳过(更快)' : '启用(行业+上市日期)' }}
              </span>
            </el-form-item>
          </el-form>
          <div class="task-card-foot">
            <el-button
              type="primary" :loading="triggering.fetch"
              @click="triggerFetch"
            >
              <el-icon><VideoPlay /></el-icon>开始拉取
            </el-button>
          </div>
        </div>

        <!-- 任务 2: 增量同步 -->
        <div class="task-card">
          <div class="task-card-head">
            <el-icon size="22" color="#67C23A"><Refresh /></el-icon>
            <span class="task-card-title">增量同步</span>
            <el-tag size="small" type="success">sync_latest</el-tag>
          </div>
          <div class="task-card-desc">
            智能增量:同步股票列表(新上市/退市)+ 仅拉缺失/过期 K线 + 主要指数。<br/>
            适用场景:日常盘后刷新。每天 16:30 自动调度。
          </div>
          <el-form :model="syncForm" label-width="100px" size="small">
            <el-form-item label="回溯天数">
              <el-input-number v-model="syncForm.days_back" :min="1" :max="120" />
              <span class="form-hint">覆盖最近交易日</span>
            </el-form-item>
            <el-form-item label="复权方式">
              <el-radio-group v-model="syncForm.adjust">
                <el-radio-button value="qfq">前复权</el-radio-button>
                <el-radio-button value="hfq">后复权</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="并发线程">
              <el-input-number v-model="syncForm.workers" :min="1" :max="16" />
              <span class="form-hint">建议 ≤ 4</span>
            </el-form-item>
            <el-form-item label="同步列表">
              <el-switch v-model="syncForm.update_stock_list" />
              <span class="form-hint" style="margin-left:8px;">
                {{ syncForm.update_stock_list ? '开启' : '关闭' }}
              </span>
            </el-form-item>
          </el-form>
          <div class="task-card-foot">
            <el-button
              type="success" :loading="triggering.sync"
              @click="triggerSync"
            >
              <el-icon><VideoPlay /></el-icon>开始同步
            </el-button>
          </div>
        </div>
      </div>

      <el-divider />
      <div>
        <el-button @click="resetCheckpoint">
          <el-icon><Refresh /></el-icon>重置断点(daily_kline)
        </el-button>
      </div>
    </div>

    <div class="page-card" v-if="current">
      <h3 class="page-title">
        当前任务:<el-tag>{{ current.task_name }}</el-tag>
        <el-tag :type="statusType" style="margin-left:8px;">{{ current.status }}</el-tag>
        <span style="float:right; color:#909399; font-weight:normal; font-size:12px;">
          任务ID: {{ current.task_id }}
        </span>
      </h3>
      <div class="task-log" ref="logBoxRef">
        <span
          v-for="(line, idx) in current.log_tail"
          :key="idx"
          class="log-line"
          :class="logClass(line)"
        >{{ line }}</span>
      </div>
      <div style="margin-top:8px;">
        <span style="color:#909399; font-size:12px;">
          开始: {{ current.started_at || '-' }} · 结束: {{ current.ended_at || '-' }}
        </span>
        <span v-if="current.message" style="margin-left:12px; color:#909399; font-size:12px;">
          消息: {{ current.message }}
        </span>
      </div>
    </div>

    <div class="page-card">
      <h3 class="page-title">最近任务</h3>
      <el-table :data="recent" stripe>
        <el-table-column prop="started_at" label="开始时间" width="180" />
        <el-table-column prop="task_name" label="任务" width="140" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTypeOf(row.status)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="message" label="消息" />
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button size="small" link @click="watch(row)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { tasksApi } from '@/api/modules'

// 两个独立表单,各自提交自己的任务
const fetchForm = reactive({
  days_back: 365,
  adjust: 'qfq',
  workers: 4,
  skip_enrich: false,
})
const syncForm = reactive({
  days_back: 10,
  adjust: 'qfq',
  workers: 4,
  update_stock_list: true,
})

const triggering = reactive({ fetch: false, sync: false })
const current = ref(null)
const recent = ref([])
const logBoxRef = ref(null)
let timer = null

function statusTypeOf(s) {
  return s === 'success' ? 'success'
    : s === 'failed' ? 'danger'
    : s === 'running' ? 'warning' : 'info'
}
const statusType = computed(() => current.value ? statusTypeOf(current.value.status) : 'info')

function logClass(line) {
  if (/ERROR|失败|Exception/i.test(line)) return 'log-error'
  if (/WARN|警告/i.test(line)) return 'log-warning'
  return 'log-info'
}

async function submit(taskName, params) {
  const r = await tasksApi.trigger({ task: taskName, params })
  current.value = {
    task_id: r.task_id, task_name: r.task_name,
    status: 'pending', log_tail: [],
  }
  ElMessage.success(`已派发任务: ${r.task_name}`)
  startPolling()
  loadRecent()
}

async function triggerFetch() {
  try {
    await ElMessageBox.confirm(
      `将拉取全部股票列表、行业映射、K线(回溯 ${fetchForm.days_back} 天)和主要指数。` +
      (fetchForm.skip_enrich ? '(跳过增强)' : ''),
      '确认拉取数据',
      { type: 'warning', confirmButtonText: '开始拉取' },
    )
  } catch { return }
  triggering.fetch = true
  try {
    await submit('fetch_all', {
      days_back: fetchForm.days_back,
      adjust: fetchForm.adjust,
      workers: fetchForm.workers,
      skip_enrich: fetchForm.skip_enrich,
    })
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    triggering.fetch = false
  }
}

async function triggerSync() {
  try {
    await ElMessageBox.confirm(
      `将增量同步股票列表 + 仅拉缺失/过期 K线(回溯 ${syncForm.days_back} 天) + 主要指数。`,
      '确认增量同步',
      { type: 'info', confirmButtonText: '开始同步' },
    )
  } catch { return }
  triggering.sync = true
  try {
    await submit('sync_latest', {
      days_back: syncForm.days_back,
      adjust: syncForm.adjust,
      workers: syncForm.workers,
      update_stock_list: syncForm.update_stock_list,
    })
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    triggering.sync = false
  }
}

function watch(row) {
  current.value = row
  startPolling()
}

function startPolling() {
  stopPolling()
  timer = setInterval(async () => {
    if (!current.value) return
    try {
      const r = await tasksApi.status(current.value.task_id)
      current.value = r
      scrollLog()
      if (['success', 'failed'].includes(r.status)) {
        stopPolling()
        loadRecent()
      }
    } catch {
      stopPolling()
    }
  }, 1500)
}

function stopPolling() {
  if (timer) { clearInterval(timer); timer = null }
}

function scrollLog() {
  nextTick(() => {
    const el = logBoxRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

async function loadRecent() {
  try {
    const r = await tasksApi.list({ limit: 10 })
    recent.value = r.items
  } catch {}
}

async function resetCheckpoint() {
  try {
    await ElMessageBox.confirm(
      '将清空 daily_kline 的断点,下次更新会重新拉取所有股票。是否继续?',
      '确认',
      { type: 'warning' },
    )
    await tasksApi.resetCheckpoint('kline_daily')
    ElMessage.success('已重置')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.message || e)
  }
}

onMounted(loadRecent)
onUnmounted(stopPolling)
</script>

<style scoped>
.task-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}
@media (max-width: 1100px) {
  .task-actions { grid-template-columns: 1fr; }
}
.task-card {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 16px 20px;
  background: #fafbfc;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.task-card-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.task-card-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
  flex: 1;
}
.task-card-desc {
  color: #606266;
  font-size: 13px;
  line-height: 1.6;
  padding: 8px 12px;
  background: var(--bg-card);
  border-radius: 4px;
  border: 1px dashed var(--border-color-dark);
}
.task-card-foot {
  display: flex;
  justify-content: flex-end;
  padding-top: 4px;
}
.form-hint {
  margin-left: 8px;
  color: #909399;
  font-size: 12px;
}
</style>