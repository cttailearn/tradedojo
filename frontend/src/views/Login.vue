<template>
  <div class="login-bg">
    <div class="login-box">
      <div class="login-header">
        <div class="logo">📈</div>
        <h1>股票数据库管理系统</h1>
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
      <div class="login-tip">
        默认账号:<code>admin</code> / <code>admin123</code>
      </div>
    </div>
    <div class="login-footer">© 2026 Stock Data System · Powered by FastAPI + Vue 3</div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { authApi } from '@/api/modules'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const formRef = ref(null)
const loading = ref(false)
const form = reactive({ username: 'admin', password: 'admin123' })
const rules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
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
    const redirect = route.query.redirect || '/dashboard'
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