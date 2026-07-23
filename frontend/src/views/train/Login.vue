<template>
  <div class="train-login-bg">
    <div class="login-card">
      <div class="left">
        <h1>K线交易训练</h1>
        <p class="sub">真实历史数据 · 模拟资金 · 训练你的盘感</p>
        <ul class="features">
          <li>📈 随机抽取真实股票 + 历史 K 线</li>
          <li>💰 真实手续费 / 印花税 / 分仓规则</li>
          <li>🎯 从历史日 K / 周 K / 月 K 多维度复盘</li>
          <li>🔑 兑换码充值,可消耗的训练资金</li>
        </ul>
      </div>
      <div class="right">
        <el-tabs v-model="mode" stretch>
          <el-tab-pane label="登录" name="login" />
          <el-tab-pane label="注册" name="register" />
        </el-tabs>

        <el-form v-if="mode === 'login'" :model="form" @submit.prevent="onLogin" label-position="top">
          <el-form-item label="账号">
            <el-input v-model="form.username" size="large" clearable autofocus>
              <template #prefix><el-icon><User /></el-icon></template>
            </el-input>
          </el-form-item>
          <el-form-item label="密码">
            <el-input v-model="form.password" type="password" size="large" show-password
                      @keyup.enter="onLogin">
              <template #prefix><el-icon><Lock /></el-icon></template>
            </el-input>
          </el-form-item>
          <el-button type="primary" size="large" class="btn" :loading="loading" @click="onLogin">
            登 录
          </el-button>
          <div class="tip">
            没有账号? 切换到"注册"标签
          </div>
        </el-form>

        <el-form v-else :model="form" @submit.prevent="onRegister" label-position="top">
          <el-form-item label="账号 (3-32 位)">
            <el-input v-model="form.username" size="large" clearable>
              <template #prefix><el-icon><User /></el-icon></template>
            </el-input>
          </el-form-item>
          <el-form-item label="昵称 (可选)">
            <el-input v-model="form.display_name" size="large" />
          </el-form-item>
          <el-form-item label="密码 (≥ 6 位)">
            <el-input v-model="form.password" type="password" size="large" show-password
                      @keyup.enter="onRegister">
              <template #prefix><el-icon><Lock /></el-icon></template>
            </el-input>
          </el-form-item>
          <el-button type="success" size="large" class="btn" :loading="loading" @click="onRegister">
            注 册
          </el-button>
          <div class="tip">
            注册后,可前往 "钱包 / 兑换" 页面用兑换码充值
          </div>
        </el-form>
      </div>
    </div>

    <div class="footer">
      用户训练端 · 仅供训练使用
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { trainApi } from '@/api/modules'
import { useTrainAuthStore } from '@/stores/trainAuth'

const router = useRouter()
const route = useRoute()
const auth = useTrainAuthStore()
const mode = ref('login')
const loading = ref(false)
const form = reactive({ username: '', password: '', display_name: '' })

async function onLogin() {
  if (!form.username || !form.password) {
    return ElMessage.warning('请输入账号和密码')
  }
  loading.value = true
  try {
    const data = await trainApi.login(form.username.trim(), form.password)
    const payload = data?.data ?? data
    if (!payload?.access_token) throw new Error('登录响应缺少 token')
    auth.setAuth(payload.access_token, {
      id: payload.user_id,
      username: payload.username,
      display_name: payload.display_name,
    })
    ElMessage.success(`欢迎回来,${payload.display_name || payload.username}`)
    const redirect = route.query.redirect || '/train/home'
    router.replace(redirect)
  } catch (e) {
    ElMessage.error(e.message || '登录失败')
  } finally {
    loading.value = false
  }
}

async function onRegister() {
  if (form.username.length < 3 || form.username.length > 32) {
    return ElMessage.warning('账号长度需 3-32 位')
  }
  if (form.password.length < 8) return ElMessage.warning('密码长度至少 8 位')
  if (!/[a-zA-Z]/.test(form.password) || !/\d/.test(form.password)) {
    return ElMessage.warning('密码必须包含字母和数字')
  }
  loading.value = true
  try {
    await trainApi.register(form.username.trim(), form.password, form.display_name || '')
    ElMessage.success('注册成功,请登录')
    mode.value = 'login'
    form.password = ''
  } catch (e) {
    ElMessage.error(e.message || '注册失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.train-login-bg {
  min-height: 100vh;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  background: var(--bg-page);
}
.train-login-bg::before {
  content: '';
  position: fixed;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: linear-gradient(90deg, var(--color-primary) 0%, var(--color-info) 100%);
  z-index: var(--z-sticky);
}
.login-card {
  display: flex; width: 880px; max-width: 92vw;
  border-radius: var(--radius-xl); overflow: hidden;
  box-shadow: var(--shadow-xl);
  border: 1px solid var(--border-color-light);
}
.left {
  flex: 1; padding: var(--space-5xl) var(--space-3xl);
  background: linear-gradient(160deg, #1e3a5f, #0f2342);
  color: #f1f5f9;
}
.left h1 {
  margin: 0 0 var(--space-sm);
  font-size: var(--text-4xl);
  font-weight: var(--font-bold);
  letter-spacing: -0.02em;
}
.left .sub {
  color: #94a3b8;
  font-size: var(--text-base);
  margin: 0 0 var(--space-4xl);
}
.features {
  padding: 0;
  list-style: none;
  display: flex; flex-direction: column; gap: var(--space-lg);
}
.features li {
  display: flex; align-items: center; gap: var(--space-sm);
  color: #cbd5e1;
  font-size: var(--text-sm);
  line-height: 1.6;
}
.right {
  width: 420px; padding: var(--space-4xl) var(--space-2xl);
  background: var(--bg-card);
}
.btn { width: 100%; }
.tip { font-size: var(--text-xs); color: var(--text-placeholder); margin-top: var(--space-md); text-align: center; }
.footer {
  color: var(--text-placeholder); margin-top: var(--space-2xl);
  font-size: var(--text-sm);
  display: flex; align-items: center;
}
</style>
