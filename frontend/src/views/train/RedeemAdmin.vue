<template>
  <div class="redeem-admin">
    <el-alert type="warning" :closable="false" show-icon style="margin-bottom: 16px;">
      <template #title>需要管理后台 admin token</template>
      此页面通过 <code>/api/train/admin/...</code> 生成兑换码,要求请求里带 admin 账号的 JWT。
      如果你直接访问训练端,需要先在另一个标签登录 admin 后再回来刷新本页。
      <span v-if="adminInfo">已验证身份: {{ adminInfo.viewer }}</span>
    </el-alert>

    <div class="page-card">
      <h3 class="page-title">兑换码生成 (管理员)</h3>
      <el-form :inline="true" @submit.prevent="generate">
        <el-form-item label="每张金额(元)">
          <el-input-number v-model="form.amount" :min="1000" :step="1000" />
        </el-form-item>
        <el-form-item label="生成数量">
          <el-input-number v-model="form.count" :min="1" :max="200" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.note" placeholder="可选,如 '2026Q1推广'" style="width: 220px;" clearable />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="generating" @click="generate">
            <el-icon><Plus /></el-icon>生成兑换码
          </el-button>
          <el-button @click="refreshList">
            <el-icon><Refresh /></el-icon>刷新
          </el-button>
        </el-form-item>
      </el-form>

      <el-collapse v-model="showNew" v-if="newCodes.length">
        <el-collapse-item title="本次生成的兑换码 (可一键复制)" name="1">
          <div class="codes">
            <div v-for="(c, i) in newCodes" :key="i" class="code-row">
              <span class="code">{{ c }}</span>
              <el-button size="small" @click="copy(c)">复制</el-button>
            </div>
          </div>
          <el-button type="success" size="small" @click="copyAll">
            <el-icon><CopyDocument /></el-icon>复制全部 ({{ newCodes.length }} 张)
          </el-button>
        </el-collapse-item>
      </el-collapse>
    </div>

    <div class="page-card" style="margin-top: 16px;">
      <div class="head-row">
        <h3 class="page-title">历史兑换码</h3>
        <el-input v-model="filterText" placeholder="搜兑换码/使用者/备注" style="width: 280px;" clearable size="default" />
      </div>
      <el-table :data="filteredList" stripe v-loading="loading" max-height="500">
        <el-table-column prop="code" label="兑换码" min-width="200" />
        <el-table-column prop="amount" label="金额(元)" align="right" width="100">
          <template #default="{ row }">¥ {{ money(row.amount) }}</template>
        </el-table-column>
        <el-table-column prop="is_used" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_used ? 'info' : 'success'" size="small">
              {{ row.is_used ? '已使用' : '未使用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="used_by" label="使用者" width="100">
          <template #default="{ row }">
            <span v-if="row.used_by">uid {{ row.used_by }}</span>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="used_at" label="使用时间" width="180">
          <template #default="{ row }">
            <span v-if="row.used_at">{{ row.used_at }}</span>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="生成时间" width="180" />
        <el-table-column prop="note" label="备注">
          <template #default="{ row }">
            <span v-if="row.note">{{ row.note }}</span>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && !filteredList.length" description="没有兑换码记录" :image-size="80" />
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { trainApi } from '@/api/modules'

const form = reactive({ amount: 10000, count: 5, note: '' })
const generating = ref(false)
const loading = ref(false)
const newCodes = ref([])
const showNew = ref([])
const list = ref([])
const filterText = ref('')
const adminInfo = ref(null)

const filteredList = computed(() => {
  const t = (filterText.value || '').trim().toLowerCase()
  if (!t) return list.value
  return list.value.filter((x) =>
    (x.code || '').toLowerCase().includes(t)
    || String(x.used_by || '').includes(t)
    || (x.note || '').toLowerCase().includes(t)
  )
})

function money(v) {
  return Number(v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function generate() {
  generating.value = true
  try {
    const res = await trainApi.createRedeemCodes(form.amount, form.count, form.note)
    newCodes.value = res.codes || []
    showNew.value = ['1']
    ElMessage.success(`已生成 ${newCodes.value.length} 张兑换码 (¥ ${money(res.amount)}/张)`)
    await refreshList()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    generating.value = false
  }
}

async function refreshList() {
  loading.value = true
  try {
    const res = await trainApi.redeemCodes()
    list.value = res?.items || []
    adminInfo.value = res?.viewer ? { viewer: res.viewer } : null
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制')
  } catch {
    ElMessage.warning('复制失败,请手动选中')
  }
}

function copyAll() {
  copy(newCodes.value.join('\n'))
}

onMounted(refreshList)
</script>

<style scoped>
.head-row {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px;
}
.head-row .page-title { margin: 0; }
.page-card { background: #fff; padding: 18px 22px; border-radius: 6px;
             box-shadow: 0 1px 4px rgba(0,0,0,.06); }
.page-card h3 { margin-top: 0; }
.codes { background: #fafbfc; padding: 12px; border-radius: 4px;
         font-family: Consolas, monospace; max-height: 200px; overflow: auto; margin-bottom: 8px;
         border: 1px solid #ebeef5; }
.code-row { display: flex; justify-content: space-between; align-items: center;
            padding: 4px 0; border-bottom: 1px dashed #e6ebf2; }
.code-row:last-child { border-bottom: none; }
.code { font-size: 13px; color: #1f3b66; font-weight: bold; }
.muted { color: #c0c4cc; }
code { background: #fff5e6; padding: 2px 6px; border-radius: 3px; font-family: Consolas, monospace; }
</style>
