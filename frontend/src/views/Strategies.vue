<template>
  <div>
    <div class="page-header">
      <h2>策略编辑器</h2>
      <div class="actions">
        <el-button @click="importDialog = true" text>
          <el-icon><Download /></el-icon>导入策略
        </el-button>
        <el-button type="primary" @click="openCreate">
          <el-icon><Plus /></el-icon>新建策略
        </el-button>
      </div>
    </div>

    <!-- 策略列表 -->
    <div class="page-card" v-if="!editing">
      <!-- 内置策略 -->
      <h3 class="page-title">内置策略</h3>
      <div class="strategy-grid">
        <div
          v-for="s in builtinStrategies" :key="s.id"
          class="strategy-card"
          :class="{ 'is-builtin': s.builtin }"
        >
          <div class="s-header">
            <span class="s-name">{{ s.name }}</span>
            <el-tag size="small" type="info">内置</el-tag>
          </div>
          <p class="s-desc">{{ s.description }}</p>
          <div class="s-params" v-if="s.params.length">
            <el-tag
              v-for="p in s.params" :key="p.key"
              size="small" type="info" effect="plain"
              class="param-tag"
            >
              {{ p.label }}: {{ p.default }}
            </el-tag>
          </div>
          <div class="s-actions">
            <el-button size="small" type="primary" plain @click="useStrategy(s)">
              <el-icon><VideoPlay /></el-icon>使用回测
            </el-button>
            <el-button size="small" @click="exportStrategy(s)">
              <el-icon><Share /></el-icon>分享
            </el-button>
          </div>
        </div>
      </div>

      <!-- 自定义策略 -->
      <h3 class="page-title" style="margin-top: 28px;">我的策略</h3>
      <div v-if="customStrategies.length === 0" class="empty-state">
        <div class="icon">📝</div>
        <div class="title">还没有自定义策略</div>
        <div class="desc">创建一个策略，或从内置策略另存为自定义策略进行编辑</div>
        <el-button type="primary" @click="openCreate">新建策略</el-button>
      </div>
      <div v-else class="strategy-grid">
        <div
          v-for="s in customStrategies" :key="s.id"
          class="strategy-card"
        >
          <div class="s-header">
            <span class="s-name">{{ s.name }}</span>
            <span class="s-date">{{ s.updatedAt }}</span>
          </div>
          <p class="s-desc">{{ s.description || '无描述' }}</p>
          <div class="s-params" v-if="s.params.length">
            <el-tag
              v-for="p in s.params" :key="p.key"
              size="small" effect="plain"
              class="param-tag"
            >
              {{ p.label }}: {{ p.default }}
            </el-tag>
          </div>
          <div class="s-actions">
            <el-button size="small" type="primary" plain @click="useStrategy(s)">
              <el-icon><VideoPlay /></el-icon>回测
            </el-button>
            <el-button size="small" @click="editStrategy(s)">
              <el-icon><Edit /></el-icon>编辑
            </el-button>
            <el-button size="small" @click="exportStrategy(s)">
              <el-icon><Share /></el-icon>分享
            </el-button>
            <el-button size="small" type="danger" text @click="deleteStrategy(s)">
              <el-icon><Delete /></el-icon>
            </el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- 编辑器 -->
    <div class="page-card" v-else>
      <div class="page-header" style="margin-bottom: 20px;">
        <h2>{{ isCreate ? '新建策略' : '编辑策略' }}</h2>
        <el-button @click="cancelEdit">返回列表</el-button>
      </div>

      <el-form :model="editForm" label-width="100px">
        <el-row :gutter="16">
          <el-col :span="16">
            <el-form-item label="策略名称">
              <el-input v-model="editForm.name" placeholder="输入策略名称" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="类型">
              <el-select v-model="editForm.type">
                <el-option label="SMA 双均线" value="sma" />
                <el-option label="动量策略" value="momentum" />
                <el-option label="买入持有" value="buy_hold" />
                <el-option label="均线多头排列" value="ma_alignment" />
                <el-option label="自定义" value="custom" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="策略描述">
          <el-input v-model="editForm.description" type="textarea" :rows="2" placeholder="描述策略思路和适用场景" />
        </el-form-item>

        <el-form-item label="参数配置">
          <div class="params-editor">
            <div
              v-for="(p, idx) in editForm.params" :key="idx"
              class="param-row"
            >
              <el-input v-model="p.key" placeholder="参数名" style="width:120px;" />
              <el-input v-model="p.label" placeholder="显示名" style="width:120px;" />
              <el-select v-model="p.type" style="width:100px;">
                <el-option label="数字" value="number" />
                <el-option label="选择" value="select" />
                <el-option label="开关" value="boolean" />
              </el-select>
              <el-input-number
                v-if="p.type === 'number'"
                v-model="p.default" :min="p.min || 0" :max="p.max || 999"
                :step="p.step || 1" controls-position="right"
                style="width:140px;"
              />
              <el-switch v-else-if="p.type === 'boolean'" v-model="p.default" style="width:60px;" />
              <template v-if="p.type === 'number'">
                <el-input-number v-model="p.min" placeholder="最小" size="small" style="width:90px;" />
                <el-input-number v-model="p.max" placeholder="最大" size="small" style="width:90px;" />
                <el-input-number v-model="p.step" placeholder="步长" size="small" :min="0.01" :step="0.01" :precision="2" style="width:90px;" />
              </template>
              <el-button type="danger" :icon="Delete" circle size="small" text @click="removeParam(idx)" />
            </div>
            <el-button size="small" @click="addParam">
              <el-icon><Plus /></el-icon>添加参数
            </el-button>
          </div>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="saveStrategy">
            <el-icon><Check /></el-icon>保存策略
          </el-button>
          <el-button @click="cancelEdit">取消</el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- 导入对话框 -->
    <el-dialog v-model="importDialog" title="导入策略" width="480px">
      <el-form-item label="分享码">
        <el-input
          v-model="importCode" placeholder="粘贴 TDJ: 开头的分享码"
          type="textarea" :rows="3"
        />
      </el-form-item>
      <div v-if="importPreview" class="import-preview">
        <div class="page-card" style="margin-top:12px;">
          <div class="s-header">
            <span class="s-name">{{ importPreview.name }}</span>
          </div>
          <p class="s-desc">{{ importPreview.description }}</p>
          <div class="s-params" v-if="importPreview.params.length">
            <el-tag v-for="p in importPreview.params" :key="p.key" size="small" effect="plain" class="param-tag">
              {{ p.label }}: {{ p.default }}
            </el-tag>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="importDialog = false">取消</el-button>
        <el-button type="primary" @click="confirmImport" :disabled="!importPreview">
          确认导入
        </el-button>
      </template>
    </el-dialog>

    <!-- 分享对话框 -->
    <el-dialog v-model="shareDialog" title="分享策略" width="480px">
      <p style="color: var(--text-secondary); font-size: var(--text-sm);">
        将以下分享码发送给其他人，他们可以导入此策略：
      </p>
      <el-input
        :model-value="shareCode" readonly
        type="textarea" :rows="3"
        style="font-family: var(--font-mono); font-size: 12px;"
      />
      <template #footer>
        <el-button type="primary" @click="copyShareCode">复制分享码</el-button>
        <el-button @click="shareDialog = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  BUILTIN_STRATEGIES, loadStrategies, saveStrategies,
  generateId, encodeShareCode, decodeShareCode,
} from '@/utils/strategy'

