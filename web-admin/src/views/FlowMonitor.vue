<template>
  <div>
    <el-card header="数据流向（桑基图）" style="margin-bottom: 16px">
      <div ref="sankeyChart" style="height: 420px"></div>
    </el-card>

    <el-row :gutter="16">
      <el-col :span="12">
        <el-card header="接口 QPS & 成功率">
          <div ref="qpsChart" style="height: 300px"></div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card header="客户端版本分布">
          <div ref="versionChart" style="height: 300px"></div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { fetchFlowTopology, fetchFlowMetrics, fetchFlowVersions } from '../api/admin'

const sankeyChart = ref(null)
const qpsChart = ref(null)
const versionChart = ref(null)

onMounted(async () => {
  await nextTick()
  renderSankey()
  renderQpsChart()
  renderVersionChart()
})

async function renderSankey() {
  if (!sankeyChart.value) return
  const data = await fetchFlowTopology()

  // 桑基图：nodes → 不同层级，links → 流量
  const levels = { client: 0, server: 1, database: 2, external: 3 }
  const nodes = data.nodes.map(n => ({
    name: n.label, itemStyle: { color: { client: '#67c23a', server: '#409EFF', database: '#e6a23c', external: '#909399' }[n.type] },
  }))
  const links = data.links.map(l => ({
    source: data.nodes.find(n => n.id === l.source)?.label || l.source,
    target: data.nodes.find(n => n.id === l.target)?.label || l.target,
    value: l.qps,
    lineStyle: { color: l.status === 'high_load' ? '#f56c6c' : l.status === 'critical' ? '#ff0000' : '#a0cfff' },
  }))

  const c = echarts.init(sankeyChart.value)
  c.setOption({
    tooltip: { trigger: 'item', triggerOn: 'mousemove' },
    series: [{
      type: 'sankey', layout: 'none',
      emphasis: { focus: 'adjacency' },
      nodeAlign: 'left',
      data: nodes,
      links: links,
      label: { fontSize: 13 },
      lineStyle: { color: 'gradient', curveness: 0.5 },
    }],
  })
}

async function renderQpsChart() {
  if (!qpsChart.value) return
  const data = await fetchFlowMetrics()

  const c = echarts.init(qpsChart.value)
  c.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['QPS', '成功率'] },
    grid: { left: 60, right: 60, top: 40, bottom: 30 },
    xAxis: { type: 'category', data: data.data.map(d => d.time), axisLabel: { interval: 3 } },
    yAxis: [
      { type: 'value', name: 'QPS' },
      { type: 'value', name: '%', min: 95, max: 100 },
    ],
    series: [
      {
        name: 'QPS', type: 'bar',
        data: data.data.map(d => d.qps),
        itemStyle: { color: '#409EFF', borderRadius: [3, 3, 0, 0] },
        yAxisIndex: 0,
      },
      {
        name: '成功率', type: 'line',
        data: data.data.map(d => d.success_rate),
        itemStyle: { color: '#67c23a' },
        yAxisIndex: 1,
        markLine: {
          silent: true,
          data: [{ yAxis: 99, label: { formatter: '99%' }, lineStyle: { type: 'dashed', color: '#e6a23c' } }],
        },
      },
    ],
  })
}

async function renderVersionChart() {
  if (!versionChart.value) return
  const data = await fetchFlowVersions()

  const c = echarts.init(versionChart.value)
  c.setOption({
    tooltip: { trigger: 'item' },
    color: ['#409EFF', '#67c23a', '#e6a23c'],
    series: [{
      type: 'pie',
      radius: ['48%', '78%'],
      data: data.versions.map(v => ({ value: v.count, name: v.version })),
      label: { formatter: '{b}\n{d}% ({c} 台)' },
      emphasis: { label: { fontSize: 18, fontWeight: 'bold' } },
    }],
  })
}
</script>
