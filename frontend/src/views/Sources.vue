<template>
  <div>
    <!-- 状态概览 -->
    <div class="page-card">
      <h3 class="page-title">
        <el-icon><Coin /></el-icon>
        数据源管理
        <span style="margin-left:auto; font-size:12px; color:#909399;">
          当前主源: <el-tag type="success" size="small">{{ primary }}</el-tag>
        </span>
      </h3>

      <div class="toolbar">
        <el-button type="primary" :loading="testingAll" @click="testAll">
          <el-icon><CircleCheck /></el-icon>测试所有源
        </el-button>
        <el-button @click="load" :loading="loading">
          <el-icon><Refresh /></el-icon>刷新
        </el-button>
      </div>

      <el-table :data="sources" stripe v-loading="loading">
        <el-table-column label="数据源" width="140">
          <template #default="{ row }">
            <strong>{{ row.name }}</strong>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.is_primary" type="success" size="small">主源</el-tag>
            <el-tag v-else type="info" size="small">备选</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="需要 Token" width="100">
          <template #default="{ row }">
            <el-icon v-if="row.requires_token" color="#e6a23c"><Lock /></el-icon>
            <el-icon v-else color="#67c23a"><Unlock /></el-icon>
            <span style="margin-left:4px;">{{ row.requires_token ? '是' : '否' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="成功/失败" width="120" align="center">
          <template #default="{ row }">
            <span style="color:#67c23a;">{{ row.success }}</span>
            <span style="color:#c0c4cc;">/</span>
            <span style="color:#f56c6c;">{{ row.failed }}</span>
          </template>
        </el-table-column>
        <el-table-column label="最近错误" min-width="200">
          <template #default="{ row }">
            <span v-if="row.last_error" style="color:#f56c6c; font-size:12px;">
              {{ row.last_error }}
            </span>
            <span v-else style="color:#c0c4cc;">-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button size="small" :loading="testing === row.name" @click="test(row.name)">
              测试
            </el-button>
            <el-button
              v-if="!row.is_primary"
              size="small" type="primary"
              @click="switchTo(row.name)"
            >
              设为主源
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 测试结果 -->
    <div class="page-card" v-if="testResults.length">
      <h3 class="page-title">连通性测试结果</h3>
      <el-table :data="testResults" stripe>
        <el-table-column prop="name" label="数据源" width="140" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.available ? 'success' : 'danger'" size="small">
              {{ row.available ? '可用' : '不可用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="rows" label="返回行数" width="120" align="right" />
        <el-table-column prop="elapsed_ms" label="耗时(ms)" width="120" align="right" />
        <el-table-column label="错误">
          <template #default="{ row }">
            <span v-if="row.error" style="color:#f56c6c; font-size:12px;">
              {{ row.error }}
            </span>
            <span v-else style="color:#67c23a;">{{ row.available ? '连接成功' : '' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 说明 -->
    <div class="page-card">
      <h3 class="page-title"><el-icon><InfoFilled /></el-icon>关于数据源</h3>
      <el-alert type="info" :closable="false" show-icon>
        <template #title>多数据源 + 自动 failover</template>
        <div style="line-height:1.8;">
          • <strong>AKShare</strong>: 默认主源,免注册,聚合多源(东方财富/新浪等)。无需 token,开箱即用。<br>
          • <strong>Baostock</strong>: 免费备选,专注 A 股日 K,数据准确度较高。在 AKShare 限流时自动接替。<br>
          • <strong>Tushare</strong>: 数据质量最高,但需注册获取 token。设置环境变量
          <code>TUSHARE_TOKEN=xxx</code> 后重启服务即可启用。<br>
          • 当主源调用失败时,系统会自动按顺序尝试其他数据源,无需手动切换。
        </div>
      </el-alert>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { sourcesApi } from '@/api/modules'

const sources = ref([])
const primary = ref('akshare')
const testResults = ref([])
const loading = ref(false)
const testingAll = ref(false)
const testing = ref('')

async function load() {
  loading.value = true
  try {
    const r = await sourcesApi.list()
    primary.value = r.primary
    sources.value = r.sources
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function test(name) {
  testing.value = name
  try {
    const r = await sourcesApi.test(name)
    ElMessage[ r.available ? 'success' : 'error' ](
      `${name}: ${r.available ? `可用 (${r.rows} 行, ${r.elapsed_ms}ms)` : '不可用 - ' + r.error}`
    )
    // 更新测试结果
    const existing = testResults.value.findIndex(x => x.name === name)
    if (existing >= 0) testResults.value[existing] = r
    else testResults.value.push(r)
    await load()  // 刷新统计
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    testing.value = ''
  }
}

async function testAll() {
  testingAll.value = true
  try {
    const r = await sourcesApi.testAll()
    testResults.value = r.results
    const ok = r.results.filter(x => x.available).length
    ElMessage.success(`测试完成: ${ok}/${r.results.length} 可用`)
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    testingAll.value = false
  }
}

async function switchTo(name) {
  try {
    await ElMessageBox.confirm(`确定将 "${name}" 设为默认数据源?`, '切换主源', {
      type: 'info',
    })
  } catch { return }
  try {
    const r = await sourcesApi.switch(name)
    primary.value = r.primary
    ElMessage.success(r.message)
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(load)
</script>