const router = useRouter()

// 策略列表
const builtinStrategies = BUILTIN_STRATEGIES
const customStrategies = ref([])

// 编辑器状态
const editing = ref(false)
const isCreate = ref(false)
const editForm = reactive({
  id: '',
  name: '',
  description: '',
  type: 'sma',
  params: [],
})

// 导入/导出
const importDialog = ref(false)
const importCode = ref('')
const importPreview = ref(null)
const shareDialog = ref(false)
const shareCode = ref('')

// 监听导入码变化
watch(importCode, (val) => {
  importPreview.value = decodeShareCode(val)
})

// 刷新自定义策略列表
function refreshCustom() {
  customStrategies.value = loadStrategies()
}

// 新建策略
function openCreate() {
  isCreate.value = true
  editForm.id = generateId()
  editForm.name = ''
  editForm.description = ''
  editForm.type = 'sma'
  editForm.params = []
  editing.value = true
}

// 编辑策略
function editStrategy(s) {
  isCreate.value = false
  editForm.id = s.id
  editForm.name = s.name
  editForm.description = s.description || ''
  editForm.type = s.type
  editForm.params = JSON.parse(JSON.stringify(s.params || []))
  editing.value = true
}

// 取消编辑
function cancelEdit() {
  editing.value = false
}

