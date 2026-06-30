<template>
  <div>
    <el-card header="数据流拓扑" style="margin-bottom: 16px">
      <div ref="topoChart" style="height: 400px"></div>
    </el-card>

    <el-row :gutter="16">
      <el-col :span="12">
        <el-card header="API QPS / 成功率">
          <div ref="qpsChart" style="height: 280px"></div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card header="客户端版本分布">
          <div ref="versionChart" style="height: 280px"></div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import * as echarts from 'echarts'

const topoChart = ref(null)
const qpsChart = ref(null)
const versionChart = ref(null)

onMounted(async () => {
  await nextTick()

  // 拓扑图（力导向）
  if (topoChart.value) {
    const c = echarts.init(topoChart.value)
    c.setOption({
      tooltip: {},
      series: [{
        type: 'graph',
        layout: 'force',
        roam: true,
        label: { show: true, fontSize: 13 },
        force: { repulsion: 400, edgeLength: 200 },
        data: [
          { name: '客户端 #c12a', category: 0, symbolSize: 30 },
          { name: '客户端 #d07f', category: 0, symbolSize: 30 },
          { name: '客户端 #e3b8', category: 0, symbolSize: 30 },
          { name: 'HAJIMI Gateway', category: 1, symbolSize: 50 },
          { name: 'PostgreSQL', category: 2, symbolSize: 40 },
          { name: 'LLM API (GPT-4)', category: 3, symbolSize: 40 },
        ],
        categories: [
          { name: '客户端', itemStyle: { color: '#67c23a' } },
          { name: '网关', itemStyle: { color: '#409EFF' } },
          { name: '数据库', itemStyle: { color: '#e6a23c' } },
          { name: '外部服务', itemStyle: { color: '#909399' } },
        ],
        links: [
          { source: '客户端 #c12a', target: 'HAJIMI Gateway' },
          { source: '客户端 #d07f', target: 'HAJIMI Gateway' },
          { source: '客户端 #e3b8', target: 'HAJIMI Gateway' },
          { source: 'HAJIMI Gateway', target: 'PostgreSQL' },
          { source: 'HAJIMI Gateway', target: 'LLM API (GPT-4)' },
        ],
      }],
    })
  }

  // QPS
  if (qpsChart.value) {
    const c = echarts.init(qpsChart.value)
    const times = Array.from({ length: 24 }, (_, i) => `${i}:00`)
    c.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 60, right: 60, top: 20, bottom: 30 },
      xAxis: { type: 'category', data: times, axisLabel: { interval: 3 } },
      yAxis: [
        { type: 'value', name: 'QPS' },
        { type: 'value', name: '%', min: 95, max: 100 },
      ],
      series: [
        { type: 'bar', data: times.map(() => 20 + Math.floor(Math.random() * 40)), yAxisIndex: 0, itemStyle: { color: '#409EFF' } },
        { type: 'line', data: times.map(() => 98 + Math.random() * 2), yAxisIndex: 1, lineStyle: { color: '#67c23a' } },
      ],
    })
  }

  // 版本饼图
  if (versionChart.value) {
    const c = echarts.init(versionChart.value)
    c.setOption({
      tooltip: { trigger: 'item' },
      series: [{
        type: 'pie',
        radius: '70%',
        data: [
          { value: 34, name: 'v2.1.0' },
          { value: 6, name: 'v2.0.5' },
          { value: 2, name: 'v1.9.0' },
        ],
        label: { formatter: '{b}\n{d}%' },
      }],
    })
  }
})
</script>
