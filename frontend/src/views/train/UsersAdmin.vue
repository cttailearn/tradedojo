<template>
  <div class="users-admin">
    <el-alert v-if="!hasAdminToken" type="warning" :closable="false" show-icon
              style="margin-bottom: 16px;">
      <template #title>此页面仅对管理员开放</template>
      <div>
        你目前登录的是用户端账号（<b>{{ trainUser?.username }}</b>），
        没有管理员 token,无法访问用户端的管理后台。
      </div>
      <div style="margin-top: 8px;">
        <el-button type="primary" size="small" @click="goAdminLogin">
          <el-icon><Switch /></el-icon>切换到管理员登录
        </el-button>
        <el-link type="info" style="margin-left: 12px;" @click="goBackHome">
          返回首页
        </el-link>
      </div>
    </el-alert>

    <el-alert v-else type="error" :closable="false" show-icon style="margin-bottom: 16px;">
      <template #title>管理员后台·所有操作均会记入审计日志</template>
      <span>当前操作者: <b>{{ adminWho }}</b> · 共 {{ actionLogTotal }} 条审计</span>
    </el-alert>

    <el-tabs v-if="hasAdminToken" v-model="activeTab">
      <!-- ===== 用户管理 ===== -->
      <el-tab-pane label="用户管理" name="users">
        <div class="page-card">
          <div class="head-row">
            <h3 class="page-title">训练用户列表 ({{ userList.total }} 人)</h3>
            <div class="filter-row">
              <el-input v-model="userSearch" placeholder="搜账号/昵称" clearable style="width: 200px;" @clear="loadUsers" @keyup.enter="loadUsers" />
              <el-select v-model="userActiveFilter" placeholder="状态" style="width: 120px; margin-left: 8px;" @change="loadUsers">
                <el-option label="全部" :value="null" />
                <el-option label="启用" :value="1" />
                <el-option label="停用" :value="0" />
              </el-select>
              <el-button @click="loadUsers" :loading="loading.users" style="margin-left: 8px;">
                <el-icon><Refresh /></el-icon>刷新
              </el-button>
            </div>
          </div>

          <el-table :data="userList.items" stripe v-loading="loading.users" max-height="600">
            <el-table-column prop="id" label="UID" width="70" />
            <el-table-column label="账号" min-width="160">
              <template #default="{ row }">
                <strong>{{ row.username }}</strong>
                <span v-if="row.display_name && row.display_name !== row.username" class="muted">
                  ({{ row.display_name }})
                </span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">
                  {{ row.is_active ? '启用' : '停用' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="钱包" align="right" width="240">
              <template #default="{ row }">
                <div style="font-weight: bold; color: #67c23a;">¥ {{ money(row.wallet.balance) }}</div>
                <div class="muted small">
                  累计充值 ¥{{ money(row.wallet.total_topup) }} ·
                  累计消耗 ¥{{ money(row.wallet.total_spent) }}
                </div>
              </template>
            </el-table-column>
            <el-table-column label="最近活跃" width="160">
              <template #default="{ row }">
                <span v-if="row.last_login">{{ row.last_login }}</span>
                <span v-else class="muted">从未登录</span>
              </template>
            </el-table-column>
            <el-table-column label="注册时间" width="160">
              <template #default="{ row }">{{ row.created_at || '-' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="280" fixed="right">
              <template #default="{ row }">
                <el-button size="small" type="primary" plain @click="openWalletDialog(row)">
                  <el-icon><Wallet /></el-icon>调整金额
                </el-button>
                <el-button size="small" :type="row.is_active ? 'warning' : 'success'" plain
                          @click="toggleActive(row)">
                  {{ row.is_active ? '停用' : '启用' }}
                </el-button>
                <el-dropdown size="small" style="margin-left: 8px;">
                  <el-button size="small" plain>
                    更多<el-icon><ArrowDown /></el-icon>
                  </el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item @click="openResetPwd(row)">
                        <el-icon><Lock /></el-icon>重置密码
                      </el-dropdown-item>
                      <el-dropdown-item @click="openLogDialog(row, 'user')">
                        <el-icon><Document /></el-icon>查看该用户相关日志
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </template>
            </el-table-column>
          </el-table>

          <el-empty v-if="!loading.users && !userList.items.length" description="没有训练用户" :image-size="80" />
        </div>
      </el-tab-pane>

      <!-- ===== 兑换码作废 ===== -->
      <el-tab-pane label="兑换码管理" name="codes">
        <div class="page-card">
          <div class="head-row">
            <h3 class="page-title">兑换码 (最近 {{ codeList.total }} 张)</h3>
            <div class="filter-row">
              <el-input v-model="codeSearch" placeholder="搜码段" clearable style="width: 200px;" @clear="loadCodes" @keyup.enter="loadCodes" />
              <el-select v-model="codeStatusFilter" placeholder="状态" style="width: 160px; margin-left: 8px;" @change="loadCodes">
                <el-option label="全部" :value="null" />
                <el-option label="未使用" :value="unused" />
                <el-option label="已使用" :value="used" />
                <el-option label="已作废" :value="revoked" />
              </el-select>
              <el-button @click="loadCodes" :loading="loading.codes" style="margin-left: 8px;">
                <el-icon><Refresh /></el-icon>刷新
              </el-button>
            </div>
          </div>

          <el-table :data="codeList.items" stripe v-loading="loading.codes" max-height="600">
            <el-table-column prop="code" label="兑换码" min-width="200" />
            <el-table-column prop="amount" label="金额" width="100" align="right">
              <template #default="{ row }">¥ {{ money(row.amount) }}</template>
            </el-table-column>
            <el-table-column label="状态" width="120">
              <template #default="{ row }">
                <el-tag v-if="row.revoked" type="danger" size="small">已作废</el-tag>
                <el-tag v-else-if="row.is_used" type="info" size="small">已使用</el-tag>
                <el-tag v-else type="success" size="small">未使用</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="使用者" width="160">
              <template #default="{ row }">
                <span v-if="row.used_by_username">{{ row.used_by_username }} (uid {{ row.used_by }})</span>
                <span v-else-if="row.is_used">uid {{ row.used_by }}</span>
                <span v-else class="muted">-</span>
              </template>
            </el-table-column>
            <el-table-column prop="used_at" label="使用时间" width="170">
              <template #default="{ row }">
                <span v-if="row.used_at">{{ row.used_at }}</span>
                <span v-else class="muted">-</span>
              </template>
            </el-table-column>
            <el-table-column prop="created_by" label="生成者" width="120" />
            <el-table-column prop="note" label="备注" />
            <el-table-column label="操作" width="130" fixed="right">
              <template #default="{ row }">
                <el-button v-if="!row.is_used && !row.revoked"
                          size="small" type="danger" plain @click="openRevoke(row)">
                  <el-icon><CircleClose /></el-icon>作废
                </el-button>
                <span v-else class="muted">无</span>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!loading.codes && !codeList.items.length" description="无符合条件的兑换码" :image-size="80" />
        </div>
      </el-tab-pane>

      <!-- ===== 操作日志 ===== -->
      <el-tab-pane label="操作日志" name="logs">
        <div class="page-card">
          <div class="head-row">
            <h3 class="page-title">管理员操作日志 ({{ logList.total }} 条)</h3>
            <div class="filter-row">
              <el-select v-model="logActionFilter" placeholder="按动作类型" clearable style="width: 200px;" @change="loadLogs">
                <el-option label="创建兑换码" value="create_redeem_codes" />
                <el-option label="作废兑换码" value="revoke_redeem_code" />
                <el-option label="调整用户状态" value="set_user_active" />
                <el-option label="重置密码" value="reset_user_password" />
                <el-option label="加减金额" value="adjust_wallet" />
              </el-select>
              <el-button @click="loadLogs" :loading="loading.logs" style="margin-left: 8px;">
                <el-icon><Refresh /></el-icon>刷新
              </el-button>
            </div>
          </div>

          <el-table :data="logList.items" stripe v-loading="loading.logs" max-height="600">
            <el-table-column prop="id" label="#" width="70" />
            <el-table-column prop="created_at" label="时间" width="170" />
            <el-table-column prop="actor" label="操作者" width="100">
              <template #default="{ row }"><strong>{{ row.actor }}</strong></template>
            </el-table-column>
            <el-table-column prop="action" label="动作" width="180">
              <template #default="{ row }">
                <el-tag size="small">{{ row.action }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="对象" width="140">
              <template #default="{ row }">
                <span v-if="row.target_type">{{ row.target_type }}/{{ row.target_id }}</span>
                <span v-else class="muted">-</span>
              </template>
            </el-table-column>
            <el-table-column label="原因" min-width="180">
              <template #default="{ row }">
                <span v-if="row.reason">{{ row.reason }}</span>
                <span v-else class="muted">-</span>
              </template>
            </el-table-column>
            <el-table-column label="变更" min-width="220">
              <template #default="{ row }">
                <span v-if="row.before_value || row.after_value">
                  <span class="muted">{{ row.before_value }}</span>
                  →
                  <span class="strong">{{ row.after_value }}</span>
                </span>
                <span v-else class="muted">-</span>
              </template>
            </el-table-column>
            <el-table-column label="详情" min-width="240">
              <template #default="{ row }">
                <el-link v-if="row.detail_json" type="primary" size="small"
                         @click="showDetail(row.detail_json)">查看</el-link>
                <span v-else class="muted">-</span>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!loading.logs && !logList.items.length" description="无操作日志" :image-size="80" />
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 调整金额 对话框 -->
    <el-dialog v-model="dialog.wallet" title="调整用户余额" width="500px">
      <el-form v-if="walletTarget" label-width="100px">
        <el-form-item label="用户">
          <strong>{{ walletTarget.username }}</strong>
          <span class="muted">当前余额: ¥ {{ money(walletTarget.wallet.balance) }}</span>
        </el-form-item>
        <el-form-item label="调整金额" required>
          <el-input-number v-model="walletForm.delta" :step="100" :precision="2"
                           placeholder="正数=加款,负数=扣款" />
          <span class="hint">金额(¥),正负都可</span>
        </el-form-item>
        <el-form-item label="影响累计">
          <el-radio-group v-model="walletForm.adjust_topup">
            <el-radio :value="false">扣款记消耗 / 加款记充值</el-radio>
            <el-radio :value="true">不计到充值/消耗(纯调整余额)</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="原因" required>
          <el-input v-model="walletForm.reason" type="textarea" :rows="2"
                    placeholder="必填,会写进审计日志,如 '2024Q1 退款 - 重复充值'" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog.wallet = false">取消</el-button>
        <el-button type="primary" :loading="actionLoading" @click="submitAdjustWallet">确认调整</el-button>
      </template>
    </el-dialog>

    <!-- 重置密码对话框 -->
    <el-dialog v-model="dialog.reset" title="重置密码" width="460px">
      <el-form v-if="resetTarget" label-width="100px">
        <el-form-item label="用户">
          <strong>{{ resetTarget.username }}</strong>
        </el-form-item>
        <el-form-item label="新密码" required>
          <el-input v-model="resetForm.new_password" placeholder="至少 6 位" show-password />
        </el-form-item>
        <el-form-item label="原因" required>
          <el-input v-model="resetForm.reason" type="textarea" :rows="2"
                    placeholder="必填" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog.reset = false">取消</el-button>
        <el-button type="primary" :loading="actionLoading" @click="submitResetPwd">确认重置</el-button>
      </template>
    </el-dialog>

    <!-- 停用 / 启用 对话框 -->
    <el-dialog v-model="dialog.active" :title="activeTarget?.is_active ? '停用账号' : '启用账号'" width="420px">
      <el-form v-if="activeTarget" label-width="80px">
        <el-form-item label="用户">
          <strong>{{ activeTarget.username }}</strong>
        </el-form-item>
        <el-form-item label="原因" required>
          <el-input v-model="activeReason" type="textarea" :rows="3"
                    :placeholder="activeTarget.is_active ? '为什么停用?违规 / 客户要求...': '为什么启用?已申诉...'" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog.active = false">取消</el-button>
        <el-button :type="activeTarget?.is_active ? 'danger' : 'success'" :loading="actionLoading"
                   @click="submitToggleActive">确认</el-button>
      </template>
    </el-dialog>

    <!-- 作废兑换码 对话框 -->
    <el-dialog v-model="dialog.revoke" title="作废兑换码" width="460px">
      <el-form v-if="revokeTarget" label-width="100px">
        <el-form-item label="兑换码">
          <span class="code-text">{{ revokeTarget.code }}</span>
        </el-form-item>
        <el-form-item label="面额">
          ¥ {{ money(revokeTarget.amount) }}
        </el-form-item>
        <el-form-item label="原因" required>
          <el-input v-model="revokeReason" type="textarea" :rows="2"
                    placeholder="必填,如 '错发 / 安全风险 / 客户退订'" />
        </el-form-item>
        <el-alert type="warning" :closable="false" show-icon>
          已使用的兑换码不能作废,如需退款请到用户管理页调整余额
        </el-alert>
      </el-form>
      <template #footer>
        <el-button @click="dialog.revoke = false">取消</el-button>
        <el-button type="danger" :loading="actionLoading" @click="submitRevoke">确认作废</el-button>
      </template>
    </el-dialog>

    <!-- 详情弹窗 -->
    <el-dialog v-model="dialog.detail" title="操作详情" width="500px">
      <pre class="json-text">{{ detailText }}</pre>
      <template #footer>
        <el-button @click="dialog.detail = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { trainApi } from '@/api/modules'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()
const adminWho = ref('')
const trainUser = ref(null)
const hasAdminToken = ref(false)
const actionLogTotal = ref(0)
const activeTab = ref('users')

// 是否同时拥有 admin token(从管理后台登录拿到的)
// 同时校验 Pinia store 和 localStorage,避免状态不同步
function checkTokens() {
  const auth = useAuthStore()
  const storeToken = auth.token || ''
  const lsToken = localStorage.getItem('stock_admin_token') || ''
  // 任一来源存在即认为已登录管理员
  const token = storeToken || lsToken
  if (!token) {
    hasAdminToken.value = false
    trainUser.value = JSON.parse(localStorage.getItem('stock_train_user') || 'null')
    return
  }
  hasAdminToken.value = true
  // 把 localStorage 的 token 同步回 store(防止另一处清掉 store 但 localStorage 还有)
  if (!storeToken && lsToken) {
    try {
      const u = JSON.parse(localStorage.getItem('stock_admin_user') || 'null')
      auth.setAuth(lsToken, u || { username: 'admin' })
    } catch {}
  }
  try {
    const u = JSON.parse(localStorage.getItem('stock_admin_user') || 'null')
    adminWho.value = u?.username || 'admin'
  } catch { adminWho.value = 'admin' }
}

function goAdminLogin() {
  // 用 router.push 让路由守卫走标准流程(避免直接改 hash 绕过守卫)
  router.push('/admin/login')
}

function goBackHome() {
  router.push('/train/home')
}

const me = ref(null)

// ============== users ==============
const userList = reactive({ items: [], total: 0 })
const userSearch = ref('')
const userActiveFilter = ref(null)
const loading = reactive({ users: false, codes: false, logs: false })

async function loadUsers() {
  loading.users = true
  try {
    const params = { limit: 200 }
    if (userSearch.value.trim()) params.search = userSearch.value.trim()
    if (userActiveFilter.value !== null) params.is_active = userActiveFilter.value
    userList.items = []
    const res = await trainApi.adminListUsers(params)
    Object.assign(userList, res)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.users = false
  }
}

// ============== redeem codes ==============
const codeList = reactive({ items: [], total: 0 })
const codeSearch = ref('')
const codeStatusFilter = ref(null)
const STATUS = { unused: { is_used: 0, revoked: 0 }, used: { is_used: 1 }, revoked: { revoked: 1 } }

async function loadCodes() {
  loading.codes = true
  try {
    const params = { limit: 200 }
    if (codeSearch.value.trim()) params.search = codeSearch.value.trim()
    const filterKey = codeStatusFilter.value
    if (filterKey && STATUS[filterKey]) {
      Object.assign(params, STATUS[filterKey])
    }
    const res = await trainApi.adminListCodes(params)
    Object.assign(codeList, res)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.codes = false
  }
}

// ============== action logs ==============
const logList = reactive({ items: [], total: 0 })
const logActionFilter = ref(null)

async function loadLogs() {
  loading.logs = true
  try {
    const params = { limit: 200 }
    if (logActionFilter.value) params.action = logActionFilter.value
    const res = await trainApi.adminActionLog(params)
    Object.assign(logList, res)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.logs = false
  }
}

// ============== 详情弹窗 ==============
const dialog = reactive({ wallet: false, reset: false, active: false, revoke: false, detail: false })
const detailText = ref('')

function showDetail(jsonStr) {
  try {
    detailText.value = JSON.stringify(JSON.parse(jsonStr), null, 2)
  } catch {
    detailText.value = jsonStr
  }
  dialog.detail = true
}

// ============== wallet adjustment ==============
const walletTarget = ref(null)
const walletForm = reactive({ delta: 0, reason: '', adjust_topup: false })
const actionLoading = ref(false)

function openWalletDialog(row) {
  walletTarget.value = row
  walletForm.delta = 0
  walletForm.reason = ''
  walletForm.adjust_topup = false
  dialog.wallet = true
}

async function submitAdjustWallet() {
  if (!walletForm.delta || Math.abs(walletForm.delta) < 0.01) {
    return ElMessage.warning('请输入非 0 的调整金额')
  }
  if (!walletForm.reason || walletForm.reason.trim().length < 2) {
    return ElMessage.warning('请填原因(至少 2 字)')
  }
  actionLoading.value = true
  try {
    const res = await trainApi.adminAdjustWallet(
      walletTarget.value.id,
      walletForm.delta,
      walletForm.reason.trim(),
      walletForm.adjust_topup,
    )
    ElMessage.success(`已调整 ${walletTarget.value.username} 余额:¥ ${money(walletTarget.value.wallet.balance)} → ¥ ${money(res.after_balance)}`)
    dialog.wallet = false
    await Promise.all([loadUsers(), loadLogs()])
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    actionLoading.value = false
  }
}

// ============== reset password ==============
const resetTarget = ref(null)
const resetForm = reactive({ new_password: '', reason: '' })

function openResetPwd(row) {
  resetTarget.value = row
  resetForm.new_password = ''
  resetForm.reason = ''
  dialog.reset = true
}

async function submitResetPwd() {
  if (!resetForm.new_password || resetForm.new_password.length < 6) {
    return ElMessage.warning('新密码至少 6 位')
  }
  if (!resetForm.reason || resetForm.reason.trim().length < 2) {
    return ElMessage.warning('请填原因')
  }
  try {
    await ElMessageBox.confirm(
      `重置 ${resetTarget.value.username} 密码会立即生效,用户即将被踢下线,确定?`,
      '警告',
      { type: 'warning' },
    )
  } catch { return }
  actionLoading.value = true
  try {
    await trainApi.adminResetPassword(
      resetTarget.value.id,
      resetForm.new_password,
      resetForm.reason.trim(),
    )
    ElMessage.success('已重置密码')
    dialog.reset = false
    await loadLogs()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    actionLoading.value = false
  }
}

// ============== toggle active ==============
const activeTarget = ref(null)
const activeReason = ref('')

function toggleActive(row) {
  activeTarget.value = row
  activeReason.value = ''
  dialog.active = true
}

async function submitToggleActive() {
  if (!activeReason.value || activeReason.value.trim().length < 2) {
    return ElMessage.warning('请填原因(至少 2 字)')
  }
  actionLoading.value = true
  try {
    await trainApi.adminSetActive(
      activeTarget.value.id,
      !activeTarget.value.is_active,
      activeReason.value.trim(),
    )
    ElMessage.success('已生效')
    dialog.active = false
    await Promise.all([loadUsers(), loadLogs()])
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    actionLoading.value = false
  }
}

// ============== revoke code ==============
const revokeTarget = ref(null)
const revokeReason = ref('')

function openRevoke(row) {
  revokeTarget.value = row
  revokeReason.value = ''
  dialog.revoke = true
}

async function submitRevoke() {
  if (!revokeReason.value || revokeReason.value.trim().length < 2) {
    return ElMessage.warning('请填原因')
  }
  actionLoading.value = true
  try {
    await trainApi.adminRevokeCode(revokeTarget.value.code, revokeReason.value.trim())
    ElMessage.success('已作废')
    dialog.revoke = false
    await Promise.all([loadCodes(), loadLogs()])
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    actionLoading.value = false
  }
}

// ============== utils ==============
function money(v) {
  return Number(v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function openLogDialog(row, kind) {
  logActionFilter.value = null
  activeTab.value = 'logs'
  // 简化:切到 logs 自动加载全部;后续可以加按 user_id 过滤
}

onMounted(async () => {
  checkTokens()
  if (!hasAdminToken.value) return
  try { me.value = await trainApi.me() } catch {}
  await Promise.all([loadUsers(), loadCodes(), loadLogs()])
  actionLogTotal.value = logList.total
})

watch(activeTab, (v) => {
  if (v === 'logs') loadLogs()
  if (v === 'codes') loadCodes()
})
</script>

<style scoped>
.head-row {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px; flex-wrap: wrap; gap: 8px;
}
.head-row .page-title { margin: 0; }
.filter-row { display: flex; align-items: center; }
.page-card { background: #fff; padding: 16px; border-radius: 6px;
             box-shadow: 0 1px 4px rgba(0,0,0,.06); }
.muted { color: #909399; }
.muted.small { font-size: 12px; }
.strong { font-weight: bold; color: #67c23a; }
.code-text { font-family: Consolas, monospace; font-weight: bold; color: #1f3b66;
             background: #f0f4ff; padding: 2px 8px; border-radius: 4px; }
.json-text { max-height: 400px; overflow: auto; background: #f6f8fb;
             padding: 12px; border-radius: 4px; font-family: Consolas, monospace;
             font-size: 12px; }
.hint { color: #909399; font-size: 12px; margin-left: 8px; }
</style>
