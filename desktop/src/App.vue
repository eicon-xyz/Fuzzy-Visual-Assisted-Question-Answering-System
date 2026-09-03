<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useTaskStore } from './stores/task'
import StatusBar from './components/StatusBar.vue'
import Timeline from './components/Timeline.vue'
import InputBar from './components/InputBar.vue'
import ConsentDialog from './components/ConsentDialog.vue'

const store = useTaskStore()
const { phase, steps, messages, busy } = storeToRefs(store)

const showConsent = ref(false)
const pendingQuery = ref('')
let unsub: (() => void) | null = null

onMounted(() => {
  unsub = window.hajimi.onTaskEvent((p) => store.onTaskEvent(p))
})
onUnmounted(() => unsub?.())

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
    <header class="titlebar">
      <span class="title">HAJIMI · L5 桌面助手</span>
    </header>
    <StatusBar />
    <section class="chat">
      <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role + ' ' + m.tone">
        {{ m.text }}
      </div>
    </section>
    <Timeline v-if="busy || steps.length || phase !== 'idle'" />
    <InputBar @submit="onSubmit" @cancel="onCancel" />
    <ConsentDialog v-if="showConsent" @accept="onConsentAccept" @decline="onConsentDecline" />
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  flex-direction: column;
  height: 100%;
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
