<template>
  <div>
    <el-card header="失败归因分析" style="margin-bottom: 16px">
      <!-- 柱状图 + 折线图 -->
      <el-row :gutter="16">
        <el-col :span="12">
          <div ref="barChart" style="height: 320px"></div>
        </el-col>
        <el-col :span="12">
          <div ref="trendChart" style="height: 320px"></div>
        </el-col>
      </el-row>
    </el-card>

    <!-- 失败列表 -->
    <el-card header="失败详情列表">
      <el-table :data="tableData" stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="100" />
        <el-table-column prop="task_name" label="任务" />
        <el-table-column prop="error_type" label="失败类型" />
        <el-table-column prop="route" label="路径" width="80" />
        <el-table-column prop="timestamp" label="时间" width="180" />
        <el-table-column label="操作" width="100">
          <template #default>
            <el-button text type="primary">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        style="margin-top: 16px; justify-content: center"
        :total="156"
        :page-size="20"
        layout="prev, pager, next"
      />
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import * as echarts from 'echarts'

const barChart = ref(null)
const trendChart = ref(null)

const tableData = ref([
  { id: 'fail_001', task_name: '打开 VSCode 编辑文件', error_type: '蓝图不匹配', route: 'L3', timestamp: '2026-06-29 14:22:10' },
  { id: 'fail_002', task_name: '安装微信客户端', error_type: 'LLM 超时', route: 'L3', timestamp: '2026-06-29 13:15:42' },
  { id: 'fail_003', task_name: '查找打印机设置', error_type: '解析错误', route: 'L2', timestamp: '2026-06-29 12:08:33' },
  { id: 'fail_004', task_name: '自动抢票脚本', error_type: '红线拦截', route: 'L2', timestamp: '2026-06-29 11:45:00' },
  { id: 'fail_005', task_name: '修改注册表键值', error_type: '用户中止', route: 'L3', timestamp: '2026-06-29 10:20:18' },
])

onMounted(async () => {
  await nextTick()

  // 柱状图
  if (barChart.value) {
    const c = echarts.init(barChart.value)
    c.setOption({
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', data: ['蓝图不匹配', 'LLM超时', '解析错误', '红线拦截', '用户中止'] },
      yAxis: { type: 'value' },
      series: [{ type: 'bar', data: [48, 32, 28, 25, 23], itemStyle: { color: '#f56c6c' } }],
    })
  }

  // 趋势
  if (trendChart.value) {
    const c = echarts.init(trendChart.value)
    const hours = Array.from({ length: 24 }, (_, i) => `${i}:00`)
    c.setOption({
      tooltip: { trigger: 'axis' },
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
