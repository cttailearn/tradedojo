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
            <!-- 1) 股票基础信息 -->
            <el-tab-pane name="stock_list">
              <template #label>
                <span><el-icon><List /></el-icon>股票基础信息</span>
              </template>
              <JobPanel
                v-if="jobByTask('stock_list')"
                :job="jobByTask('stock_list')"
                :saving="savingTask === 'stock_list'"
                :triggering="triggeringTask === 'stock_list'"
                @save="(body) => saveJob('stock_list', body)"
                @trigger="triggerJob('stock_list')"
              >
                <template #params>
                  <el-form-item label="强制全量">
                    <el-switch v-model="forms.stock_list.full_refresh" />
                    <span style="margin-left:8px;color:#909399;font-size:12px;">
                      ON 时清空 stock_list 后重建(IPO/退市改名时使用)
                    </span>
                  </el-form-item>
                </template>
              </JobPanel>
            </el-tab-pane>

            <!-- 2) 主要指数 -->
            <el-tab-pane name="index_daily">
              <template #label>
                <span><el-icon><TrendCharts /></el-icon>主要指数</span>
              </template>
              <JobPanel
                v-if="jobByTask('index_daily')"
                :job="jobByTask('index_daily')"
                :saving="savingTask === 'index_daily'"
                :triggering="triggeringTask === 'index_daily'"
                @save="(body) => saveJob('index_daily', body)"
                @trigger="triggerJob('index_daily')"
              >
                <template #params>
                  <el-alert type="info" :closable="false">
                    默认维护 5 只主要指数(sh000001 / sh000300 / sh000016 / sz399001 / sz399006)。
                  </el-alert>
                </template>
              </JobPanel>
            </el-tab-pane>

            <!-- 3) 日 K 线 -->
            <el-tab-pane name="kline_daily">
              <template #label>
                <span><el-icon><DataLine /></el-icon>日 K 线</span>
              </template>
              <JobPanel
                v-if="jobByTask('kline_daily')"
                :job="jobByTask('kline_daily')"
                :saving="savingTask === 'kline_daily'"
                :triggering="triggeringTask === 'kline_daily'"
                @save="(body) => saveJob('kline_daily', body)"
                @trigger="triggerJob('kline_daily')"
              >
                <template #params>
                  <el-form-item label="更新模式">
                    <el-radio-group v-model="forms.kline_daily.mode">
                      <el-radio-button value="smart">智能增量</el-radio-button>
                      <el-radio-button value="full">全量回溯</el-radio-button>
                    </el-radio-group>
                    <span style="margin-left:8px;color:#909399;font-size:12px;">
                      smart=仅缺失/过期股票;full=按回溯天数全量重拉
                    </span>
                  </el-form-item>
                  <el-form-item label="复权方式">
                    <el-radio-group v-model="forms.kline_daily.adjust">
                      <el-radio-button value="qfq">前复权</el-radio-button>
                      <el-radio-button value="hfq">后复权</el-radio-button>
                    </el-radio-group>
                  </el-form-item>
                  <el-form-item label="回溯天数">
                    <el-input-number v-model="forms.kline_daily.days_back" :min="30" :max="3650" />
                    <span style="margin-left:8px;color:#909399;font-size:12px;">
                      full 模式回溯;smart 模式为增量窗口
                    </span>
                  </el-form-item>
                  <el-form-item label="并发线程">
                    <el-input-number v-model="forms.kline_daily.workers" :min="1" :max="32" />
                  </el-form-item>
                </template>
              </JobPanel>
            </el-tab-pane>

            <!-- 4) 股票信息增强 -->
            <el-tab-pane name="stock_enrich">
              <template #label>
                <span><el-icon><MagicStick /></el-icon>股票信息增强</span>
              </template>
              <JobPanel
                v-if="jobByTask('stock_enrich')"
                :job="jobByTask('stock_enrich')"
                :saving="savingTask === 'stock_enrich'"
                :triggering="triggeringTask === 'stock_enrich'"
                @save="(body) => saveJob('stock_enrich', body)"
                @trigger="triggerJob('stock_enrich')"
              >
                <template #params>
                  <el-form-item label="限制条数">
                    <el-input-number v-model="forms.stock_enrich.limit" :min="0" />
                    <span style="margin-left:8px;color:#909399;font-size:12px;">
                      0 = 处理全部;测试时设小值
                    </span>
                  </el-form-item>
                  <el-form-item label="Phase 2 并发">
                    <el-input-number v-model="forms.stock_enrich.workers" :min="0" :max="16" />
                    <span style="margin-left:8px;color:#909399;font-size:12px;">
                      0 = 跳过 profile API(用 K线 兜底取上市日期)
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

          <el-form :model="triggerForm" label-width="100px" style="max-width:640px;">
            <el-form-item label="任务类型">
              <el-select v-model="triggerForm.task" style="width:240px;">
                <el-option label="更新股票列表 (stock_list)" value="stock_list" />
                <el-option label="主要指数 (index_daily)" value="index_daily" />
                <el-option label="日 K 线 (kline_daily)" value="kline_daily" />
                <el-option label="股票信息增强 (stock_enrich)" value="stock_enrich" />
                <el-option label="[旧] 主要指数 (index)" value="index" />
                <el-option label="[旧] 增强信息 (enrich)" value="enrich" />
                <el-option label="[旧] 智能增量 (daily_smart)" value="daily_smart" />
              </el-select>
            </el-form-item>

            <template v-if="triggerForm.task === 'kline_daily' || triggerForm.task === 'daily_smart'">
              <el-form-item label="更新模式">
                <el-radio-group v-model="triggerForm.mode">
                  <el-radio-button value="smart">智能增量</el-radio-button>
                  <el-radio-button value="full">全量回溯</el-radio-button>
                </el-radio-group>
              </el-form-item>
              <el-form-item label="复权方式">
                <el-radio-group v-model="triggerForm.adjust">
                  <el-radio-button value="qfq">前复权</el-radio-button>
                  <el-radio-button value="hfq">后复权</el-radio-button>
                </el-radio-group>
              </el-form-item>
              <el-form-item label="回溯天数">
                <el-input-number v-model="triggerForm.days_back" :min="30" :max="3650" />
              </el-form-item>
              <el-form-item label="并发线程">
                <el-input-number v-model="triggerForm.workers" :min="1" :max="32" />
              </el-form-item>
              <el-form-item label="限定代码">
                <el-input
                  v-model="triggerForm.codesText"
                  placeholder="600000, 000001(可选,逗号分隔;留空=全部)"
                  style="width:380px;"
                />
              </el-form-item>
            </template>

            <template v-if="triggerForm.task === 'stock_enrich' || triggerForm.task === 'enrich'">
              <el-form-item label="限制条数">
                <el-input-number v-model="triggerForm.limit" :min="0" />
                <span style="margin-left:8px;color:#909399;font-size:12px;">0 = 处理全部</span>
              </el-form-item>
              <el-form-item label="Phase 2 并发">
                <el-input-number v-model="triggerForm.workers" :min="0" :max="16" />
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

          <!-- 实时日志 -->
          <div v-if="currentTask" style="margin-top: 16px;">
            <h3 class="page-title">
              当前任务:<el-tag>{{ currentTask.task_name }}</el-tag>
              <el-tag :type="statusType" style="margin-left:8px;">{{ currentTask.status }}</el-tag>
              <span style="float:right; color:#909399; font-weight:normal; font-size:12px;">
                任务ID: {{ currentTask.task_id }}
              </span>
            </h3>
            <div class="task-log" ref="logBoxRef">
              <span
                v-for="(line, idx) in currentTask.log_tail || []"
                :key="idx"
                class="log-line"
                :class="logClass(line)"
              >{{ line }}</span>
            </div>
            <div style="margin-top:8px;">
              <span style="color:#909399;font-size:12px;">
                开始: {{ currentTask.started_at || '-' }} · 结束: {{ currentTask.ended_at || '-' }}
              </span>
              <span v-if="currentTask.message" style="margin-left:12px;color:#909399;font-size:12px;">
                消息: {{ currentTask.message }}
              </span>
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
import { ref, reactive, onMounted, onUnmounted, computed, nextTick } from 'vue'
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
  stock_list:    { full_refresh: false },
  index_daily:   {},
  kline_daily:   { mode: 'smart', adjust: 'qfq', days_back: 365, workers: 6 },
  stock_enrich:  { limit: 0, workers: 4 },
})

