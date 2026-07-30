<template>
  <header class="navbar">
    <div class="navbar__left">
      <button
        v-if="showBack"
        class="navbar__btn"
        aria-label="返回"
        @click="onBack"
      >
        <svg viewBox="0 0 24 24" width="22" height="22">
          <path d="M15 18 9 12l6-6" fill="none" stroke="currentColor" stroke-width="2"
                stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </button>
      <slot name="left" />
    </div>
    <div class="navbar__title">{{ title }}</div>
    <div class="navbar__right">
      <slot name="right" />
    </div>
  </header>
</template>

<script setup>
import { useRouter } from 'vue-router'

const props = defineProps({
  title: { type: String, default: '' },
  showBack: { type: Boolean, default: false },
})
const emit = defineEmits(['back'])
const router = useRouter()

function onBack() {
  emit('back')
  if (window.history.length > 1) router.back()
  else router.replace('/home')
}
</script>

<style scoped>
.navbar {
  position: sticky;
  top: 0;
  z-index: 50;
  height: var(--navbar-h);
  display: flex;
  align-items: center;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border-color-light);
  padding: 0 var(--sp-3xl);
  /* Tauri 安全区:statusBar H 由原生控状态栏;但 iOS notch 要 padding */
  padding-top: constant(safe-area-inset-top); /* iOS 11.0-11.2 */
}
.navbar__left,
.navbar__right { flex: 0 0 0.84rem; display: flex; align-items: center; }
.navbar__right { justify-content: flex-end; }
.navbar__btn {
  background: transparent;
  border: none;
  color: var(--text-primary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 0.56rem;
  height: 0.56rem;
  border-radius: var(--radius-full);
  cursor: pointer;
  transition: background 0.15s;
}
.navbar__btn:active { background: var(--bg-hover); }

.navbar__title {
  flex: 1;
  text-align: center;
  font-size: 0.32rem;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
