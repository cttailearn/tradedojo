<template>
  <div>
    <!-- 状态卡片 -->
    <el-row :gutter="16">
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-icon" :class="status.enabled ? 'green' : 'gray'">
            <el-icon><AlarmClock /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-label">调度器状态</div>
            <div class="stat-value">
              <el-tag :type="status.enabled ? 'success' : 'info'" size="large">
                {{ status.enabled ? '运行中' : '已停止' }}
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
            <div class="stat-label">执行时间</div>
            <div class="stat-value">{{ status.config?.time || '--:--' }}</div>
            <div class="stat-sub">每天</div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-icon orange">
            <el-icon><Loading /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-label">下次运行</div>
            <div class="stat-value" style="font-size:16px;">
              {{ status.next_run_at || '-' }}
            </div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-icon purple">
            <el-icon><Histogram /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-label">历史运行</div>
            <div class="stat-value">{{ status.history_count || 0 }} 次</div>
            <div class="stat-sub">最近 20 次</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 控制面板 -->
    <div class="page-card">
      <h3 class="page-title">
        <el-icon><Setting /></el-icon>
        调度配置
      </h3>

      <el-form :model="form" label-width="120px" style="max-width:720px;">
        <el-form-item label="执行时间">
          <el-time-picker
            v-model="form.time"
            format="HH:mm"
            value-format="HH:mm"
            placeholder="选择时间"
            style="width:160px;"
          />
          <span style="margin-left:12px; color:#909399; font-size:12px;">
            每天在该时间自动执行所选任务
          </span>
        </el-form-item>

        <el-form-item label="执行任务">
          <el-checkbox-group v-model="form.tasks">
            <el-checkbox label="stock_list">股票列表</el-checkbox>
            <el-checkbox label="index">主要指数</el-checkbox>
            <el-checkbox label="kline_daily">日K线</el-checkbox>
            <el-checkbox label="enrich">股票信息丰富</el-checkbox>
            <el-checkbox label="daily_smart">智能增量更新</el-checkbox>
          </el-checkbox-group>
        </el-form-item>

        <el-form-item label="日K复权" v-if="form.tasks.includes('kline_daily') || form.tasks.includes('daily_smart')">
          <el-radio-group v-model="form.adjust">
            <el-radio-button value="qfq">前复权</el-radio-button>
            <el-radio-button value="hfq">后复权</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="回溯天数" v-if="form.tasks.includes('kline_daily') || form.tasks.includes('daily_smart')">
          <el-input-number v-model="form.days" :min="30" :max="3650" />
          <span style="margin-left:12px; color:#909399; font-size:12px;">
            首次拉取的历史天数(增量更新时为窗口大小)
          </span>
        </el-form-item>

        <el-form-item label="并发线程数">
          <el-input-number v-model="form.workers" :min="1" :max="32" />
        </el-form-item>

        <el-form-item>
          <el-button
            v-if="!status.enabled"
            type="primary"
            :loading="operating"
            @click="startScheduler"
          >
            <el-icon><VideoPlay /></el-icon>启动调度
          </el-button>
          <el-button
            v-else
            type="danger"
            :loading="operating"
            @click="stopScheduler"
          >
            <el-icon><VideoPause /></el-icon>停止调度
          </el-button>

          <el-button :loading="operating" @click="saveConfig" v-if="status.enabled">
            <el-icon><Refresh /></el-icon>保存配置(热更新)
          </el-button>

          <el-button
            type="success"
            plain
            :loading="triggering"
            @click="triggerNow"
          >
            <el-icon><Promotion /></el-icon>立即运行一次
          </el-button>

          <el-button @click="loadAll">
            <el-icon><Refresh /></el-icon>刷新状态
          </el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- 上次运行 -->
    <div class="page-card" v-if="status.last_run">
      <h3 class="page-title">上次运行</h3>
      <el-descriptions :column="2" border>
        <el-descriptions-item label="开始时间">{{ status.last_run.started_at }}</el-descriptions-item>
        <el-descriptions-item label="结束时间">{{ status.last_run.ended_at }}</el-descriptions-item>
        <el-descriptions-item label="整体状态" :span="2">
          <el-tag :type="status.last_run.success ? 'success' : 'danger'" size="small">
            {{ status.last_run.success ? '成功' : '失败' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="任务详情" :span="2">
          <el-table :data="status.last_run.tasks || []" size="small">
            <el-table-column prop="task" label="任务" width="160" />
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small">
                  {{ row.status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="started_at" label="开始" width="180" />
            <el-table-column prop="ended_at" label="结束" width="180" />
            <el-table-column prop="error" label="错误" />
          </el-table>
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <!-- 运行历史 -->
    <div class="page-card">
      <h3 class="page-title">运行历史 (最近 10 次)</h3>
      <el-table :data="history" stripe>
        <el-table-column prop="started_at" label="开始时间" width="180" />
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.success ? 'success' : 'danger'" size="small">
              {{ row.success ? 'OK' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="任务数" width="100" align="center">
          <template #default="{ row }">{{ row.tasks?.length || 0 }}</template>
        </el-table-column>
        <el-table-column label="耗时">
          <template #default="{ row }">{{ formatDuration(row) }}</template>
        </el-table-column>
        <el-table-column label="开始-结束" width="300">
          <template #default="{ row }">
            <span style="color:#909399; font-size:12px;">
              {{ row.started_at }} → {{ row.ended_at }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { schedulerApi } from '@/api/modules'

const status = ref({
  enabled: false,
  running: false,
  config: { time: '16:30', tasks: [], adjust: 'qfq', days: 365, workers: 8 },
  history_count: 0,
})
const history = ref([])
const operating = ref(false)
const triggering = ref(false)
let timer = null

const form = reactive({
  time: '16:30',
  tasks: ['stock_list', 'index', 'kline_daily'],
  adjust: 'qfq',
  days: 365,
  workers: 8,
})

async function loadAll() {
  try {
    const s = await schedulerApi.status()
    status.value = s
    // 用后端配置同步表单
    if (s.config) {
      Object.assign(form, {
        time: s.config.time,
        tasks: [...(s.config.tasks || [])],
        adjust: s.config.adjust || 'qfq',
        days: s.config.days || 365,
        workers: s.config.workers || 8,
      })
    }
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function loadHistory() {
  try {
    const r = await schedulerApi.history(10)
    history.value = r.items || []
  } catch (e) {
    // ignore
  }
}

async function startScheduler() {
  if (!form.time) return ElMessage.warning('请选择执行时间')
  if (!form.tasks.length) return ElMessage.warning('请至少选择一个任务')
  operating.value = true
  try {
    const r = await schedulerApi.start({ ...form })
    status.value = r
    ElMessage.success(`调度已启动,下次运行: ${r.next_run_at}`)
    loadHistory()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    operating.value = false
  }
}

async function stopScheduler() {
  try {
    await ElMessageBox.confirm('确定停止调度器吗?当前正在执行的任务会继续完成。', '确认', {
      type: 'warning',
    })
  } catch { return }
  operating.value = true
  try {
    const r = await schedulerApi.stop()
    status.value = r
    ElMessage.success('调度已停止')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    operating.value = false
  }
}

async function saveConfig() {
  operating.value = true
  try {
    const r = await schedulerApi.updateConfig({ ...form })
    status.value = r
    ElMessage.success('配置已更新,立即生效')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    operating.value = false
  }
}

async function triggerNow() {
  try {
    await ElMessageBox.confirm(
      '立即按当前配置执行一次所有任务。该操作会持续数分钟到数十分钟,确认执行?',
      '立即运行',
      { type: 'warning' },
    )
  } catch { return }
  triggering.value = true
  try {
    const r = await schedulerApi.trigger()
    ElMessage.success('已触发,可在历史记录查看结果')
    loadAll()
    loadHistory()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    triggering.value = false
  }
}

function formatDuration(record) {
  try {
    const s = new Date(record.started_at)
    const e = new Date(record.ended_at)
    const sec = (e - s) / 1000
    if (sec < 60) return `${sec.toFixed(1)}s`
    const min = Math.floor(sec / 60)
    const rest = (sec % 60).toFixed(0)
    return `${min}m${rest}s`
  } catch {
    return '-'
  }
}

onMounted(() => {
  loadAll()
  loadHistory()
  // 定时刷新状态(每 30 秒)
  timer = setInterval(() => {
    loadAll()
    loadHistory()
  }, 30000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>