<template>
  <div>
    <!-- 全局状态 -->
    <el-row :gutter="16">
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-icon" :class="globalStatus.enabled ? 'green' : 'gray'">
            <el-icon><AlarmClock /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-label">调度器</div>
            <div class="stat-value">
              <el-tag :type="globalStatus.enabled ? 'success' : 'info'" size="large">
                {{ globalStatus.enabled ? '运行中' : '已停止' }}
              </el-tag>
            </div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-icon blue">
            <el-icon><Clock /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-label">下次运行</div>
            <div class="stat-value" style="font-size:16px;">
              {{ globalStatus.next_run_at || '-' }}
            </div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-icon orange">
            <el-icon><Loading /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-label">启用任务</div>
            <div class="stat-value">
              {{ enabledCount }} / {{ jobs.length }}
            </div>
            <div class="stat-sub">每类独立启停</div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-icon purple">
            <el-icon><Histogram /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-label">最近运行</div>
            <div class="stat-value">{{ recentTasks.length }} 次</div>
            <div class="stat-sub">最近 {{ recentTasks.length }} 条</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 3 个主 Tab -->
    <div class="page-card">
      <el-tabs v-model="mainTab" type="border-card">
        <!-- Tab 1: 计划 -->
        <el-tab-pane name="plan">
          <template #label><span><el-icon><Calendar /></el-icon>计划</span></template>

          <div class="toolbar" style="margin-bottom: 12px;">
            <h3 class="page-title" style="margin:0;">
              <el-icon><Setting /></el-icon>
              调度控制
            </h3>
            <span class="grow"></span>
            <el-button v-if="!globalStatus.enabled" type="primary" :loading="operating" @click="startScheduler">
              <el-icon><VideoPlay /></el-icon>启动调度
            </el-button>
            <el-button v-else type="danger" :loading="operating" @click="stopScheduler">
              <el-icon><VideoPause /></el-icon>停止调度
            </el-button>
            <el-button @click="loadAll" :loading="loading">
              <el-icon><Refresh /></el-icon>刷新状态
            </el-button>
          </div>
          <el-alert type="info" :closable="false" style="margin-bottom: 12px;">
            每个 Tab 控制一类数据的独立 cron。修改任一 Tab 的 cron/参数后点 <b>保存</b> 即可热生效；点 <b>立即触发</b> 可单独运行该类任务，无需等调度周期。
          </el-alert>

          <!-- 按数据类型 Tab -->
          <el-tabs v-model="activeTab" type="card">
            <!-- 1) 拉取数据(全量) -->
            <el-tab-pane name="fetch_all">
              <template #label>
                <span><el-icon><Download /></el-icon>拉取数据(全量)</span>
              </template>
              <JobPanel
                v-if="jobByTask('fetch_all')"
                :job="jobByTask('fetch_all')"
                :saving="savingTask === 'fetch_all'"
                :triggering="triggeringTask === 'fetch_all'"
                @save="(body) => saveJob('fetch_all', body)"
                @trigger="triggerJob('fetch_all')"
              >
                <template #params>
                  <el-alert type="info" :closable="false" style="margin-bottom: 8px;">
                    一次性完成:股票列表 → 行业映射 → 全市场 K线 → 主要指数。<br/>
                    适合首次部署 / 换数据源 / 长时间未更新。日常请用「增量同步」。
                  </el-alert>
                  <el-form-item label="K线回溯">
                    <el-input-number v-model="forms.fetch_all.days_back" :min="0" :max="3650" />
                    <span style="margin-left:8px;color:#909399;font-size:12px;">
                      {{ forms.fetch_all.days_back === 0 ? '0=自上市以来全量' : '天' }}
                    </span>
                  </el-form-item>
                  <el-form-item label="复权方式">
                    <el-radio-group v-model="forms.fetch_all.adjust">
                      <el-radio-button value="qfq">前复权</el-radio-button>
                      <el-radio-button value="hfq">后复权</el-radio-button>
                    </el-radio-group>
                  </el-form-item>
                  <el-form-item label="并发线程">
                    <el-input-number v-model="forms.fetch_all.workers" :min="1" :max="16" />
                    <span style="margin-left:8px;color:#909399;font-size:12px;">建议 ≤ 4</span>
                  </el-form-item>
                  <el-form-item label="跳过增强">
                    <el-switch v-model="forms.fetch_all.skip_enrich" />
                    <span style="margin-left:8px;color:#909399;font-size:12px;">
                      ON=跳过 stock_enrich(更快);OFF=行业映射 + 上市日期
                    </span>
                  </el-form-item>
                </template>
              </JobPanel>
            </el-tab-pane>

            <!-- 2) 增量同步 -->
            <el-tab-pane name="sync_latest">
              <template #label>
                <span><el-icon><Refresh /></el-icon>增量同步</span>
              </template>
              <JobPanel
                v-if="jobByTask('sync_latest')"
                :job="jobByTask('sync_latest')"
                :saving="savingTask === 'sync_latest'"
                :triggering="triggeringTask === 'sync_latest'"
                @save="(body) => saveJob('sync_latest', body)"
                @trigger="triggerJob('sync_latest')"
              >
                <template #params>
                  <el-alert type="info" :closable="false" style="margin-bottom: 8px;">
                    智能增量:同步股票列表(新上市/退市)+ 仅拉缺失/过期 K线 + 主要指数。<br/>
                    推荐每天 16:30 调度一次。
                  </el-alert>
                  <el-form-item label="回溯天数">
                    <el-input-number v-model="forms.sync_latest.days_back" :min="1" :max="120" />
                    <span style="margin-left:8px;color:#909399;font-size:12px;">
                      覆盖最近交易日(一般 10 天够用)
                    </span>
                  </el-form-item>
                  <el-form-item label="复权方式">
                    <el-radio-group v-model="forms.sync_latest.adjust">
                      <el-radio-button value="qfq">前复权</el-radio-button>
                      <el-radio-button value="hfq">后复权</el-radio-button>
                    </el-radio-group>
                  </el-form-item>
                  <el-form-item label="并发线程">
                    <el-input-number v-model="forms.sync_latest.workers" :min="1" :max="16" />
                    <span style="margin-left:8px;color:#909399;font-size:12px;">建议 ≤ 4</span>
                  </el-form-item>
                  <el-form-item label="同步列表">
                    <el-switch v-model="forms.sync_latest.update_stock_list" />
                    <span style="margin-left:8px;color:#909399;font-size:12px;">
                      ON=同时 UPSERT 股票列表(捕获新上市/退市)
                    </span>
                  </el-form-item>
                </template>
              </JobPanel>
            </el-tab-pane>
          </el-tabs>
        </el-tab-pane>

        <!-- Tab 2: 即时触发 -->
        <el-tab-pane name="trigger">
          <template #label><span><el-icon><VideoPlay /></el-icon>即时触发</span></template>

          <el-alert type="info" :closable="false" show-icon style="margin-bottom: 16px;">
            仅两个入口:<b>拉取数据</b>(首次/换源)和<b>增量同步</b>(日常)。所有拉取任务会写到 <code>data/stock.db</code>。
          </el-alert>

          <el-form :model="triggerForm" label-width="100px" style="max-width:640px;">
            <el-form-item label="任务类型">
              <el-radio-group v-model="triggerForm.task" style="display:flex; gap:12px;">
                <el-radio-button value="fetch_all">
                  <el-icon><Download /></el-icon>拉取数据
                </el-radio-button>
                <el-radio-button value="sync_latest">
                  <el-icon><Refresh /></el-icon>增量同步
                </el-radio-button>
              </el-radio-group>
            </el-form-item>

            <!-- 公共:复权方式 -->
            <el-form-item label="复权方式">
              <el-radio-group v-model="triggerForm.adjust">
                <el-radio-button value="qfq">前复权</el-radio-button>
                <el-radio-button value="hfq">后复权</el-radio-button>
              </el-radio-group>
            </el-form-item>

            <!-- fetch_all 专属 -->
            <template v-if="triggerForm.task === 'fetch_all'">
              <el-form-item label="全量拉取 (自上市以来)">
                <el-switch v-model="triggerForm.fullSinceListDate" />
                <span style="margin-left:8px;color:#909399;font-size:12px;">
                  默认开启 · 关闭后按下方「K线回溯」天数拉取
                </span>
              </el-form-item>
              <el-form-item label="K线回溯">
                <el-input-number
                  v-model="triggerForm.days_back"
                  :min="0" :max="3650" :disabled="triggerForm.fullSinceListDate"
                />
                <span style="margin-left:8px;color:#909399;font-size:12px;">
                  {{ triggerForm.fullSinceListDate ? '已按各股上市日期(0=自上市以来)' : '天' }}
                </span>
              </el-form-item>
              <el-form-item label="并发线程">
                <el-input-number v-model="triggerForm.workers" :min="1" :max="16" />
              </el-form-item>
              <el-form-item label="跳过增强">
                <el-switch v-model="triggerForm.skip_enrich" />
                <span style="margin-left:8px;color:#909399;font-size:12px;">
                  跳过可大幅加速(但行业映射会缺)
                </span>
              </el-form-item>
            </template>

            <!-- sync_latest 专属 -->
            <template v-if="triggerForm.task === 'sync_latest'">
              <el-form-item label="回溯天数">
                <el-input-number v-model="triggerForm.days_back" :min="1" :max="120" />
                <span style="margin-left:8px;color:#909399;font-size:12px;">覆盖最近交易日</span>
              </el-form-item>
              <el-form-item label="并发线程">
                <el-input-number v-model="triggerForm.workers" :min="1" :max="16" />
              </el-form-item>
              <el-form-item label="限定代码">
                <el-input
                  v-model="triggerForm.codesText"
                  placeholder="600000, 000001(可选,逗号分隔;留空=全部)"
                  style="width:380px;"
                />
              </el-form-item>
              <el-form-item label="同步列表">
                <el-switch v-model="triggerForm.update_stock_list" />
              </el-form-item>
            </template>

            <el-form-item>
              <el-button type="primary" :loading="triggering" @click="doTrigger">
                <el-icon><VideoPlay /></el-icon>开始任务
              </el-button>
              <el-button @click="doResetCheckpoint">
                <el-icon><Refresh /></el-icon>重置断点
              </el-button>
            </el-form-item>
          </el-form>

          <!-- 任务进度 -->
          <div v-if="currentTask" class="task-progress-card">
            <h3 class="page-title task-progress-title">
              当前任务:<el-tag>{{ taskDisplayName }}</el-tag>
              <el-tag :type="statusType" style="margin-left:8px;">{{ statusText }}</el-tag>
              <span class="task-id">任务ID: {{ currentTask.task_id }}</span>
            </h3>

            <el-steps
              :active="activeStageIndex"
              :process-status="stepProcessStatus"
              :finish-status="stepFinishStatus"
              align-center
              class="task-steps"
            >
              <el-step
                v-for="stage in taskStages"
                :key="stage.key"
                :title="stage.label"
              />
            </el-steps>

            <div class="progress-summary">
              <div class="progress-row">
                <span>{{ progressSummary }}</span>
                <strong>{{ progressPercent }}%</strong>
              </div>
              <el-progress
                :percentage="progressPercent"
                :status="progressBarStatus"
                :stroke-width="16"
              />
              <div v-if="progressStats" class="progress-stats">{{ progressStats }}</div>
            </div>

            <el-alert
              v-if="hasTaskError"
              title="任务执行出现问题"
              type="error"
              :closable="false"
              show-icon
              class="task-error"
            >
              <template #default>
                <div v-if="currentTask.message">{{ currentTask.message }}</div>
                <pre v-if="errorLines.length" class="error-detail">{{ errorLines.join('\n') }}</pre>
              </template>
            </el-alert>

            <div class="task-time">
              开始: {{ currentTask.started_at || '-' }} · 结束: {{ currentTask.ended_at || '-' }}
            </div>
          </div>
        </el-tab-pane>

        <!-- Tab 3: 运行历史 -->
        <el-tab-pane name="history">
          <template #label><span><el-icon><Histogram /></el-icon>运行历史</span></template>

          <el-table :data="recentTasks" stripe>
            <el-table-column prop="started_at" label="开始时间" width="180" />
            <el-table-column prop="task_name" label="任务" width="160">
              <template #default="{ row }">
                <el-tag size="small">{{ row.task_name }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="statusTypeOf(row.status)" size="small">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="message" label="消息" />
            <el-table-column label="操作" width="80">
              <template #default="{ row }">
                <el-button size="small" link @click="watchTask(row)">查看</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { schedulerApi, tasksApi } from '@/api/modules'
import JobPanel from './scheduler/JobPanel.vue'

const mainTab = ref('plan')
const jobs = ref([])
const history = ref([])
const recentTasks = ref([])
const globalStatus = ref({ enabled: false, next_run_at: null })
const operating = ref(false)
const loading = ref(false)
const savingTask = ref('')
const triggeringTask = ref('')
const activeTab = ref('stock_list')

// 各 Tab 的参数表单(保存时合并)
const forms = reactive({
  fetch_all:    { days_back: 0, adjust: 'qfq', workers: 4, skip_enrich: false },
  sync_latest:  { days_back: 10,  adjust: 'qfq', workers: 4, update_stock_list: true },
})

// 即时触发 Tab 的表单
const triggerForm = reactive({
  task: 'sync_latest',
  adjust: 'qfq',
  days_back: 0,
  fullSinceListDate: true,   // fetch_all 默认全量自上市以来
  workers: 4,
  skip_enrich: false,
  update_stock_list: true,
  codesText: '',
})
const triggering = ref(false)
const currentTask = ref(null)
let pollTimer = null

const TASK_META = {
  fetch_all: {
    label: '全量拉取数据',
    stages: [
      { key: 'stock_list', label: '股票列表' },
      { key: 'stock_enrich', label: '行业增强' },
      { key: 'kline_daily', label: '日K线' },
      { key: 'index_daily', label: '指数数据' },
    ],
  },
  sync_latest: {
    label: '增量同步到最新',
    stages: [
      { key: 'stock_list', label: '股票列表' },
      { key: 'kline_daily', label: '日K线' },
      { key: 'index_daily', label: '指数数据' },
    ],
  },
}

const taskType = computed(() => {
  const name = currentTask.value?.task_name || ''
  if (name.startsWith('fetch_all')) return 'fetch_all'
  if (name.startsWith('sync_latest')) return 'sync_latest'
  return triggerForm.task
})
const taskMeta = computed(() => TASK_META[taskType.value] || TASK_META.sync_latest)
const taskDisplayName = computed(() => taskMeta.value.label)
const taskStages = computed(() => {
  const stages = taskMeta.value.stages
  if (taskType.value !== 'sync_latest' || triggerForm.update_stock_list) return stages
  return stages.filter(stage => stage.key !== 'stock_list')
})
const currentStage = computed(() => currentTask.value?.progress?.stage || '')
const activeStageIndex = computed(() => {
  if (currentTask.value?.status === 'success' || currentStage.value === 'all') {
    return taskStages.value.length
  }
  const index = taskStages.value.findIndex(stage => stage.key === currentStage.value)
  return index >= 0 ? index : 0
})
const progressPercent = computed(() => {
  if (currentTask.value?.status === 'success') return 100
  const progress = currentTask.value?.progress || {}
  const total = Number(progress.total || progress.total_count || 0)
  const completed = Number(progress.completed || progress.done || progress.current || 0)
  if (total > 0 && completed >= 0) {
    return Math.min(99, Math.round(completed / total * 100))
  }
  const count = taskStages.value.length || 1
  const index = taskStages.value.findIndex(stage => stage.key === currentStage.value)
  if (index < 0) return currentTask.value?.status === 'running' ? 3 : 0
  const stageDone = progress.status === 'done' ? 1 : 0.25
  return Math.min(99, Math.round((index + stageDone) / count * 100))
})
const progressSummary = computed(() => {
  const status = currentTask.value?.status
  if (status === 'pending') return '等待执行'
  if (status === 'success') return '数据更新完成'
  if (status === 'failed') return '数据更新失败'
  const stage = taskStages.value.find(item => item.key === currentStage.value)
  return stage ? `正在更新：${stage.label}` : '正在准备数据更新'
})
const progressStats = computed(() => {
  const p = currentTask.value?.progress || {}
  const parts = []
  const total = Number(p.total || p.total_count || 0)
  const completed = Number(p.completed || p.done || p.current || 0)
  if (total > 0) parts.push(`已处理 ${completed}/${total}`)
  if (p.success != null) parts.push(`成功 ${p.success}`)
  if (p.failed != null) parts.push(`失败 ${p.failed}`)
  if (p.rows != null) parts.push(`写入 ${p.rows} 行`)
  return parts.join(' · ')
})
const statusText = computed(() => ({
  pending: '等待中', running: '执行中', success: '已完成', failed: '失败',
}[currentTask.value?.status] || currentTask.value?.status || '未知'))
const errorLines = computed(() => (currentTask.value?.log_tail || []).filter(line =>
  /\bERROR\b|失败|Exception|Traceback/i.test(line),
))
const hasTaskError = computed(() => currentTask.value?.status === 'failed' || errorLines.value.length > 0)
const progressBarStatus = computed(() => currentTask.value?.status === 'success'
  ? 'success' : currentTask.value?.status === 'failed' ? 'exception' : '')
const stepProcessStatus = computed(() => currentTask.value?.status === 'failed' ? 'error' : 'process')
const stepFinishStatus = computed(() => currentTask.value?.status === 'failed' ? 'error' : 'success')

const enabledCount = computed(() => jobs.value.filter(j => j.enabled).length)

function jobByTask(task) {
  return jobs.value.find(j => j.task === task)
}

function statusTypeOf(s) {
  return s === 'success' ? 'success'
    : s === 'failed' ? 'danger'
    : s === 'running' ? 'warning' : 'info'
}
const statusType = computed(() => currentTask.value ? statusTypeOf(currentTask.value.status) : 'info')

async function loadAll() {
  loading.value = true
  try {
    const [s, j] = await Promise.all([schedulerApi.status(), schedulerApi.listJobs()])
    globalStatus.value = {
      enabled: s.enabled,
      running: s.running,
      next_run_at: s.next_run_at,
    }
    jobs.value = j
    for (const jb of jobs.value) {
      if (jb.task in forms && jb.params && typeof jb.params === 'object') {
        Object.assign(forms[jb.task], jb.params)
      }
    }
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function loadRecent() {
  try {
    const r = await tasksApi.list({ limit: 20 })
    recentTasks.value = r.items
  } catch {}
}

async function startScheduler() {
  operating.value = true
  try {
    const r = await schedulerApi.start({})
    globalStatus.value.enabled = r.enabled
    globalStatus.value.next_run_at = r.next_run_at
    ElMessage.success('调度已启动')
    loadAll()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    operating.value = false
  }
}

async function stopScheduler() {
  try {
    await ElMessageBox.confirm('确定停止调度器吗?当前正在执行的任务会继续完成。', '确认', { type: 'warning' })
  } catch { return }
  operating.value = true
  try {
    await schedulerApi.stop()
    globalStatus.value.enabled = false
    globalStatus.value.next_run_at = null
    ElMessage.success('调度已停止')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    operating.value = false
  }
}

async function saveJob(task, body) {
  savingTask.value = task
  try {
    const params = { ...(body.params || {}), ...forms[task] }
    await schedulerApi.updateJob(task, {
      cron: body.cron,
      enabled: body.enabled,
      params,
    })
    ElMessage.success(`${task} 配置已热生效`)
    loadAll()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    savingTask.value = ''
  }
}

async function triggerJob(task) {
  try {
    await ElMessageBox.confirm(
      `立即触发 [${task}] 任务?根据数据量可能持续数分钟到数十分钟。`,
      '立即运行', { type: 'warning' },
    )
  } catch { return }
  triggeringTask.value = task
  try {
    await schedulerApi.triggerJob(task)
    ElMessage.success(`已触发 ${task}`)
    loadAll()
    loadRecent()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    triggeringTask.value = ''
  }
}

// ============== 即时触发 Tab ==============
function parseCodes(text) {
  if (!text) return null
  const codes = text.split(/[,;\s]+/).map(s => s.trim()).filter(Boolean)
  return codes.length ? codes : null
}

async function doTrigger() {
  const params = {}
  const t = triggerForm.task
  params.adjust = triggerForm.adjust

  if (t === 'fetch_all') {
    // "全量拉取 (自上市以来)" 开启时,days_back 固定为 0,后端按各股 list_date 拉取
    params.days_back = triggerForm.fullSinceListDate ? 0 : triggerForm.days_back
    params.workers = triggerForm.workers
    params.skip_enrich = triggerForm.skip_enrich
  } else if (t === 'sync_latest') {
    params.days_back = triggerForm.days_back
    params.workers = triggerForm.workers
    params.update_stock_list = triggerForm.update_stock_list
    const codes = parseCodes(triggerForm.codesText)
    if (codes) params.codes = codes
  }

  triggering.value = true
  try {
    const r = await tasksApi.trigger({ task: t, params })
    currentTask.value = {
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

async function doResetCheckpoint() {
  try {
    await ElMessageBox.confirm(
      '将清空该任务的断点,下次更新会重新拉取所有股票。是否继续?',
      '确认', { type: 'warning' },
    )
  } catch { return }
  try {
    // 新任务 fetch_all / sync_latest 内部使用的子任务断点
    await tasksApi.resetCheckpoint('kline_daily')
    ElMessage.success('已重置断点')
  } catch (e) {
    ElMessage.error(e.message || e)
  }
}

function watchTask(row) {
  mainTab.value = 'trigger'
  currentTask.value = row
  if (['pending', 'running'].includes(row.status)) startPolling()
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    if (!currentTask.value) return
    try {
      const r = await tasksApi.status(currentTask.value.task_id)
      currentTask.value = r
      if (['success', 'failed'].includes(r.status)) {
        stopPolling()
        loadRecent()
      }
    } catch { stopPolling() }
  }, 1500)
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

let timer = null
onMounted(() => {
  loadAll()
  loadRecent()
  timer = setInterval(() => { loadAll(); loadRecent() }, 30000)
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
  stopPolling()
})
</script>

<style scoped>
.task-progress-card {
  margin-top: 16px;
  padding: 18px 20px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  background: #fff;
}

.task-progress-title {
  margin: 0;
}

.task-id {
  float: right;
  color: #909399;
  font-size: 12px;
  font-weight: normal;
}

.task-steps {
  margin: 24px 20px 20px;
}

.progress-summary {
  padding: 14px 16px;
  border-radius: 6px;
  background: #f5f7fa;
}

.progress-row {
  display: flex;
  justify-content: space-between;
  margin-bottom: 9px;
  color: #606266;
}

.progress-stats,
.task-time {
  margin-top: 8px;
  color: #909399;
  font-size: 12px;
}

.task-error {
  margin-top: 14px;
}

.error-detail {
  max-height: 220px;
  margin: 8px 0 0;
  padding: 10px;
  overflow: auto;
  white-space: pre-wrap;
  color: #c45656;
  background: #fff;
  border-radius: 4px;
  font-family: Consolas, monospace;
  font-size: 12px;
}

@media (max-width: 768px) {
  .task-id {
    display: block;
    float: none;
    margin-top: 8px;
  }

  .task-steps {
    margin-right: 0;
    margin-left: 0;
  }
}
</style>