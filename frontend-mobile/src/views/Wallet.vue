<template>
  <div class="wallet page page--no-navbar" :style="{ paddingTop: 'var(--navbar-h)' }">
    <div class="wallet__intro">
      <h2>钱包 / 兑换</h2>
    </div>

    <!-- 余额卡 -->
    <section class="balance">
      <div class="balance__lbl">训练资金余额</div>
      <div class="balance__amount num">¥ {{ money(auth.wallet.balance) }}</div>
      <div class="balance__meta">
        <div>
          <div class="balance__meta-lbl">累计充值</div>
          <div class="num">¥ {{ money(auth.wallet.total_topup) }}</div>
        </div>
        <div>
          <div class="balance__meta-lbl">累计消耗</div>
          <div class="num">¥ {{ money(auth.wallet.total_spent) }}</div>
        </div>
      </div>
    </section>

    <!-- 兑换码 -->
    <section class="card">
      <h3 class="card__title">🔑 兑换码充值</h3>
      <van-field
        v-model="code"
        placeholder="如 ABCD1234-00100000"
        clearable
        size="large"
        style="margin-bottom: var(--sp-3xl);"
      />
      <button
        class="btn btn--primary btn--block btn--lg"
        :disabled="loading || !code.trim()"
        @click="redeem"
      >
        <span v-if="loading">兑换中…</span>
        <span v-else>立刻兑换</span>
      </button>
      <div
        v-if="auth.wallet.balance < 50"
        class="alert"
        style="background: #fef2f2; color: var(--color-danger); margin-top: var(--sp-3xl);"
      >余额偏低,建议尽快充值!</div>
    </section>

    <!-- 充值记录 -->
    <section class="card">
      <h3 class="card__title">充值记录</h3>
      <ul class="list" v-if="history.length">
        <li v-for="(h, i) in history" :key="i" class="list-item">
          <div class="list-item__body">
            <div class="list-item__title">{{ h.code }}</div>
            <div class="list-item__sub">{{ h.time }}</div>
          </div>
          <div class="list-item__aside up" style="font-weight: 600;">
            + ¥ {{ money(h.amount) }}
          </div>
        </li>
      </ul>
      <div class="empty" v-else>
        <div class="empty__icon">💰</div>
        <div class="empty__text">还没有充值记录</div>
      </div>
    </section>

    <section class="card">
      <h3 class="card__title">怎么获取兑换码?</h3>
      <p style="font-size: 0.26rem; line-height: 1.7; color: var(--text-regular); margin: 0;">
        请联系系统管理员 (admin) 生成兑换码,然后把码发给你。
      </p>
    </section>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import { showToast, showSuccessToast } from 'vant'
import { trainApi } from '@/api/modules'
import { useTrainAuthStore } from '@/stores/trainAuth'
import { money } from '@/utils/trainFee'

const auth = useTrainAuthStore()
const code = ref('')
const loading = ref(false)
const history = ref([])

async function load() {
  try {
    const w = await trainApi.wallet()
    auth.setWallet(w || {})
    // history 暂从 w.recent_redemptions 之类读取(后端若没有则为空)
    history.value = w?.recent_redemptions || w?.redemption_history || []
  } catch { /* silent */ }
}

async function redeem() {
  if (!code.value.trim()) return showToast('请输入兑换码')
  loading.value = true
  try {
    const r = await trainApi.redeem(code.value.trim())
    const amount = r?.amount || r?.data?.amount || 0
    showSuccessToast(`成功充值 ¥ ${money(amount)}`)
    code.value = ''
    await load()
  } catch (e) {
    showToast({ type: 'fail', message: e.message || '兑换失败' })
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.wallet__intro { padding: var(--sp-4xl); }
.wallet__intro h2 { margin: 0; font-size: 0.40rem; font-weight: 700; }

.balance {
  margin: 0 var(--sp-4xl) var(--sp-3xl);
  background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
  color: #fff;
  border-radius: var(--radius-xl);
  padding: var(--sp-5xl);
  box-shadow: var(--shadow-md);
}
.balance__lbl { font-size: 0.26rem; opacity: 0.9; }
.balance__amount {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  margin: var(--sp-3xl) 0;
}
.balance__meta { display: grid; grid-template-columns: 1fr 1fr; gap: var(--sp-3xl); }
.balance__meta-lbl { font-size: 0.22rem; opacity: 0.85; margin-bottom: var(--sp-sm); }

.alert {
  padding: var(--sp-3xl);
  border-radius: var(--radius-md);
  font-size: 0.24rem;
}

.up { color: var(--color-up); }
</style>
