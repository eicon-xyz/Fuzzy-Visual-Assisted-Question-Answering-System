<script setup lang="ts">
import { ref } from 'vue'

const emit = defineEmits<{ accept: [dontShowAgain: boolean]; decline: [] }>()
const dontShow = ref(true)
</script>

<template>
  <div class="mask">
    <div class="dlg">
      <h2>L5 自动执行 — 知情确认</h2>
      <p>
        您已选择 L5 自动执行模式。<br /><br />
        HAJIMI 将通过本机 Sidecar (server_A) 自动操作鼠标与键盘完成步骤。请确保屏幕无敏感内容，且可随时按
        「停止」终止任务。
      </p>
      <label class="dont">
        <input v-model="dontShow" type="checkbox" />
        不再提示
      </label>
      <div class="btns">
        <button class="decline" @click="emit('decline')">取消</button>
        <button class="accept" @click="emit('accept', dontShow)">同意并执行</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mask {
  position: fixed;
  inset: 0;
  background: rgba(2, 6, 23, 0.72);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
}
.dlg {
  width: min(90%, 380px);
  background: var(--hm-panel);
  border: 1px solid rgba(100, 116, 139, 0.4);
  border-radius: 12px;
  padding: 18px 20px;
}
h2 {
  font-size: 16px;
  margin: 0 0 10px;
}
p {
  font-size: 13px;
  line-height: 1.7;
  color: var(--hm-text);
  margin: 0 0 12px;
}
.dont {
  display: flex;
  gap: 6px;
  align-items: center;
  font-size: 12px;
  color: var(--hm-muted);
  margin-bottom: 14px;
}
.btns {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
button {
  padding: 6px 16px;
  border-radius: 8px;
  border: none;
  cursor: pointer;
  font-size: 13px;
}
.accept {
  background: var(--hm-accent);
  color: #1e1b34;
  font-weight: 600;
}
.decline {
  background: transparent;
  border: 1px solid var(--hm-muted);
  color: var(--hm-muted);
}
</style>
