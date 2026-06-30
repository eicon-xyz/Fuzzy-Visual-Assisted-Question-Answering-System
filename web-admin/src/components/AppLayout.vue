<template>
  <el-container style="height: 100vh">
    <!-- 左侧导航 -->
    <el-aside width="220px" style="background: #304156">
      <div class="logo">
        <span style="font-size: 20px">🔮</span>
        <span>HAJIMI 控制台</span>
      </div>
      <el-menu
        :default-active="route.path"
        router
        background-color="#304156"
        text-color="#bfcbd9"
        active-text-color="#409EFF"
      >
        <el-menu-item index="/dashboard">
          <el-icon><DataAnalysis /></el-icon>
          <span>总览</span>
        </el-menu-item>
        <el-menu-item index="/failures">
          <el-icon><WarningFilled /></el-icon>
          <span>失败归因</span>
        </el-menu-item>
        <el-menu-item index="/flow">
          <el-icon><Connection /></el-icon>
          <span>数据流监控</span>
        </el-menu-item>
        <el-menu-item index="/config">
          <el-icon><Setting /></el-icon>
          <span>系统配置</span>
        </el-menu-item>
        <el-menu-item index="/health">
          <el-icon><Monitor /></el-icon>
          <span>健康监控</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <!-- 右侧内容 -->
    <el-container>
      <el-header style="display: flex; align-items: center; justify-content: space-between; background: #fff; border-bottom: 1px solid #e6e6e6">
        <span style="font-size: 16px; font-weight: 600">{{ route.meta.title }}</span>
        <div>
          <span style="margin-right: 12px; color: #909399">admin@hajimi.local</span>
          <el-button text @click="logout">退出</el-button>
        </div>
      </el-header>
      <el-main style="background: #f0f2f5; overflow-y: auto">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

function logout() {
  localStorage.removeItem('hajimi_token')
  router.replace('/login')
}
</script>

<style scoped>
.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  border-bottom: 1px solid rgba(255,255,255,.1);
}
</style>
