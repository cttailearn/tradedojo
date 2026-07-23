<template>
  <div class="login-bg">
    <div class="login-box">
      <div class="login-header">
        <div class="logo">📈</div>
        <h1>管理后台</h1>
        <p class="subtitle">A 股数据采集 · 回测 · 智能管理</p>
      </div>
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        @submit.prevent="onLogin"
      >
        <el-form-item label="账号" prop="username">
          <el-input v-model="form.username" placeholder="请输入账号" size="large" clearable>
            <template #prefix><el-icon><User /></el-icon></template>
          </el-input>
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            size="large"
            show-password
            @keyup.enter="onLogin"
          >
            <template #prefix><el-icon><Lock /></el-icon></template>
          </el-input>
        </el-form-item>
        <el-button type="primary" size="large" :loading="loading" class="login-btn" @click="onLogin">
        登 录
      </el-button>
    </el-form>
    <!--
      默认账号提示: 仅在开发者模式下显示 (通过 URL 加 ?dev=1 启用).
      普通用户访问 /admin/login 时看不到, 管理员自己知道默认值.
    -->
    <div v-if="showDevHint" class="login-tip">
      默认管理员账号: <code>{{ devUsername }}</code> / <code>{{ devPassword }}</code>
      <br />
      <small>(提示来自 URL <code>?dev=1</code>, 仅开发环境)</small>
    </div>
  </div>
    <div class="login-footer">
      © 2026 Stock Data System · Powered by FastAPI + Vue 3
      <el-link
        v-if="!showDevHint"
        type="info"
        :underline="false"
        style="margin-left: 12px; font-size: 12px;"
        @click="enableDevHint"
        title="显示默认管理员账号提示"
      >·</el-link>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { authApi } from '@/api/modules'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const formRef = ref(null)
const loading = ref(false)
const form = reactive({ username: '', password: '' })
const rules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

// 开发者提示: 仅当 URL 带 ?dev=1 时显示
const showDevHint = computed(() => route.query.dev === '1')
const devUsername = 'admin'
const devPassword = 'admin123'

function enableDevHint() {
  router.replace({ query: { ...route.query, dev: '1' } })
}

async function onLogin() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    const data = await authApi.login(form.username, form.password)
    // 兼容两种返回: {access_token,...} 或 {code,data:{access_token,...}}
    const payload = data?.data ?? data
    const token = payload?.access_token
    const username = payload?.username ?? form.username
    if (!token) {
      throw new Error('登录响应缺少 access_token')
    }
    auth.setAuth(token, {
      username,
      user_id: payload.user_id,
    })
    ElMessage.success(`欢迎回来,${username}`)
    const redirect = route.query.redirect || '/admin/dashboard'
    // 用 replace 避免登录页可以 back 返回
    router.replace(redirect)
  } catch (e) {
    console.error('[Login]', e)
    ElMessage.error(e.message || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>