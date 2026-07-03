<template>
  <div>
    <el-card header="系统配置" style="margin-bottom: 16px">
      <el-form :model="config" label-width="180px" style="max-width: 660px">
        <el-divider content-position="left">AI 推理</el-divider>
        <el-form-item label="LLM Provider">
          <el-select v-model="config.llm_provider">
            <el-option label="DeepSeek" value="deepseek" />
            <el-option label="OpenAI" value="openai" />
            <el-option label="Claude" value="claude" />
            <el-option label="OpenRouter" value="openrouter" />
            <el-option label="Ollama" value="ollama" />
          </el-select>
        </el-form-item>
        <el-form-item label="LLM 端点">
          <el-input v-model="config.llm_api_endpoint" />
        </el-form-item>
        <el-form-item label="LLM 模型">
          <el-input v-model="config.llm_model" placeholder="deepseek-v4-flash" />
        </el-form-item>
        <el-form-item label="Temperature">
          <el-slider v-model="config.llm_temperature" :min="0" :max="2" :step="0.1" show-input />
        </el-form-item>
        <el-form-item label="Max Tokens">
          <el-input-number v-model="config.llm_max_tokens" :min="256" :max="32768" :step="256" />
        </el-form-item>
        <el-form-item label="置信度阈值">
          <el-slider v-model="config.confidence_threshold" :min="50" :max="100" show-input />
        </el-form-item>
        <el-form-item label="模板相似度阈值">
          <el-slider v-model="config.template_similarity_threshold" :min="50" :max="100" show-input />
        </el-form-item>
        <el-form-item label="步骤评估 (P1)">
          <el-switch v-model="config.evaluate_steps" />
        </el-form-item>
        <el-form-item label="信任级别 (P1)">
          <el-select v-model="config.trust_level">
            <el-option label="保守" value="conservative" />
            <el-option label="平衡" value="balanced" />
            <el-option label="激进" value="aggressive" />
          </el-select>
        </el-form-item>

        <el-divider content-position="left">任务控制</el-divider>
        <el-form-item label="最大蓝图步骤数">
          <el-input-number v-model="config.max_blueprint_steps" :min="1" :max="30" />
        </el-form-item>
        <el-form-item label="配置拉取间隔 (分钟)">
          <el-input-number v-model="config.config_pull_interval_min" :min="5" :max="1440" />
        </el-form-item>
        <el-form-item label="审计批量大小">
          <el-input-number v-model="config.audit_batch_size" :min="1" :max="100" />
        </el-form-item>

        <el-divider content-position="left">语音</el-divider>
        <el-form-item label="离线 TTS 引擎">
          <el-select v-model="config.offline_tts_engine">
            <el-option label="pyttsx3" value="pyttsx3" />
            <el-option label="azure" value="azure" />
            <el-option label="baidu" value="baidu" />
          </el-select>
        </el-form-item>

        <el-divider content-position="left">路由规则</el-divider>
        <el-form-item label="路由规则 JSON">
          <el-input v-model="routingRulesJson" type="textarea" :rows="6" />
          <el-button text type="primary" size="small" @click="formatJson" style="margin-top: 4px">格式化</el-button>
          <el-button text size="small" @click="validateJson" style="margin-top: 4px; margin-left: 4px">校验</el-button>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="deploy">热部署</el-button>
          <el-button @click="resetConfig">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 部署操作日志 -->
    <el-card header="部署操作日志">
      <el-table :data="deployLogs" stripe size="small">
        <el-table-column prop="operator" label="操作人" width="180" />
        <el-table-column prop="action" label="操作" width="100">
          <template #default="{ row }">
            <el-tag :type="row.action === 'deploy' ? 'success' : 'warning'" size="small">
              {{ row.action === 'deploy' ? '部署' : '回滚' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="version" label="版本" width="100" />
        <el-table-column prop="affected" label="影响客户端" width="100" />
        <el-table-column prop="timestamp" label="时间" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { fetchConfigCurrent, deployConfig, fetchDeployLogs } from '../api/admin'

const config = reactive({
  llm_provider: 'deepseek',
  llm_api_endpoint: 'https://api.deepseek.com',
  llm_model: 'deepseek-v4-flash',
  llm_temperature: 0.3,
  llm_max_tokens: 4096,
  confidence_threshold: 80,
  template_similarity_threshold: 90,
  evaluate_steps: false,
  trust_level: 'balanced',
  max_blueprint_steps: 15,
  config_pull_interval_min: 30,
  audit_batch_size: 10,
  offline_tts_engine: 'pyttsx3',
})

const routingRulesJson = ref(JSON.stringify({
  length_weight: 0.3, verb_weight: 8, cross_app_bonus: 10,
  threshold_score: 30, custom_keywords: ['安装', '配置', '设置'],
}, null, 2))

const deployLogs = ref([])

onMounted(async () => {
  try {
    const data = await fetchConfigCurrent()
    if (data?.config) Object.assign(config, data.config)
    if (data?.config?.routing_rules) {
      routingRulesJson.value = JSON.stringify(data.config.routing_rules, null, 2)
    }
  } catch {}
  try {
    const logs = await fetchDeployLogs()
    deployLogs.value = logs?.logs || []
  } catch {}
})

function formatJson() {
  try {
    routingRulesJson.value = JSON.stringify(JSON.parse(routingRulesJson.value), null, 2)
    ElMessage.success('格式化成功')
  } catch {
    ElMessage.error('JSON 格式错误，无法格式化')
  }
}

function validateJson() {
  try {
    JSON.parse(routingRulesJson.value)
    ElMessage.success('JSON 校验通过')
  } catch {
    ElMessage.error('JSON 格式不合法')
  }
}

async function deploy() {
  // 先校验 JSON
  try { JSON.parse(routingRulesJson.value) } catch {
    ElMessage.error('路由规则 JSON 格式不合法，请先修正')
    return
  }
  ElMessageBox.confirm(
    `确认热部署配置到全部在线客户端？`,
    '二次确认',
    { confirmButtonText: '确认部署', type: 'warning' },
  ).then(async () => {
    const result = await deployConfig({
      ...config,
      routing_rules: JSON.parse(routingRulesJson.value),
    })
    ElMessage.success(`部署成功！版本 ${result.version}，${result.affected_clients} 个客户端已更新`)
    // 刷新日志
    const logs = await fetchDeployLogs()
    deployLogs.value = logs?.logs || []
  }).catch(() => {})
}

function resetConfig() {
  ElMessage.info('已重置为服务端当前配置')
}
</script>
