<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useTaskStore } from '../stores/task'
import StepRowItem from './StepRow.vue'

const store = useTaskStore()
const { steps, phase, goal } = storeToRefs(store)
</script>

<template>
  <section class="timeline">
    <div v-if="goal" class="goal">目标：{{ goal }}</div>
    <div v-if="!steps.length" class="empty">
      {{ phase === 'planning' ? '规划中…' : '尚无执行中的步骤' }}
    </div>
    <ul>
      <StepRowItem v-for="s in steps" :key="s.stepIndex" :step="s" />
    </ul>
  </section>
</template>

<style scoped>
.timeline {
  flex: 1;
  overflow-y: auto;
  padding: 10px 12px;
}
.goal {
  font-size: 12px;
  color: var(--hm-muted);
  margin-bottom: 8px;
}
.empty {
  color: var(--hm-muted);
  font-size: 12px;
  text-align: center;
  margin-top: 30px;
}
ul {
  list-style: none;
  margin: 0;
  padding: 0;
}
</style>
