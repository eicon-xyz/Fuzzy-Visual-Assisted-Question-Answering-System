<template>
  <div style="display: flex; justify-content: center; align-items: center; height: 100vh; background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%)">
    <el-card style="width: 420px; border-radius: 8px">
      <template #header>
        <div style="text-align: center">
          <span style="font-size: 28px">🔮</span>
          <h2 style="margin: 8px 0 0">HAJIMI 管理控制台</h2>
          <p style="color: #909399; margin: 4px 0 0">智能桌面指引助手</p>
        </div>
      </template>

      <el-form ref="formRef" :model="form" :rules="rules" @keyup.enter="login">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="管理员账号" :prefix-icon="User" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" placeholder="密码" show-password :prefix-icon="Lock" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" style="width: 100%" :loading="loading" @click="login">
            {{ loading ? '登录中...' : '登 录' }}
          </el-button>
        </el-form-item>
      </el-form>

      <div style="text-align: center; color: #c0c4cc; font-size: 12px">
        Demo 阶段 · 默认账号 admin@hajimi.local
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { User, Lock } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const router = useRouter()
const loading = ref(false)

const form = reactive({
  username: 'admin@hajimi.local',
  password: '',
})

const rules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function login() {
  loading.value = true
  try {
    // Demo 阶段：接受任意非空密码，签发 mock JWT
    if (form.password.length > 0) {
      const mockToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.' +
        btoa(JSON.stringify({ sub: form.username, exp: Date.now() + 7200000 })) +
        '.mock-signature'
      localStorage.setItem('hajimi_token', mockToken)
      ElMessage.success('登录成功')
      router.replace('/dashboard')
    } else {
      ElMessage.error('请输入密码')
    }
  } finally {
    loading.value = false
  }
}
</script>