// 添加参数
function addParam() {
  editForm.params.push({
    key: '',
    label: '',
    type: 'number',
    default: 0,
    min: 0,
    max: 100,
    step: 1,
  })
}

// 移除参数
function removeParam(idx) {
  editForm.params.splice(idx, 1)
}

// 保存策略
function saveStrategy() {
  if (!editForm.name.trim()) {
    return ElMessage.warning('请输入策略名称')
  }
  const strategies = loadStrategies()
  const now = new Date().toISOString().slice(0, 10)

  // 清理参数（过滤空 key）
  const cleanParams = (editForm.params || []).filter(p => p.key.trim())

  const entry = {
    id: editForm.id,
    name: editForm.name.trim(),
    description: editForm.description.trim(),
    type: editForm.type,
    builtin: false,
    params: cleanParams.map(p => ({
      key: p.key.trim(),
      label: p.label || p.key,
      type: p.type || 'number',
      default: p.default ?? 0,
      min: p.min ?? 0,
      max: p.max ?? 100,
      step: p.step ?? 1,
    })),
    createdAt: isCreate.value ? now : (strategies.find(s => s.id === editForm.id)?.createdAt || now),
    updatedAt: now,
  }

  if (isCreate.value) {
    strategies.push(entry)
  } else {
    const idx = strategies.findIndex(s => s.id === editForm.id)
    if (idx >= 0) strategies[idx] = entry
  }

  saveStrategies(strategies)
  refreshCustom()
  editing.value = false
  ElMessage.success(isCreate.value ? '策略已创建' : '策略已更新')
}

// 删除策略
async function deleteStrategy(s) {
  try {
    await ElMessageBox.confirm(`确定删除策略「${s.name}」吗？`, '确认删除', { type: 'warning' })
  } catch {
    return
  }
  const strategies = loadStrategies().filter(x => x.id !== s.id)
  saveStrategies(strategies)
  refreshCustom()
  ElMessage.success('已删除')
}

// 使用策略回测
function useStrategy(s) {
  router.push({ path: '/admin/backtest', query: { strategy: s.id } })
}

// 导出分享码
function exportStrategy(s) {
  shareCode.value = encodeShareCode(s)
  shareDialog.value = true
}

// 复制分享码
async function copyShareCode() {
  try {
    await navigator.clipboard.writeText(shareCode.value)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.info(shareCode.value)
  }
  shareDialog.value = false
}

// 确认导入
function confirmImport() {
  if (!importPreview.value) return
  const strategies = loadStrategies()
  strategies.push(importPreview.value)
  saveStrategies(strategies)
  refreshCustom()
  importDialog.value = false
  importCode.value = ''
  ElMessage.success(`已导入策略「${importPreview.value.name}」`)
}

onMounted(refreshCustom)
</script>

<style scoped>
.strategy-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: var(--space-lg);
}
.strategy-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color-light);
  border-radius: var(--radius-lg);
  padding: var(--space-xl);
  transition: all var(--transition-fast);
  display: flex; flex-direction: column;
  gap: var(--space-md);
}
.strategy-card:hover {
  border-color: var(--color-primary-lighter);
  box-shadow: var(--shadow-sm);
}
.strategy-card.is-builtin {
  background: var(--bg-muted);
}
.s-header {
  display: flex; align-items: center; justify-content: space-between;
  gap: var(--space-sm);
}
.s-name {
  font-size: var(--text-lg); font-weight: var(--font-semibold);
  color: var(--text-primary);
}
.s-date {
  font-size: var(--text-xs); color: var(--text-placeholder);
}
.s-desc {
  margin: 0; color: var(--text-secondary); font-size: var(--text-sm);
  line-height: var(--leading-relaxed);
}
.s-params {
  display: flex; flex-wrap: wrap; gap: var(--space-xs);
}
.param-tag {
  font-family: var(--font-mono); font-size: var(--text-xs);
}
.s-actions {
  display: flex; gap: var(--space-sm); margin-top: auto; padding-top: var(--space-sm);
  border-top: 1px solid var(--border-color-light);
}

.params-editor {
  display: flex; flex-direction: column; gap: var(--space-sm);
  width: 100%;
}
.param-row {
  display: flex; align-items: center; gap: var(--space-xs);
  flex-wrap: wrap;
}
.import-preview .page-card {
  padding: var(--space-lg);
  margin-bottom: 0;
}
</style>
