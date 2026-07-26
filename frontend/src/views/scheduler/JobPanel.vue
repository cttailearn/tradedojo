<template>
  <el-form :model="local" label-width="110px" style="max-width:760px;">
    <el-form-item label="启用">
      <el-switch v-model="local.enabled" />
    </el-form-item>

    <el-form-item label="Cron 表达式">
      <el-input
        v-model="local.cron"
        placeholder="例如 30 16 * * 1-5  (分 时 日 月 周)"
        style="width:280px;"
      />
      <span style="margin-left:12px;color:#909399;font-size:12px;">
        上次运行: {{ job?.last_run_at || '-' }}
        <span v-if="job?.last_status"> · 状态: {{ job.last_status }}</span>
      </span>
    </el-form-item>

    <!-- 各类型专属参数(插槽由父组件填充) -->
    <slot name="params" />

    <el-form-item>
      <el-button
        type="primary"
        :loading="saving"
        @click="$emit('save', local)"
      >
        <el-icon><DocumentChecked /></el-icon>保存 (热生效)
      </el-button>
      <el-button
        type="success"
        plain
        :loading="triggering"
        style="margin-left:8px;"
        @click="$emit('trigger')"
      >
        <el-icon><Promotion /></el-icon>立即触发
      </el-button>
      <span style="margin-left:12px;color:#909399;font-size:12px;">
        参数会合并到该任务的 cron 调度里
      </span>
    </el-form-item>
  </el-form>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  job: { type: Object, required: true },
  saving: { type: Boolean, default: false },
  triggering: { type: Boolean, default: false },
})
defineEmits(['save', 'trigger'])

// 本地编辑态(从 props.job 同步)
const local = ref({
  cron: props.job?.cron || '0 0 * * *',
  enabled: props.job?.enabled !== false,
  params: props.job?.params || {},
})

watch(() => props.job, (j) => {
  if (j) {
    local.value = {
      cron: j.cron || '0 0 * * *',
      enabled: j.enabled !== false,
      params: j.params || {},
    }
  }
}, { deep: true })
</script>