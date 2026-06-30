<template>
  <div>
    <!-- KPI 卡片 -->
    <el-row :gutter="16" style="margin-bottom: 16px">
      <el-col :span="6" v-for="card in kpiCards" :key="card.label">
        <el-card shadow="hover" style="text-align: center; cursor: pointer">
          <p style="color: #909399; font-size: 14px">{{ card.label }}</p>
          <p :style="{ fontSize: '28px', fontWeight: 700, color: card.color, margin: '8px 0' }">
            {{ card.value }}
          </p>
          <p :style="{ fontSize: '12px', color: card.trend > 0 ? '#67c23a' : '#f56c6c' }">
            {{ card.trend > 0 ? '↑' : '↓' }} {{ Math.abs(card.trend) }}% vs 昨日
          </p>
        </el-card>
      </el-col>
    </el-row>

    <!-- 双饼图 -->
    <el-row :gutter="16" style="margin-bottom: 16px">
      <el-col :span="12">
        <el-card header="反馈分布">
          <div ref="feedbackChart" style="height: 300px"></div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card header="L2 / L3 路径占比">
          <div ref="routeChart" style="height: 300px"></div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 双折线图 -->
    <el-row :gutter="16">
      <el-col :span="12">
        <el-card header="24h 事务量趋势">
          <div ref="volumeChart" style="height: 300px"></div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card header="24h 响应时长趋势 (秒)">
          <div ref="latencyChart" style="height: 300px"></div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import * as echarts from 'echarts'

// ── KPI 数据 ──
const kpiCards = ref([
  { label: '今日事务量', value: '1,247', trend: 12, color: '#409EFF' },
  { label: '在线客户端', value: '42', trend: 8, color: '#67C23A' },
  { label: '有用反馈率', value: '89%', trend: 3, color: '#E6A23C' },
  { label: '整体失败率', value: '3.2%', trend: -5, color: '#F56C6C' },
])

// ── 图表 refs ──
const feedbackChart = ref(null)
const routeChart = ref(null)
const volumeChart = ref(null)
const latencyChart = ref(null)

onMounted(async () => {
  await nextTick()
  renderFeedbackPie()
  renderRoutePie()
  renderVolumeLine()
  renderLatencyLine()
})

// ── 饼图：反馈分布 ──
function renderFeedbackPie() {
  if (!feedbackChart.value) return
  const chart = echarts.init(feedbackChart.value)
  chart.setOption({
    tooltip: { trigger: 'item' },
    color: ['#67c23a', '#f56c6c', '#e6a23c'],
    series: [{
      type: 'pie',
      radius: ['45%', '75%'],
      data: [
        { value: 89, name: '有用' },
        { value: 6, name: '无用' },
        { value: 5, name: '中立' },
      ],
      label: { formatter: '{b}\n{d}%' },
    }],
  })
}

// ── 饼图：L2/L3 占比 ──
function renderRoutePie() {
  if (!routeChart.value) return
  const chart = echarts.init(routeChart.value)
  chart.setOption({
    tooltip: { trigger: 'item' },
    color: ['#409EFF', '#e6a23c'],
    series: [{
      type: 'pie',
      radius: ['45%', '75%'],
      data: [
        { value: 70, name: 'L2 快路径' },
        { value: 30, name: 'L3 慢路径' },
      ],
      label: { formatter: '{b}\n{d}%' },
    }],
  })
}

// ── 折线图：事务量 ──
function renderVolumeLine() {
  if (!volumeChart.value) return
  const hours = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, '0') + ':00')
  const values = hours.map((h) => {
    const hour = parseInt(h)
    return hour >= 8 && hour < 18 ? 40 + Math.floor(Math.random() * 80) : 5 + Math.floor(Math.random() * 20)
  })
  const chart = echarts.init(volumeChart.value)
  chart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 20, top: 20, bottom: 30 },
    xAxis: { type: 'category', data: hours, axisLabel: { interval: 3 } },
    yAxis: { type: 'value' },
    series: [{
      type: 'line',
      data: values,
      smooth: true,
      areaStyle: { opacity: 0.15 },
      lineStyle: { color: '#409EFF' },
      itemStyle: { color: '#409EFF' },
    }],
  })
}

// ── 折线图：响应时长 ──
function renderLatencyLine() {
  if (!latencyChart.value) return
  const hours = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, '0') + ':00')
  const l2 = hours.map(() => 1.5 + Math.random() * 1.5)
  const l3 = hours.map(() => 4 + Math.random() * 6)
  const chart = echarts.init(latencyChart.value)
  chart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 20, top: 20, bottom: 30 },
    xAxis: { type: 'category', data: hours, axisLabel: { interval: 3 } },
    yAxis: { type: 'value', name: '秒' },
    series: [
      {
        type: 'line', name: 'L2', data: l2, smooth: true,
        lineStyle: { color: '#67c23a' }, itemStyle: { color: '#67c23a' },
        markLine: { silent: true, data: [{ yAxis: 3, label: { formatter: 'L2阈值 3s' }, lineStyle: { type: 'dashed', color: '#e6a23c' } }] },
      },
      {
        type: 'line', name: 'L3', data: l3, smooth: true,
        lineStyle: { color: '#409EFF' }, itemStyle: { color: '#409EFF' },
        markLine: { silent: true, data: [{ yAxis: 10, label: { formatter: 'L3阈值 10s' }, lineStyle: { type: 'dashed', color: '#e6a23c' } }] },
      },
    ],
  })
}
</script>
