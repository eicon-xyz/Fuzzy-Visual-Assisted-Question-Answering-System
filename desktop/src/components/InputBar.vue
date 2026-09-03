<script setup lang="ts">
import { ref } from 'vue'
import { useTaskStore } from '../stores/task'

const store = useTaskStore()
const input = ref('')
const emit = defineEmits<{ submit: [query: string]; cancel: [] }>()

function send(): void {
  const q = input.value.trim()
  if (!q || store.busy) return
  input.value = ''
  emit('submit', q)
}
</script>

<template>
  <footer class="inputbar">
    <textarea
      v-model="input"
      rows="2"
      :disabled="store.busy"
      placeholder="用一句话描述要 HAJIMI 自动完成的操作（Enter 发送 / Shift+Enter 换行）"
      @keydown.enter.exact.prevent="send"
    />
    <div class="btns">
      <button v-if="store.busy" class="stop" @click="emit('cancel')">停止</button>
      <button v-else class="send" :disabled="!input.trim()" @click="send">执行</button>
    </div>
  </footer>
</template>

<style scoped>
.inputbar {
  display: flex;
  gap: 8px;
  padding: 10px 12px;
  border-top: 1px solid rgba(100, 116, 139, 0.25);
  background: rgba(30, 41, 59, 0.6);
}
textarea {
  flex: 1;
  resize: none;
  background: var(--hm-bg);
  color: var(--hm-text);
  border: 1px solid rgba(100, 116, 139, 0.35);
  border-radius: 8px;
  padding: 8px 10px;
  font: inherit;
}
textarea:focus {
  outline: none;
  border-color: var(--hm-accent);
}
.btns {
  display: flex;
  align-items: flex-end;
}
button {
  height: 34px;
  padding: 0 16px;
  border-radius: 8px;
  border: none;
  cursor: pointer;
  font-weight: 600;
}
.send {
  background: var(--hm-accent);
  color: #1e1b34;
}
.send:disabled {
  opacity: 0.4;
  cursor: default;
}
.stop {
  background: var(--hm-danger);
  color: #fff;
}
</style>
