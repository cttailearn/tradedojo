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
      默认管理员账号: <code>{{ devUsername }}</code>
      <br />
      <small>密码请查看后端 <code>logs/DEV_ADMIN_PASSWORD.txt</code>(dev 模式自动生成,生产请显式设置 <code>STOCK_ADMIN_PASSWORD</code>)</small>
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

// 开发者提示: 仅在 dev 构建(Vite import.meta.env.DEV)且 URL 带 ?dev=1 时显示
// 生产构建时整段 tree-shake 掉
const isDevBuild = import.meta.env.DEV
const showDevHint = computed(() => isDevBuild && route.query.dev === '1')
// 注: dev 密码现在由后端写到 logs/DEV_ADMIN_PASSWORD.txt(强随机),前端不再硬编码
const devUsername = 'admin'

function enableDevHint() {
  if (!isDevBuild) return
  router.replace({ query: { ...route.query, dev: '1' } })
}

async function onLogin() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    const data = await authApi.login(form.username, form.password)
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
    if (payload?.must_change_pw) {
      ElMessage.warning('首次登录请修改默认密码')
    } else {
      ElMessage.success(`欢迎回来,${username}`)
    }
    const redirect = route.query.redirect || '/admin/dashboard'
    router.replace(redirect)
  } catch (e) {
    console.error('[Login]', e)
    ElMessage.error(e.message || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>