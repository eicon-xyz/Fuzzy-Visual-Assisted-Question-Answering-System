<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import type { SettingsSnapshot } from '../../types/ipc'

const emit = defineEmits<{ close: [] }>()

const s = reactive<Required<Pick<SettingsSnapshot, 'llm' | 'voice'>> & SettingsSnapshot>({
  llm: { base_url: '', api_key: '', model: 'deepseek-chat' },
  voice: {}
})
const loading = ref(true)
const saving = ref(false)
const note = ref('')

onMounted(async () => {
  const snap = await window.hajimi.settingsGet()
  Object.assign(s, snap)
  s.llm = { base_url: '', api_key: '', model: 'deepseek-chat', ...(snap.llm ?? {}) }
  s.voice = { ...(snap.voice ?? {}) }
  loading.value = false
})

async function save(): Promise<void> {
  saving.value = true
  note.value = ''
  const r = await window.hajimi.settingsSave({
    llm: { ...s.llm },
    voice: { tts_enabled: s.voice?.tts_enabled !== false },
    demo_key: s.demo_key
  })
  note.value = r.ok
    ? r.envSyncedTo
      ? `已保存，模型配置已同步 Sidecar .env 并重启生效`
      : '已保存（未找到 server_A/.env，仅本地存储）'
    : `保存失败：${r.error ?? ''}`
  saving.value = false
}

async function logout(): Promise<void> {
  await window.hajimi.authLogout()
  note.value = '已退出登录'
}
</script>

<template>
  <section class="settings">
    <header class="bar">
      <h2>系统设置</h2>
      <button class="back" @click="emit('close')">← 返回</button>
    </header>
    <div v-if="loading" class="hint">加载中…</div>
    <form v-else class="form" @submit.prevent="save">
      <fieldset>
        <legend>模型（LLM）</legend>
        <label>API Key
          <input v-model="s.llm!.api_key" type="password" placeholder="留空 = 沿用 server_A/.env 现值" autocomplete="off" />
        </label>
        <label>Base URL
          <input v-model="s.llm!.base_url" placeholder="https://api.deepseek.com" />
        </label>
        <label>模型名
          <input v-model="s.llm!.model" placeholder="deepseek-chat" />
        </label>
        <p class="hint">留空字段不会覆盖 Sidecar 已有配置（与 PyQt 端同一 .env、同一「空值不覆盖」语义）。保存后自动重启 Sidecar 生效。</p>
      </fieldset>
      <fieldset>
        <legend>语音播报</legend>
        <label class="row">
          <input v-model="s.voice!.tts_enabled" type="checkbox" />
          步骤完成 TTS 播报
        </label>
      </fieldset>
      <fieldset>
        <legend>账号</legend>
        <button type="button" class="ghost" @click="logout">退出登录</button>
      </fieldset>
      <div class="actions">
        <span class="note">{{ note }}</span>
        <button type="submit" class="primary" :disabled="saving">{{ saving ? '保存中…' : '保存设置' }}</button>
      </div>
    </form>
  </section>
</template>

<style scoped>
.settings {
  flex: 1;
  overflow-y: auto;
  padding: 12px 14px;
}
.bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
h2 {
  font-size: 15px;
  margin: 0;
}
.back {
  background: transparent;
  border: 1px solid var(--hm-muted);
  color: var(--hm-muted);
  border-radius: 6px;
  padding: 3px 10px;
  cursor: pointer;
  font-size: 12px;
}
fieldset {
  border: 1px solid rgba(100, 116, 139, 0.25);
  border-radius: 10px;
  margin: 0 0 12px;
  padding: 10px 12px;
}
legend {
  font-size: 12px;
  color: var(--hm-muted);
  padding: 0 6px;
}
label {
  display: block;
  font-size: 12px;
  color: var(--hm-muted);
  margin-bottom: 8px;
}
input:not([type='checkbox']) {
  display: block;
  width: 100%;
  margin-top: 3px;
  background: var(--hm-bg);
  color: var(--hm-text);
  border: 1px solid rgba(100, 116, 139, 0.35);
  border-radius: 6px;
  padding: 6px 8px;
  font: inherit;
}
.row {
  display: flex;
  gap: 8px;
  align-items: center;
}
.hint {
  font-size: 11px;
  color: var(--hm-muted);
  margin: 4px 0;
}
.actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
}
.note {
  font-size: 12px;
  color: #86efac;
}
.primary {
  background: var(--hm-accent);
  color: #1e1b34;
  border: none;
  border-radius: 8px;
  padding: 7px 18px;
  font-weight: 600;
  cursor: pointer;
}
.ghost {
  background: transparent;
  border: 1px solid var(--hm-muted);
  color: var(--hm-muted);
  border-radius: 6px;
  padding: 4px 12px;
  cursor: pointer;
}
</style>
