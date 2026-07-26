<template>
  <el-container class="layout">
    <!-- 左侧菜单 -->
    <el-aside :width="collapsed ? '64px' : '220px'" class="sidebar">
      <div class="logo-area">
        <span class="logo-icon">📈</span>
        <span v-show="!collapsed" class="logo-text">管理后台</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        :collapse="collapsed"
        :collapse-transition="false"
        router
        class="sidebar-menu"
      >
        <el-menu-item index="/admin/dashboard">
          <el-icon><Odometer /></el-icon>
          <template #title>仪表盘</template>
        </el-menu-item>
        <el-menu-item index="/admin/stocks">
          <el-icon><Box /></el-icon>
          <template #title>股票管理</template>
        </el-menu-item>
        <el-menu-item index="/admin/kline">
          <el-icon><DataLine /></el-icon>
          <template #title>K线查询</template>
        </el-menu-item>
        <el-menu-item index="/admin/scheduler">
          <el-icon><AlarmClock /></el-icon>
          <template #title>数据任务</template>
        </el-menu-item>
        <el-menu-item index="/admin/backtest">
          <el-icon><TrendCharts /></el-icon>
          <template #title>回测中心</template>
        </el-menu-item>
        <el-menu-item index="/admin/strategies">
          <el-icon><EditPen /></el-icon>
          <template #title>策略编辑器</template>
        </el-menu-item>
        <el-menu-item index="/admin/sources">
          <el-icon><Coin /></el-icon>
          <template #title>数据源</template>
        </el-menu-item>
        <el-menu-item index="/admin/system">
          <el-icon><Setting /></el-icon>
          <template #title>系统状态</template>
        </el-menu-item>
        <el-menu-item index="/admin/train-users">
          <el-icon><User /></el-icon>
          <template #title>训练用户管理</template>
        </el-menu-item>
        <el-menu-item index="/admin/train-redeem">
          <el-icon><Ticket /></el-icon>
          <template #title>兑换码生成</template>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <!-- 顶部 -->
      <el-header class="header">
        <div class="header-left">
          <el-icon class="collapse-btn" @click="collapsed = !collapsed">
            <Fold v-if="!collapsed" />
            <Expand v-else />
          </el-icon>
          <el-breadcrumb separator="/">
            <el-breadcrumb-item :to="{ path: '/admin/dashboard' }">首页</el-breadcrumb-item>
            <el-breadcrumb-item>{{ menuTitle }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="header-right">
          <el-tag size="small" type="success">在线</el-tag>
          <el-dropdown @command="onCommand">
            <span class="user-info">
              <el-icon><UserFilled /></el-icon>
              <span>{{ auth.user?.username }}</span>
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="password">修改密码</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <!-- 右侧内容 -->
      <el-main class="main-content">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>

    <!-- 修改密码 -->
    <el-dialog v-model="pwdDialog" title="修改密码" width="420px">
      <el-form :model="pwdForm" label-width="90px">
        <el-form-item label="原密码">
          <el-input v-model="pwdForm.old_password" type="password" show-password />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="pwdForm.new_password" type="password" show-password />
        </el-form-item>
        <el-form-item label="确认密码">
          <el-input v-model="pwdForm.confirm" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="pwdDialog = false">取消</el-button>
        <el-button type="primary" :loading="pwdLoading" @click="changePassword">确认</el-button>
      </template>
    </el-dialog>
  </el-container>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const collapsed = ref(false)

const pwdDialog = ref(false)
const pwdLoading = ref(false)
const pwdForm = ref({ old_password: '', new_password: '', confirm: '' })

const activeMenu = computed(() => route.path)
const menuTitle = computed(() => route.meta?.title || '')

onMounted(async () => {
  // 启动时尝试获取用户信息。如果用户没有 admin token(例如从训练端误入),
  // 不在此处强制跳转,让具体页面(如 UsersAdmin)给出友好的引导提示。
  if (!auth.token) return
  try {
    // 复用 trainApi.me 也能读 /auth/me,但为避免双重 import,这里直接调 api
    const { authApi } = await import('@/api/modules')
    const me = await authApi.me()
    const payload = me?.data ?? me
    if (payload?.username) {
      auth.user = {
        username: payload.username,
        user_id: payload.id ?? payload.user_id,
        last_login: payload.last_login,
      }
    }
  } catch {
    // token 过期则清掉,跳到登录页(用户已经在 admin 区域,这样体验比卡死好)
    auth.clear()
    router.push('/admin/login')
  }
})

async function onCommand(cmd) {
  if (cmd === 'logout') {
    try { await authApi.logout() } catch {}
    auth.clear()
    ElMessage.success('已退出登录')
    router.push('/admin/login')
  } else if (cmd === 'password') {
    pwdForm.value = { old_password: '', new_password: '', confirm: '' }
    pwdDialog.value = true
  }
}

async function changePassword() {
  const { old_password, new_password, confirm } = pwdForm.value
  if (!old_password || !new_password) return ElMessage.warning('请填写完整')
  if (new_password !== confirm) return ElMessage.warning('两次密码不一致')
  if (new_password.length < 6) return ElMessage.warning('新密码至少 6 位')
  pwdLoading.value = true
  try {
    await authApi.changePassword(old_password, new_password)
    ElMessage.success('密码已修改,请重新登录')
    pwdDialog.value = false
    setTimeout(() => {
      auth.clear()
      router.push('/admin/login')
    }, 800)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    pwdLoading.value = false
  }
}
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>