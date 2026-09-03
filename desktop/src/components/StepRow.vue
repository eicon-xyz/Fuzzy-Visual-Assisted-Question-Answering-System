<script setup lang="ts">
import { computed } from 'vue'
import type { StepRow } from '../stores/task'

const props = defineProps<{ step: StepRow }>()

const statusLabel = computed(
  () =>
    ({
      pending: '待执行',
      executing: '执行中',
      done: '完成',
      failed: '失败',
      blocked: '受阻'
    })[props.step.status]
)
</script>

<template>
  <li class="step" :data-status="step.status">
    <div class="head">
      <span class="dot" />
      <span class="idx">步骤 {{ step.stepIndex }}</span>
      <span class="badge" :class="step.status">{{ statusLabel }}</span>
    </div>
    <div v-if="step.instruction" class="instruction">{{ step.instruction }}</div>
    <div v-if="step.summary" class="summary">{{ step.summary }}</div>
    <div v-if="step.reason" class="reason">{{ step.reason }}</div>
    <div v-if="step.evidence" class="evidence" title="done 独立证据（P0-0.7）">
      证据：{{ step.evidence }}
    </div>
    <details v-if="step.tools.length" class="tools">
      <summary>工具调用 {{ step.tools.length }}</summary>
      <div v-for="(t, i) in step.tools" :key="i" class="tool" :class="{ err: t.success === false }">
        <code>{{ t.tool }}</code>
        <span v-if="t.summary">{{ t.summary }}</span>
        <span v-if="t.error" class="terr">{{ t.error }}{{ t.errorCode ? ` [${t.errorCode}]` : '' }}</span>
      </div>
    </details>
    <img v-if="step.screenshot" :src="step.screenshot" class="shot" alt="屏幕快照" />
  </li>
</template>

<style scoped>
.step {
  border: 1px solid rgba(100, 116, 139, 0.25);
  border-radius: 10px;
  padding: 10px 12px;
  margin-bottom: 10px;
  background: rgba(30, 41, 59, 0.5);
}
.step[data-status='executing'] {
  border-color: var(--hm-accent);
}
.step[data-status='failed'],
.step[data-status='blocked'] {
  border-color: var(--hm-danger);
}
.head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--hm-muted);
}
.step[data-status='done'] .dot {
  background: #22c55e;
}
.step[data-status='executing'] .dot {
  background: var(--hm-accent);
  animation: pulse 1s infinite;
}
@keyframes pulse {
  50% {
    opacity: 0.35;
  }
}
.idx {
  font-size: 12px;
  color: var(--hm-muted);
}
.badge {
  margin-left: auto;
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 999px;
  border: 1px solid var(--hm-muted);
  color: var(--hm-muted);
}
.badge.done {
  color: #22c55e;
  border-color: #22c55e;
}
.badge.executing {
  color: var(--hm-accent);
  border-color: var(--hm-accent);
}
.badge.failed,
.badge.blocked {
  color: var(--hm-danger);
  border-color: var(--hm-danger);
}
.instruction {
  margin-top: 6px;
  font-size: 13px;
}
.summary {
  margin-top: 4px;
  font-size: 12px;
  color: #a7f3d0;
}
.reason {
  margin-top: 4px;
  font-size: 12px;
  color: #fecaca;
}
.evidence {
  margin-top: 4px;
  font-size: 11px;
  color: var(--hm-muted);
  font-family: Consolas, monospace;
}
.tools {
  margin-top: 6px;
  font-size: 11px;
  color: var(--hm-muted);
}
.tools summary {
  cursor: pointer;
}
.tool {
  margin-top: 3px;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.tool.err .terr {
  color: var(--hm-danger);
}
.shot {
  margin-top: 8px;
  width: 100%;
  border-radius: 8px;
  border: 1px solid rgba(100, 116, 139, 0.3);
}
</style>
