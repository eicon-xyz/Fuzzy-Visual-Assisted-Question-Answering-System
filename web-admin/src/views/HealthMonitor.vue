<template>
  <div>
    <!-- 资源卡片 -->
    <el-row :gutter="16" style="margin-bottom: 16px">
      <el-col :span="6" v-for="r in resources" :key="r.label">
        <el-card shadow="hover">
          <p style="color: #909399; font-size: 13px">{{ r.label }}</p>
          <p style="font-size: 22px; font-weight: 700; color: #303133; margin: 8px 0">{{ r.value }}</p>
        </el-card>
      </el-col>
    </el-row>

    <!-- 组件状态 -->
    <el-card header="组件健康状态" style="margin-bottom: 16px">
      <el-table :data="components" stripe>
        <el-table-column prop="name" label="组件" />
        <el-table-column prop="status" label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="row.status === 'healthy' ? 'success' : 'warning'" size="small">
              {{ row.status === 'healthy' ? '正常' : '降级' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="detail" label="详情" />
      </el-table>
    </el-card>

    <!-- 告警列表 -->
    <el-card header="活跃告警">
      <el-table :data="alerts" stripe>
        <el-table-column prop="timestamp" label="时间" width="180" />
        <el-table-column prop="level" label="级别" width="80">
          <template #default="{ row }">
            <el-tag :type="row.level === 'warning' ? 'warning' : 'danger'" size="small">
              {{ row.level }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="message" label="内容" />
        <el-table-column label="操作" width="100">
          <template #default>
            <el-button text type="primary">已读</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const resources = ref([
  { label: 'CPU 使用率', value: '42%' },
  { label: '内存占用', value: '3.2 GB' },
  { label: '磁盘剩余', value: '128 GB' },
  { label: '运行时间', value: '14d 7h' },
])

const components = ref([
  { name: 'PostgreSQL', status: 'healthy', detail: '连接池 8/20' },
  { name: 'Redis', status: 'healthy', detail: '命中率 94%' },
  { name: 'LLM API', status: 'degraded', detail: '平均延迟 4.2s（超阈值 3s）' },
  { name: 'Nginx', status: 'healthy', detail: 'QPS 120' },
])

const alerts = ref([
  { timestamp: '2026-06-29 14:20:33', level: 'warning', message: 'LLM API 平均延迟 4.2s 超过阈值 3s，持续 15 分钟' },
  { timestamp: '2026-06-29 13:45:00', level: 'warning', message: '客户端 #d07f 离线超过 30 分钟' },
])
</script>
