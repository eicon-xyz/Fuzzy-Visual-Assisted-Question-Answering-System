<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useTaskStore } from './stores/task'
import StatusBar from './components/StatusBar.vue'
import Timeline from './components/Timeline.vue'
import InputBar from './components/InputBar.vue'
import ConsentDialog from './components/ConsentDialog.vue'
import SettingsView from './components/SettingsView.vue'
import LoginDialog from './components/LoginDialog.vue'
import CompactBar from './components/CompactBar.vue'

const store = useTaskStore()
const { phase, steps, messages, busy } = storeToRefs(store)

const showConsent = ref(false)
const pendingQuery = ref('')
const showSettings = ref(false)
const needLogin = ref(false)
const compact = ref(false)
const theme = ref('current')
let unsub: (() => void) | null = null
let unsubMode: (() => void) | null = null

onMounted(async () => {
  unsub = window.hajimi.onTaskEvent((p) => store.onTaskEvent(p))
  unsubMode = window.hajimi.onWindowMode((m) => (compact.value = m.compact))
  compact.value = (await window.hajimi.windowGetMode()).compact
  const st = await window.hajimi.settingsGet()
  theme.value = st.ui_theme === 'variant_luxury' ? 'variant_luxury' : 'current'
  document.documentElement.dataset.theme = theme.value
  // 登录门：等价 PyQt main 的 HAJIMI_SKIP_LOGIN / is_session_valid 检查
  const auth = await window.hajimi.authStatus()
  needLogin.value = !auth.valid
})
onUnmounted(() => {
  unsub?.()
  unsubMode?.()
})

async function toggleCompact(): Promise<void> {
  const r = await window.hajimi.windowSetCompact(!compact.value)
  compact.value = r.compact
}

async function doSubmit(query: string, acceptConsent: boolean, dontShowAgain = true): Promise<void> {
  const r = await window.hajimi.taskSubmit(query, acceptConsent, dontShowAgain)
  if (r.consentDeclined) {
    store.pushSystem('已取消 L5 自动执行', 'warn')
    store.busy = false
    if (store.phase === 'planning') store.phase = 'idle'
    return
  }
  if (!r.ok) {
    store.pushSystem(`提交失败：${r.error ?? '未知错误'}`, 'danger')
    store.busy = false
    store.phase = 'failed'
  }
}

async function onSubmit(query: string): Promise<void> {
  const accepted = await window.hajimi.consentAccepted()
  pendingQuery.value = query
  if (!accepted) {
    // 与 PyQt 一致：弹知情确认，用户确认后才提交；同时先落用户消息
    store.resetForSubmit(query)
    showConsent.value = true
    return
  }
  store.resetForSubmit(query)
  await doSubmit(query, false)
}

async function onConsentAccept(dontShowAgain: boolean): Promise<void> {
  showConsent.value = false
  await doSubmit(pendingQuery.value, true, dontShowAgain)
}

async function onConsentDecline(): Promise<void> {
  showConsent.value = false
  await doSubmit(pendingQuery.value, false) // 主进程返回 consentDeclined
}

async function onCancel(): Promise<void> {
  const r = await window.hajimi.taskCancel()
  if (!r.ok) store.pushSystem(`取消失败：${r.error ?? ''}`, 'warn')
}
</script>

<template>
  <div class="shell">
    <template v-if="compact">
      <CompactBar @submit="onSubmit" @cancel="onCancel" @expand="toggleCompact" />
    </template>
    <template v-else>
      <header class="titlebar">
        <span class="title">HAJIMI · L5 桌面助手</span>
        <span class="tb-btns">
          <button class="tbb" title="紧凑模式" @click="toggleCompact">▁</button>
          <button class="tbb" title="设置" @click="showSettings = !showSettings">⚙</button>
        </span>
      </header>
      <StatusBar />
      <template v-if="showSettings">
        <SettingsView @close="showSettings = false" />
      </template>
      <template v-else>
        <section class="chat">
          <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role + ' ' + m.tone">
            {{ m.text }}
          </div>
        </section>
        <Timeline v-if="busy || steps.length || phase !== 'idle'" />
        <InputBar @submit="onSubmit" @cancel="onCancel" />
      </template>
    </template>
    <ConsentDialog v-if="showConsent" @accept="onConsentAccept" @decline="onConsentDecline" />
    <LoginDialog v-if="needLogin" @close="needLogin = false" />
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.tb-btns {
  -webkit-app-region: no-drag;
  display: flex;
  gap: 2px;
}
.tbb {
  background: transparent;
  border: none;
  color: var(--hm-muted);
  cursor: pointer;
  font-size: 13px;
  padding: 2px 8px;
  border-radius: 6px;
}
.tbb:hover {
  background: rgba(100, 116, 139, 0.25);
  color: var(--hm-text);
}
.chat {
  max-height: 30%;
  overflow-y: auto;
  padding: 8px 12px 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.msg {
  font-size: 13px;
  line-height: 1.55;
  padding: 6px 10px;
  border-radius: 8px;
  max-width: 92%;
}
.msg.user {
  align-self: flex-end;
  background: rgba(244, 114, 182, 0.16);
}
.msg.system {
  align-self: flex-start;
  color: var(--hm-muted);
}
.msg.system.ok {
  color: #86efac;
}
.msg.system.warn {
  color: #fde047;
}
.msg.system.danger {
  color: #fca5a5;
}
</style>
