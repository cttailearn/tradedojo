<template>
  <div class="login">
    <div class="login__brand">
      <div class="login__logo">📈</div>
      <h1 class="login__title">K线交易训练</h1>
      <p class="login__sub">真实历史数据 · 模拟资金 · 训练盘感</p>
    </div>

    <div class="login__tabs">
      <button
        class="login__tab"
        :class="{ 'is-active': mode === 'login' }"
        @click="mode = 'login'"
      >登录</button>
      <button
        class="login__tab"
        :class="{ 'is-active': mode === 'register' }"
        @click="mode = 'register'"
      >注册</button>
    </div>

    <form class="login__form" @submit.prevent="onSubmit">
      <label class="field">
        <span class="field__label">账号</span>
        <input
          v-model="form.username"
          class="field__input"
          type="text"
          placeholder="3-32 位字母/数字"
          autocomplete="username"
          autocapitalize="off"
          required
        />
      </label>

      <label v-if="mode === 'register'" class="field">
        <span class="field__label">昵称 (可选)</span>
        <input
          v-model="form.display_name"
          class="field__input"
          type="text"
          placeholder="显示给他人看的名字"
        />
      </label>

      <label class="field">
        <span class="field__label">密码</span>
        <input
          v-model="form.password"
          class="field__input"
          :type="showPassword ? 'text' : 'password'"
          :placeholder="mode === 'register' ? '≥ 8 位,含字母+数字' : '请输入密码'"
          autocomplete="current-password"
          required
        />
        <button
          type="button"
          class="field__toggle"
          @click="showPassword = !showPassword"
          aria-label="切换密码显示"
        >
          <span v-if="showPassword">🙈</span>
          <span v-else>👁</span>
        </button>
      </label>

      <button
        class="btn btn--primary btn--block btn--lg"
        :disabled="loading"
        @click="onSubmit"
      >
        <span v-if="loading">处理中…</span>
        <span v-else-if="mode === 'login'">登 录</span>
        <span v-else>注 册</span>
      </button>

      <p class="login__tip">
        <template v-if="mode === 'login'">
          还没有账号? 点上方"注册"标签
        </template>
        <template v-else>
          注册后到「钱包 → 兑换码」充值即可训练
        </template>
      </p>
    </form>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showToast } from 'vant'
import { trainApi } from '@/api/modules'
import { useTrainAuthStore } from '@/stores/trainAuth'

const router = useRouter()
const route = useRoute()
const auth = useTrainAuthStore()
const mode = ref('login')
const loading = ref(false)
const showPassword = ref(false)
const form = reactive({ username: '', password: '', display_name: '' })

async function onSubmit() {
  if (!form.username || !form.password) {
    showToast('请输入账号和密码')
    return
  }
  if (mode.value === 'login') {
    return doLogin()
  }
  return doRegister()
}

async function doLogin() {
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
    showToast({ type: 'success', message: `欢迎回来,${payload.display_name || payload.username}` })
    const redirect = route.query.redirect || '/home'
    router.replace(redirect)
  } catch (e) {
    showToast({ type: 'fail', message: e.message || '登录失败' })
  } finally {
    loading.value = false
  }
}

async function doRegister() {
  if (form.username.length < 3 || form.username.length > 32) {
    return showToast('账号长度需 3-32 位')
  }
  if (form.password.length < 8) return showToast('密码长度至少 8 位')
  if (!/[a-zA-Z]/.test(form.password) || !/\d/.test(form.password)) {
    return showToast('密码必须包含字母和数字')
  }
  loading.value = true
  try {
    await trainApi.register(form.username.trim(), form.password, form.display_name || '')
    showToast({ type: 'success', message: '注册成功,请登录' })
    mode.value = 'login'
    form.password = ''
  } catch (e) {
    showToast({ type: 'fail', message: e.message || '注册失败' })
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login {
  min-height: 100vh;
  min-height: 100dvh;
  padding: calc(var(--safe-top) + 1.5rem) var(--sp-5xl) var(--sp-5xl);
  background: linear-gradient(180deg, #eff6ff 0%, var(--bg-page) 30%);
}

.login__brand {
  text-align: center;
  margin-bottom: var(--sp-6xl);
}
.login__logo {
  font-size: 1.20rem;
  margin-bottom: var(--sp-2xl);
}
.login__title {
  margin: 0 0 var(--sp-lg);
  font-size: 0.44rem;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.02em;
}
.login__sub {
  margin: 0;
  color: var(--text-secondary);
  font-size: 0.26rem;
}

.login__tabs {
  display: flex;
  background: var(--bg-card);
  border-radius: var(--radius-full);
  padding: 4px;
  margin: 0 auto var(--sp-5xl);
  width: 5.00rem;
  box-shadow: var(--shadow-xs);
}
.login__tab {
  flex: 1;
  height: 0.64rem;
  border: none;
  background: transparent;
  border-radius: var(--radius-full);
  font-size: 0.28rem;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s;
}
.login__tab.is-active {
  background: var(--color-primary);
  color: #fff;
  font-weight: 600;
}

.login__form { max-width: 5.00rem; margin: 0 auto; }

.field { position: relative; }
.field__toggle {
  position: absolute;
  right: var(--sp-3xl);
  top: 50%;
  transform: translateY(-30%);
  background: transparent;
  border: none;
  cursor: pointer;
  font-size: 0.32rem;
  color: var(--text-placeholder);
}

.login__tip {
  text-align: center;
  margin-top: var(--sp-4xl);
  font-size: 0.24rem;
  color: var(--text-placeholder);
}
</style>