// 即时触发 Tab 的表单
const triggerForm = reactive({
  task: 'kline_daily',
  mode: 'smart',
  adjust: 'qfq',
  days_back: 365,
  workers: 6,
  limit: 0,
  codesText: '',
})
const triggering = ref(false)
const currentTask = ref(null)
const logBoxRef = ref(null)
let pollTimer = null

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

function logClass(line) {
  if (/ERROR|失败|Exception/i.test(line)) return 'log-error'
  if (/WARN|警告/i.test(line)) return 'log-warning'
  return 'log-info'
}

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
  if (t === 'kline_daily' || t === 'daily_smart') {
    params.mode = triggerForm.mode
    params.adjust = triggerForm.adjust
    params.days_back = triggerForm.days_back
    params.workers = triggerForm.workers
    const codes = parseCodes(triggerForm.codesText)
    if (codes) params.codes = codes
  } else if (t === 'stock_enrich' || t === 'enrich') {
    params.limit = triggerForm.limit
    params.workers = triggerForm.workers
  }
  // 旧别名 daily_smart 强制 mode=smart
  if (t === 'daily_smart') params.mode = 'smart'

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
    await tasksApi.resetCheckpoint(triggerForm.task)
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
      scrollLog()
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

function scrollLog() {
  nextTick(() => {
    const el = logBoxRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
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