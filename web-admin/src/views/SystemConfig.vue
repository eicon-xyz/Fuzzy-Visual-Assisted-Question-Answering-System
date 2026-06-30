<template>
  <div>
    <el-card header="系统配置" style="margin-bottom: 16px">
      <el-form :model="config" label-width="160px" style="max-width: 600px">
        <el-form-item label="置信度阈值">
          <el-slider v-model="config.confidence_threshold" :min="50" :max="100" show-input />
        </el-form-item>
        <el-form-item label="最大蓝图步骤数">
          <el-input-number v-model="config.max_blueprint_steps" :min="1" :max="30" />
        </el-form-item>
        <el-form-item label="Token 限制">
          <el-input-number v-model="config.token_limit" :min="1000" :max="32000" :step="1000" />
        </el-form-item>
        <el-form-item label="LLM 模型">
          <el-select v-model="config.llm_model">
            <el-option label="deepseek-chat" value="deepseek-chat" />
            <el-option label="gpt-4o" value="gpt-4o" />
            <el-option label="qwen-vl-max" value="qwen-vl-max" />
          </el-select>
        </el-form-item>
        <el-form-item label="配置拉取间隔 (分钟)">
          <el-input-number v-model="config.config_pull_interval_min" :min="5" :max="1440" />
        </el-form-item>
        <el-form-item label="审计批量大小">
          <el-input-number v-model="config.audit_batch_size" :min="1" :max="100" />
        </el-form-item>
        <el-form-item label="路由规则 JSON">
          <el-input v-model="config.routing_rules_json" type="textarea" :rows="4" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="deploy">热部署</el-button>
          <el-button @click="reset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const config = reactive({
  confidence_threshold: 80,
  max_blueprint_steps: 15,
  token_limit: 8000,
  llm_model: 'deepseek-chat',
  config_pull_interval_min: 30,
  audit_batch_size: 10,
  routing_rules_json: JSON.stringify({
    length_weight: 0.3,
    verb_weight: 8,
    cross_app_bonus: 10,
    threshold_score: 30,
  }, null, 2),
})

function deploy() {
  ElMessageBox.confirm('确认热部署此配置到所有客户端？', '二次确认', {
    confirmButtonText: '确认部署',
    type: 'warning',
  }).then(() => {
    ElMessage.success('配置已部署至 42 个在线客户端')
  }).catch(() => {})
}

function reset() {
  ElMessage.info('已重置为服务端当前配置')
}
</script>
