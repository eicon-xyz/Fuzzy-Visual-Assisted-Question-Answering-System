<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import type { SidecarStatePayload } from '../../types/ipc'

const state = ref<SidecarStatePayload>({ phase: 'starting', detail: '探测中…' })
let unsub: (() => void) | null = null
let timer: ReturnType<typeof setInterval> | null = null

onMounted(async () => {
  unsub = window.hajimi.onSidecarState((s) => (state.value = s))
  const poll = async (): Promise<void> => {
    const st = await window.hajimi.sidecarStatus()
    if (st.ok) state.value = { phase: 'running', detail: st.detail }
    else if (state.value.phase === 'running') state.value = { phase: 'down', detail: 'down' }
  }
  await poll()
  timer = setInterval(() => void poll(), 8000)
})
onUnmounted(() => {
  unsub?.()
  if (timer) clearInterval(timer)
})

const cls = () =>
  state.value.phase === 'running' ? 'ok' : state.value.phase === 'down' || state.value.phase === 'failed' || state.value.phase === 'missing' ? 'bad' : 'warn'
</script>

<template>
  <div class="statusbar">
    <span class="dot" :class="cls()" />
    <span class="text">
      <template v-if="state.phase === 'running'">L5 自动执行就绪 (Sidecar :8011)</template>
      <template v-else>{{ state.detail }}</template>
    </span>
  </div>
</template>

<style scoped>
.statusbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  font-size: 12px;
  color: var(--hm-muted);
  border-bottom: 1px solid rgba(100, 116, 139, 0.25);
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.dot.ok {
  background: #22c55e;
}
.dot.warn {
  background: #eab308;
}
.dot.bad {
  background: var(--hm-danger);
}
</style>
