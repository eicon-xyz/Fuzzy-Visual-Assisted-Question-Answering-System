<template>
  <div>
    <el-card header="失败归因分析" style="margin-bottom: 16px">
      <el-row :gutter="16">
        <el-col :span="12">
          <div ref="barChart" style="height: 320px; cursor: pointer" title="点击柱状图按类型筛选列表"></div>
        </el-col>
        <el-col :span="12">
          <div ref="trendChart" style="height: 320px"></div>
        </el-col>
      </el-row>
    </el-card>

    <!-- 失败列表 -->
    <el-card :header="`失败详情列表${filterType ? ' — 筛选: ' + filterType : ''}`">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>失败详情列表{{ filterType ? ' — ' + filterType : '' }}</span>
          <el-button v-if="filterType" text type="primary" @click="filterType = ''">清除筛选</el-button>
        </div>
      </template>

      <el-table :data="filteredData" stripe @row-click="showDetail" style="cursor: pointer">
        <el-table-column prop="id" label="ID" width="100" />
        <el-table-column prop="task_name" label="任务" />
        <el-table-column prop="error_type" label="失败类型" width="120">
          <template #default="{ row }">
            <el-tag size="small" type="danger">{{ row.error_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="failed_step" label="失败步骤" width="80" />
        <el-table-column prop="route" label="路径" width="80" />
        <el-table-column prop="timestamp" label="时间" width="180" />
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button text type="primary" @click.stop="showDetail(row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-if="filteredData.length > 0"
        style="margin-top: 16px; justify-content: center"
        :total="filteredData.length"
        :page-size="pageSize"
        layout="prev, pager, next"
        v-model:current-page="currentPage"
      />
    </el-card>

    <!-- 详情滑出面板 -->
    <el-drawer v-model="drawerVisible" title="失败详情" size="480px" direction="rtl">
      <template v-if="selectedItem">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="任务 ID">{{ selectedItem.id }}</el-descriptions-item>
          <el-descriptions-item label="任务名称">{{ selectedItem.task_name }}</el-descriptions-item>
          <el-descriptions-item label="失败类型">
            <el-tag type="danger" size="small">{{ selectedItem.error_type }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="失败步骤">第 {{ selectedItem.failed_step }} 步</el-descriptions-item>
          <el-descriptions-item label="错误摘要">{{ selectedItem.error_summary }}</el-descriptions-item>
          <el-descriptions-item label="处理路径">{{ selectedItem.route }}</el-descriptions-item>
          <el-descriptions-item label="发生时间">{{ selectedItem.timestamp }}</el-descriptions-item>
        </el-descriptions>

        <!-- LLM 快照折叠区 -->
        <el-collapse style="margin-top: 16px">
          <el-collapse-item title="📸 LLM 输入/输出快照" name="llm_snapshot">
            <el-card shadow="never" style="margin-bottom: 8px">
              <template #header>
                <span style="font-weight: 600">LLM 请求快照</span>
              </template>
              <el-descriptions :column="1" size="small">
                <el-descriptions-item label="模型">{{ selectedItem.llm_input?.model || 'gpt-4o' }}</el-descriptions-item>
                <el-descriptions-item label="Temperature">{{ selectedItem.llm_input?.temperature || 0.7 }}</el-descriptions-item>
                <el-descriptions-item label="Max Tokens">{{ selectedItem.llm_input?.max_tokens || 4096 }}</el-descriptions-item>
              </el-descriptions>
              <div style="margin-top: 8px">
                <p style="font-size: 12px; color: #909399; margin-bottom: 4px">System Prompt (脱敏后):</p>
                <el-input
                  type="textarea" :rows="4" readonly
                  :model-value="selectedItem.llm_input?.system_prompt || defaultSystemPrompt"
                />
              </div>
            </el-card>

            <el-card shadow="never">
              <template #header>
                <span style="font-weight: 600">LLM 响应快照</span>
              </template>
              <el-descriptions :column="1" size="small">
                <el-descriptions-item label="Finish Reason">
                  <el-tag :type="selectedItem.llm_output?.finish_reason === 'error' ? 'danger' : 'success'" size="small">
                    {{ selectedItem.llm_output?.finish_reason || 'error' }}
                  </el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="错误详情">{{ selectedItem.llm_output?.error_detail || 'timeout waiting for element #file_list' }}</el-descriptions-item>
              </el-descriptions>
              <div style="margin-top: 8px">
                <p style="font-size: 12px; color: #909399; margin-bottom: 4px">Blueprint 输出 (脱敏后):</p>
                <el-input
                  type="textarea" :rows="4" readonly
                  :model-value="selectedItem.llm_output?.blueprint || defaultBlueprint"
                />
              </div>
            </el-card>
          </el-collapse-item>

          <el-collapse-item title="🔍 指纹比对详情" name="fingerprint">
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="期望 App">{{ selectedItem.expected_fingerprint?.app || 'vscode' }}</el-descriptions-item>
              <el-descriptions-item label="实际 App">{{ selectedItem.actual_fingerprint?.app || 'vscode' }}</el-descriptions-item>
              <el-descriptions-item label="期望 Verb">{{ selectedItem.expected_fingerprint?.verb || 'write' }}</el-descriptions-item>
              <el-descriptions-item label="实际 Verb">
                <span style="color: #f56c6c">{{ selectedItem.actual_fingerprint?.verb || 'delete' }}</span>
              </el-descriptions-item>
              <el-descriptions-item label="不匹配字段">
                <el-tag v-for="f in (selectedItem.mismatch_fields || ['verb'])" :key="f" type="warning" size="small" style="margin-right: 4px">{{ f }}</el-tag>
              </el-descriptions-item>
            </el-descriptions>
          </el-collapse-item>
        </el-collapse>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, computed } from 'vue'
import * as echarts from 'echarts'

const barChart = ref(null)
const trendChart = ref(null)
const drawerVisible = ref(false)
const selectedItem = ref(null)
const filterType = ref('')
const currentPage = ref(1)
const pageSize = ref(20)

// LLM 快照默认文本（避免模板内嵌含花括号的字符串）
const defaultSystemPrompt = '你是一个桌面操作指引助手... [已脱敏]'
const defaultBlueprint = '{ "steps": [...] } [已脱敏]'

// ── 完整 Mock 数据（含 LLM 快照）──

const allFailures = [
  {
    id: 'fail_001', task_name: '打开 VSCode 编辑文件', error_type: '蓝图不匹配',
    failed_step: 2, route: 'L3', timestamp: '2026-06-29 14:22:10',
    error_summary: '蓝图 verb 不匹配：期望 write，实际 delete',
    llm_input: { model: 'gpt-4o', temperature: 0.7, max_tokens: 4096, system_prompt: '你是一个桌面操作指引助手...[已脱敏]' },
    llm_output: { blueprint: '{ "steps": [{"action":"编辑文件","target":"~3"},...] }', finish_reason: 'error', error_detail: 'timeout waiting for element #file_list' },
    expected_fingerprint: { app: 'vscode', action: 'edit_file', verb: 'write' },
    actual_fingerprint: { app: 'vscode', action: 'edit_file', verb: 'delete' },
    mismatch_fields: ['verb'],
  },
  {
    id: 'fail_002', task_name: '安装微信客户端', error_type: 'LLM 超时',
    failed_step: 1, route: 'L3', timestamp: '2026-06-29 13:15:42',
    error_summary: 'DeepSeek API 30s 超时未响应',
    llm_input: { model: 'deepseek-chat', temperature: 0.3, max_tokens: 1000, system_prompt: '你是一个桌面操作指引助手...[已脱敏]' },
    llm_output: { blueprint: '', finish_reason: 'error', error_detail: 'connection timeout after 30s' },
    expected_fingerprint: null, actual_fingerprint: null, mismatch_fields: [],
  },
  {
    id: 'fail_003', task_name: '查找打印机设置', error_type: '解析错误',
    failed_step: 1, route: 'L2', timestamp: '2026-06-29 12:08:33',
    error_summary: 'LLM 返回非 JSON 内容，解析失败',
    llm_input: { model: 'qwen-vl-max', temperature: 0.5, max_tokens: 2048, system_prompt: '请严格按 JSON 格式返回...[已脱敏]' },
    llm_output: { blueprint: '抱歉，我无法理解您的问题...（非 JSON）', finish_reason: 'parse_error', error_detail: 'JSONDecodeError at line 1 column 1' },
    expected_fingerprint: null, actual_fingerprint: null, mismatch_fields: [],
  },
  {
    id: 'fail_004', task_name: '自动抢票脚本', error_type: '红线拦截',
    failed_step: 0, route: 'L2', timestamp: '2026-06-29 11:45:00',
    error_summary: '检测到自动点击关键词 → 拦截',
    llm_input: null, llm_output: null,
    expected_fingerprint: null, actual_fingerprint: null, mismatch_fields: [],
  },
  {
    id: 'fail_005', task_name: '修改注册表键值', error_type: '用户中止',
    failed_step: 3, route: 'L3', timestamp: '2026-06-29 10:20:18',
    error_summary: '用户在第 3 步手动终止任务',
    llm_input: { model: 'gpt-4o', temperature: 0.7, max_tokens: 4096, system_prompt: '你是一个桌面操作指引助手...[已脱敏]' },
    llm_output: { blueprint: '{ "steps": [...] }', finish_reason: 'user_abort', error_detail: 'user clicked terminate button' },
    expected_fingerprint: { app: 'regedit', action: 'modify_key', verb: 'set' },
    actual_fingerprint: { app: 'regedit', action: 'modify_key', verb: 'cancel' },
    mismatch_fields: ['verb'],
  },
]

// 筛选后的数据
const filteredData = computed(() => {
  if (!filterType.value) return allFailures
  return allFailures.filter((f) => f.error_type === filterType.value)
})

// 点击行 → 显示详情面板
function showDetail(row) {
  selectedItem.value = row
  drawerVisible.value = true
}

// ── 图表 ──

onMounted(async () => {
  await nextTick()

  const categories = ['蓝图不匹配', 'LLM超时', '解析错误', '红线拦截', '用户中止']
  const values = [48, 32, 28, 25, 23]

  // 柱状图（点击触发筛选）
  if (barChart.value) {
    const c = echarts.init(barChart.value)
    c.setOption({
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', data: categories },
      yAxis: { type: 'value' },
      series: [{
        type: 'bar', data: values,
        itemStyle: { color: '#f56c6c', borderRadius: [4, 4, 0, 0] },
      }],
    })
    c.on('click', (params) => {
      filterType.value = params.name
    })
  }

  // 趋势折线图
  if (trendChart.value) {
    const c = echarts.init(trendChart.value)
    const hours = Array.from({ length: 24 }, (_, i) => `${i}:00`)
    c.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 40, right: 20, top: 20, bottom: 30 },
      xAxis: { type: 'category', data: hours, axisLabel: { interval: 3 } },
      yAxis: { type: 'value' },
      series: [{
        type: 'line', smooth: true,
        data: hours.map(() => Math.floor(Math.random() * 25 + 5)),
        areaStyle: { opacity: 0.1, color: '#f56c6c' },
        lineStyle: { color: '#f56c6c' },
      }],
    })
  }
})
</script>
