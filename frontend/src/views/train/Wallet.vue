<template>
  <div class="wallet">
    <div class="page-card">
      <el-row :gutter="16">
        <el-col :span="8">
          <div class="big balance">
            <div class="lbl">训练资金余额</div>
            <div class="val">¥ {{ money(data.balance) }}</div>
            <div class="indicator"></div>
          </div>
        </el-col>
        <el-col :span="8">
          <div class="big muted">
            <div class="lbl">累计充值</div>
            <div class="val">¥ {{ money(data.total_topup) }}</div>
          </div>
        </el-col>
        <el-col :span="8">
          <div class="big muted">
            <div class="lbl">累计消耗 (训练费)</div>
            <div class="val">¥ {{ money(data.total_spent) }}</div>
          </div>
        </el-col>
      </el-row>

      <el-alert type="info" :closable="false" show-icon style="margin-top: 12px;">
        每次发起训练会按初始资金的 1% (5 ~ 50 元封顶) 从余额扣除。
        <span v-if="data.balance < 50" style="color: #f56c6c;">
          余额偏低,建议尽快充值!
        </span>
        <span v-else>用完了? 在下面输入兑换码即可充值。</span>
      </el-alert>
    </div>

    <div class="page-card" style="margin-top: 16px;">
      <h3 class="page-title">兑换码充值</h3>
      <el-form :inline="true" @submit.prevent="redeem">
        <el-form-item label="兑换码">
          <el-input v-model="code" placeholder="如 ABCD1234-00100000" style="width: 360px;"
                    @keyup.enter="redeem" clearable size="large" />
        </el-form-item>
        <el-button type="primary" :loading="loading" size="large" @click="redeem">
          <el-icon><Present /></el-icon>立刻兑换
        </el-button>
      </el-form>

      <el-divider>充值记录</el-divider>
      <el-empty v-if="!history.length" description="还没有充值记录" :image-size="80" />
      <el-table v-else :data="history" stripe size="small" :max-height="280">
        <el-table-column prop="time" label="时间" width="180" />
        <el-table-column prop="amount" label="金额" align="right" width="120">
          <template #default="{ row }">
            <span style="color: #67c23a; font-weight: bold;">+ ¥ {{ money(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="code" label="兑换码" />
      </el-table>
    </div>

    <div class="page-card" style="margin-top: 16px;">
      <h3 class="page-title">怎么获取兑换码?</h3>
      <p>
        请联系系统管理员 (admin) 生成兑换码,然后把码发给你。
        也可以登录管理后台,在 <b>"兑换码管理"</b> 页面生成。
      </p>
      <p style="margin-bottom: 0;">
        自己也是管理员?
        <el-link type="primary" @click="$router.push('/train/redeem-admin')">点这里生成兑换码</el-link>
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, inject } from 'vue'
import { ElMessage } from 'element-plus'
import { trainApi } from '@/api/modules'

const layoutRef = inject('trainLayout', null)
const data = reactive({ balance: 0, total_topup: 0, total_spent: 0 })
const code = ref('')
const loading = ref(false)
const history = ref([])

function money(v) {
  return Number(v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function load() {
  try {
    const w = await trainApi.wallet()
    Object.assign(data, w || {})
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function redeem() {
  if (!code.value.trim()) return ElMessage.warning('请输入兑换码')
  loading.value = true
  try {
    const res = await trainApi.redeem(code.value.trim().toUpperCase())
    ElMessage.success(`兑换成功,获得 ¥ ${money(res.amount)}`)
    history.value.unshift({
      time: new Date().toLocaleString('zh-CN'),
      amount: res.amount,
      code: code.value.trim().toUpperCase(),
    })
    code.value = ''
    await load()
    if (layoutRef?.refreshWallet) layoutRef.refreshWallet()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.big { padding: 20px; border-radius: 6px; }
.balance { background: linear-gradient(135deg, #1f3b66, #0f1d33); color: #fff;
           position: relative; overflow: hidden; }
.balance::before {
  content: ''; position: absolute; right: -40px; top: -40px;
  width: 160px; height: 160px; border-radius: 50%;
  background: rgba(64, 158, 255, 0.15);
}
.balance .lbl, .balance .lbl-hint { color: #b4bcd0; }
.balance .val { color: #67c23a; font-size: 32px; margin-top: 8px; }
.muted { background: #f6f8fb; }
.muted .lbl { color: #909399; font-size: 12px; }
.muted .val { color: #303133; font-size: 28px; font-weight: bold; margin-top: 6px; }
.page-card { background: #fff; padding: 18px 22px; border-radius: 6px;
             box-shadow: 0 1px 4px rgba(0,0,0,.06); }
.page-card h3 { margin-top: 0; }
</style>
