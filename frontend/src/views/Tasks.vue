<template>
  <div>
    <div class="page-card">
      <h3 class="page-title">触发更新任务</h3>
      <el-form :model="form" label-width="100px" style="max-width:640px;">
        <el-form-item label="任务类型">
          <el-select v-model="form.task" style="width:240px;">
            <el-option label="更新股票列表" value="stock_list" />
            <el-option label="更新日K线" value="kline_daily" />
            <el-option label="更新主要指数" value="index" />
            <el-option label="丰富股票信息" value="enrich" />
            <el-option label="智能增量更新" value="daily_smart" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.task === 'kline_daily'" label="复权方式">
          <el-radio-group v-model="form.adjust">
            <el-radio-button value="qfq">前复权</el-radio-button>
            <el-radio-button value="hfq">后复权</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="needsDays" label="回溯天数">
          <el-input-number v-model="form.days" :min="30" :max="3650" />
        </el-form-item>
        <el-form-item label="并发线程数">
          <el-input-number v-model="form.workers" :min="1" :max="32" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="triggering" @click="trigger">
            <el-icon><VideoPlay /></el-icon>开始任务
          </el-button>
          <el-button @click="resetCheckpoint">
            <el-icon><Refresh /></el-icon>重置断点
          </el-button>
        </el-form-item>
      </el-form>
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

const form = reactive({ task: 'kline_daily', adjust: 'qfq', days: 365, workers: 8 })
const triggering = ref(false)
const current = ref(null)
const recent = ref([])
const logBoxRef = ref(null)
let timer = null

const needsDays = computed(() => form.task === 'kline_daily' || form.task === 'daily_smart')

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

async function trigger() {
  triggering.value = true
  try {
    const r = await tasksApi.trigger(form)
    current.value = {
      task_id: r.task_id, task_name: r.task_name,
      status: 'pending', log_tail: [],
    }
    ElMessage.success(`已派发任务: ${r.task_name}`)
    startPolling()
    loadRecent()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    triggering.value = false
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
    await tasksApi.resetCheckpoint('daily_kline')
    ElMessage.success('已重置')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.message || e)
  }
}

onMounted(loadRecent)
onUnmounted(stopPolling)
</script>