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
      <el-link href="#/dashboard" type="info">前往管理后台</el-link>
      <span style="margin: 0 12px;">·</span>
      <el-link href="#/login" type="info">管理员登录</el-link>
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
  if (form.password.length < 6) return ElMessage.warning('密码长度至少 6 位')
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
  background: linear-gradient(135deg, #0f1622 0%, #1a2b46 100%);
}
.login-card {
  display: flex; width: 880px; max-width: 92vw;
  border-radius: 14px; overflow: hidden;
  box-shadow: 0 24px 48px rgba(0,0,0,.4);
}
.left {
  flex: 1; padding: 48px 36px;
  background: linear-gradient(160deg, #1f3b66, #0f1d33);
  color: #f3f3f3;
}
.left h1 { margin: 0 0 8px; font-size: 28px; }
.left .sub { color: #b4bcd0; margin: 0 0 36px; }
.features { padding-left: 20px; line-height: 1.9; color: #d8dde6; }
.right {
  width: 420px; padding: 36px 32px;
  background: #fff;
}
.btn { width: 100%; }
.tip { font-size: 12px; color: #909399; margin-top: 12px; text-align: center; }
.footer { color: #b4bcd0; margin-top: 22px; font-size: 13px; }
</style>
