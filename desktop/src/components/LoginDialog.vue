<script setup lang="ts">
import { ref } from 'vue'

const emit = defineEmits<{ close: [] }>()
const username = ref('admin')
const password = ref('')
const busy = ref(false)
const error = ref('')

async function submit(): Promise<void> {
  busy.value = true
  error.value = ''
  const r = await window.hajimi.authLogin(username.value, password.value)
  busy.value = false
  if (r.ok) emit('close')
  else error.value = r.error ?? '登录失败'
}
</script>

<template>
  <div class="mask">
    <form class="dlg" @submit.prevent="submit">
      <h2>HAJIMI 登录</h2>
      <label>用户名
        <input v-model="username" autocomplete="username" />
      </label>
      <label>密码
        <input v-model="password" type="password" autocomplete="current-password" />
      </label>
      <p v-if="error" class="err">{{ error }}</p>
      <div class="btns">
        <button type="submit" class="primary" :disabled="busy || !password">{{ busy ? '登录中…' : '登录' }}</button>
      </div>
      <p class="hint">离线 + 默认凭据(admin/demo123) 时生成本地演示会话（与 PyQt 行为一致）。</p>
    </form>
  </div>
</template>

<style scoped>
.mask {
  position: fixed;
  inset: 0;
  background: rgba(2, 6, 23, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 60;
}
.dlg {
  width: min(90%, 320px);
  background: var(--hm-panel);
  border: 1px solid rgba(100, 116, 139, 0.4);
  border-radius: 12px;
  padding: 18px 20px;
}
h2 {
  font-size: 15px;
  margin: 0 0 12px;
}
label {
  display: block;
  font-size: 12px;
  color: var(--hm-muted);
  margin-bottom: 10px;
}
input {
  display: block;
  width: 100%;
  margin-top: 3px;
  background: var(--hm-bg);
  color: var(--hm-text);
  border: 1px solid rgba(100, 116, 139, 0.35);
  border-radius: 6px;
  padding: 7px 9px;
  font: inherit;
}
.err {
  color: var(--hm-danger);
  font-size: 12px;
}
.btns {
  display: flex;
  justify-content: flex-end;
}
.primary {
  background: var(--hm-accent);
  color: #1e1b34;
  border: none;
  border-radius: 8px;
  padding: 7px 20px;
  font-weight: 600;
  cursor: pointer;
}
.hint {
  font-size: 11px;
  color: var(--hm-muted);
  margin: 10px 0 0;
}
</style>
