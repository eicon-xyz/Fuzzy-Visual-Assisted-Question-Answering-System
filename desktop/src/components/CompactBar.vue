<script setup lang="ts">
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useTaskStore } from '../stores/task'

const emit = defineEmits<{ submit: [query: string]; cancel: []; expand: [] }>()
const store = useTaskStore()
const { phase, busy } = storeToRefs(store)
const input = ref('')

const statusText = computed(
  () =>
    ({
      idle: '就绪',
      planning: '规划中…',
      running: 'L5 执行中…',
      done: '已完成',
      failed: '失败',
      cancelled: '已取消',
      blocked: '受阻'
    })[phase.value]
)

function send(): void {
  const q = input.value.trim()
  if (!q || busy.value) return
  input.value = ''
  emit('submit', q)
}
</script>

<template>
  <div class="compact">
    <span class="mark" @click="emit('expand')">✦</span>
    <span class="status" :class="phase">{{ statusText }}</span>
    <input
      v-model="input"
      class="ci"
      placeholder="Ask HAJIMI…"
      :disabled="busy"
      @keydown.enter.prevent="send"
    />
    <button v-if="busy" class="stop" @click="emit('cancel')">停止</button>
    <button v-else class="send" :disabled="!input.trim()" @click="send">执行</button>
  </div>
</template>

<style scoped>
.compact {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 100%;
  padding: 6px 10px;
  background: rgba(30, 41, 59, 0.92);
}
.mark {
  width: 32px;
  height: 32px;
  line-height: 32px;
  text-align: center;
  border-radius: 10px;
  background: linear-gradient(135deg, var(--hm-accent), #8b5cf6);
  color: #fff;
  cursor: pointer;
  -webkit-app-region: no-drag;
}
.status {
  font-size: 12px;
  color: var(--hm-muted);
  min-width: 64px;
}
.status.running,
.status.planning {
  color: var(--hm-accent);
}
.status.failed,
.status.blocked {
  color: var(--hm-danger);
}
.status.done {
  color: #86efac;
}
.ci {
  flex: 1;
  background: var(--hm-bg);
  color: var(--hm-text);
  border: 1px solid rgba(100, 116, 139, 0.35);
  border-radius: 8px;
  padding: 6px 10px;
  font: inherit;
}
button {
  border: none;
  border-radius: 8px;
  padding: 6px 12px;
  cursor: pointer;
  font-weight: 600;
}
.send {
  background: var(--hm-accent);
  color: #1e1b34;
}
.send:disabled {
  opacity: 0.4;
}
.stop {
  background: var(--hm-danger);
  color: #fff;
}
</style>
