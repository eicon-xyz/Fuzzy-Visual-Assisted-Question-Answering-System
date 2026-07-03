<template>
  <div>
    <!-- 资源卡片 -->
    <el-row :gutter="16" style="margin-bottom: 16px">
      <el-col :span="6" v-for="r in resources" :key="r.label">
        <el-card shadow="hover">
          <div style="display: flex; align-items: center; gap: 12px">
            <div :style="{ width: '48px', height: '48px', borderRadius: '12px', background: r.bg, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '22px' }">
              {{ r.icon }}
            </div>
            <div>
              <p style="color: #909399; font-size: 12px; margin: 0">{{ r.label }}</p>
              <p style="font-size: 20px; font-weight: 700; color: #303133; margin: 2px 0">{{ r.value }}</p>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- GPU 状态 (OmniParser 校园网 GPU 服务器) -->
    <el-row :gutter="16" style="margin-bottom: 16px" v-if="gpuInfo">
      <el-col :span="6">
        <el-card shadow="hover">
          <div style="display: flex; align-items: center; gap: 12px">
            <div :style="{ width: '48px', height: '48px', borderRadius: '12px', background: gpuInfo.ready ? '#e8f8e8' : '#fde8e8', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '22px' }">
              🖥
            </div>
            <div>
              <p style="color: #909399; font-size: 12px; margin: 0">GPU 服务器</p>
              <p style="font-size: 14px; font-weight: 600; color: #303133; margin: 2px 0">{{ gpuInfo.gpu_name || 'NVIDIA A800' }}</p>
              <el-tag :type="gpuInfo.ready ? 'success' : 'danger'" size="small">{{ gpuInfo.ready ? '就绪' : '离线' }}</el-tag>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6" v-if="gpuInfo.vram_total_gb">
        <el-card shadow="hover">
          <p style="color: #909399; font-size: 12px">显存使用</p>
          <p style="font-size: 20px; font-weight: 700; color: #303133; margin: 4px 0">
            {{ (gpuInfo.vram_allocated_gb || 0).toFixed(1) }} / {{ gpuInfo.vram_total_gb }} GB
          </p>
          <el-progress :percentage="gpuInfo.vram_total_gb ? ((gpuInfo.vram_allocated_gb || 0) / gpuInfo.vram_total_gb * 100).toFixed(0) : 0" :stroke-width="8" />
        </el-card>
      </el-col>
    </el-row>

    <!-- 组件状态 -->
    <el-card header="组件健康状态" style="margin-bottom: 16px">
      <div style="display: flex; gap: 16px; flex-wrap: wrap">
        <el-card
          v-for="comp in components" :key="comp.name"
          shadow="hover"
          :body-style="{ padding: '20px', textAlign: 'center', minWidth: '160px' }"
        >
          <div :style="{ width: '16px', height: '16px', borderRadius: '50%', background: statusColor(comp.status), margin: '0 auto 8px', boxShadow: `0 0 8px ${statusColor(comp.status)}` }" />
          <p style="font-weight: 600; margin: 4px 0">{{ comp.name }}</p>
          <el-tag :type="comp.status === 'healthy' ? 'success' : 'warning'" size="small">
            {{ comp.status === 'healthy' ? '正常' : '降级' }}
          </el-tag>
          <p style="font-size: 12px; color: #909399; margin: 6px 0 0">{{ comp.detail }}</p>
        </el-card>
      </div>
    </el-card>

    <!-- 告警列表 -->
    <el-card>
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>活跃告警
            <el-badge :value="unreadCount" :hidden="unreadCount === 0" style="margin-left: 8px" />
          </span>
          <div style="display: flex; gap: 8px">
            <el-button text type="primary" @click="markAllRead" :disabled="unreadCount === 0">全部已读</el-button>
            <el-button text @click="exportCSV">CSV 导出</el-button>
          </div>
        </div>
      </template>

      <el-table :data="alerts" stripe @row-click="showDetail">
        <el-table-column prop="timestamp" label="时间" width="180">
          <template #default="{ row }">
            {{ formatTime(row.timestamp) }}
          </template>
        </el-table-column>
        <el-table-column prop="level" label="级别" width="80">
          <template #default="{ row }">
            <el-tag :type="row.level === 'error' ? 'danger' : 'warning'" size="small">
              {{ row.level === 'error' ? '严重' : '告警' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="message" label="内容" />
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'unread' ? 'danger' : 'info'" size="small">
              {{ row.status === 'unread' ? '未读' : '已读' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'unread'"
              text type="primary" size="small"
              @click.stop="markRead(row)"
            >已读</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { fetchMonitorHealth, fetchAlerts, markAlertRead, markAllAlertsRead, fetchGpuProbe } from '../api/admin'

const resources = ref([
  { icon: '🖥', label: 'CPU 使用率', value: '42%', bg: '#e8f4fd' },
  { icon: '💾', label: '内存占用', value: '3.2 GB', bg: '#e8f8e8' },
  { icon: '💿', label: '磁盘剩余', value: '128 GB', bg: '#fdf6e8' },
  { icon: '⏱', label: '运行时间', value: '14d 7h', bg: '#f0e8fd' },
])

const components = ref([])
const alerts = ref([])
const gpuInfo = ref(null)

const unreadCount = computed(() => alerts.value.filter(a => a.status === 'unread').length)

function statusColor(s) {
  return s === 'healthy' ? '#67c23a' : s === 'degraded' ? '#e6a23c' : '#f56c6c'
}

function formatTime(ts) {
  return ts ? new Date(ts).toLocaleString('zh-CN') : ''
}

async function markRead(row) {
  await markAlertRead(row.id)
  row.status = 'read'
  ElMessage.success('已标记为已读')
}

async function markAllRead() {
  await markAllAlertsRead()
  alerts.value.forEach(a => a.status = 'read')
  ElMessage.success('全部已标记为已读')
}

function exportCSV() {
  const header = 'ID,时间,级别,消息,状态\n'
  const rows = alerts.value.map(a => `${a.id},"${formatTime(a.timestamp)}",${a.level},"${a.message}",${a.status}`).join('\n')
  const blob = new Blob(['﻿' + header + rows], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = `hajimi-alerts-${new Date().toISOString().slice(0, 10)}.csv`
  a.click(); URL.revokeObjectURL(url)
  ElMessage.success('CSV 已导出')
}

onMounted(async () => {
  try {
    const h = await fetchMonitorHealth()
    components.value = h?.components || []
    resources.value[0].value = h?.resources?.cpu_pct + '%' || '42%'
    resources.value[1].value = (h?.resources?.memory_gb || 3.2) + ' GB'
    resources.value[2].value = (h?.resources?.disk_free_gb || 128) + ' GB'
  } catch {}
  try {
    const a = await fetchAlerts()
    alerts.value = a?.alerts || []
  } catch {}
  // GPU 状态
  try {
    const probe = await fetchGpuProbe()
    if (probe) {
      gpuInfo.value = {
        ready: probe.ready,
        gpu_name: probe.gpu?.name,
        vram_total_gb: probe.gpu?.vram_total_gb,
        vram_allocated_gb: probe.gpu?.vram_allocated_gb,
        ocr_engine: probe.models?.ocr_engine,
      }
    }
  } catch {}
})
</script>
