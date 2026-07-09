<template>
  <div>
    <!-- 用户列表表格 -->
    <el-card>
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>用户列表</span>
          <el-input
            v-model="searchText"
            placeholder="搜索用户名"
            clearable
            style="width: 240px"
            @clear="loadUsers"
            @keyup.enter="loadUsers"
          >
            <template #append>
              <el-button @click="loadUsers">搜索</el-button>
            </template>
          </el-input>
        </div>
      </template>

      <el-table :data="users" stripe v-loading="tableLoading">
        <el-table-column prop="username" label="用户名" />
        <el-table-column prop="role" label="角色" width="100">
          <template #default="{ row }">
            <el-tag :type="row.role === 'admin' ? 'danger' : 'info'" size="small">
              {{ row.role === 'admin' ? '管理员' : '用户' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="task_count" label="任务数" width="80" />
        <el-table-column prop="last_login_at" label="最后登录" width="170">
          <template #default="{ row }">
            {{ row.last_login_at ? new Date(row.last_login_at).toLocaleString() : '从未登录' }}
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="注册时间" width="170">
          <template #default="{ row }">
            {{ row.created_at ? new Date(row.created_at).toLocaleString() : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link @click="showStats(row)">统计</el-button>
            <el-button type="warning" link @click="showResetDialog(row)">重置密码</el-button>
            <el-button type="danger" link @click="confirmDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div style="margin-top: 16px; display: flex; justify-content: flex-end">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @size-change="loadUsers"
          @current-change="loadUsers"
        />
      </div>
    </el-card>

    <!-- 用户统计抽屉 -->
    <el-drawer v-model="statsVisible" title="用户统计" direction="rtl" size="400px">
      <template v-if="stats">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="用户名">{{ stats.username }}</el-descriptions-item>
          <el-descriptions-item label="总任务数">{{ stats.total_tasks }}</el-descriptions-item>
          <el-descriptions-item label="成功率">{{ (stats.success_rate * 100).toFixed(1) }}%</el-descriptions-item>
          <el-descriptions-item label="失败次数">{{ stats.total_failures }}</el-descriptions-item>
          <el-descriptions-item label="反馈数">{{ stats.total_feedback }}</el-descriptions-item>
          <el-descriptions-item label="最后活跃">
            {{ stats.last_active_at ? new Date(stats.last_active_at).toLocaleString() : '无记录' }}
          </el-descriptions-item>
        </el-descriptions>
      </template>
      <template v-else>
        <el-skeleton :rows="8" />
      </template>
    </el-drawer>

    <!-- 重置密码对话框 -->
    <el-dialog v-model="resetVisible" title="重置密码" width="400px">
      <el-form :model="resetForm" label-width="80px">
        <el-form-item label="用户名">
          <span>{{ resetForm.username }}</span>
        </el-form-item>
        <el-form-item label="新密码" required>
          <el-input v-model="resetForm.newPassword" type="password" placeholder="至少6位" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetVisible = false">取消</el-button>
        <el-button type="primary" :loading="resetLoading" @click="doResetPassword">
          确定重置
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { fetchUsersList, fetchUserStats, resetUserPassword, deleteUser } from '../api/admin'

const users = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const searchText = ref('')
const tableLoading = ref(false)

// 统计
const statsVisible = ref(false)
const stats = ref(null)

// 重置密码
const resetVisible = ref(false)
const resetLoading = ref(false)
const resetForm = reactive({ userId: '', username: '', newPassword: '' })

async function loadUsers() {
  tableLoading.value = true
  try {
    const res = await fetchUsersList({
      page: currentPage.value,
      page_size: pageSize.value,
      search: searchText.value || undefined,
    })
    if (res.success) {
      users.value = res.data.items
      total.value = res.data.total
    } else {
      ElMessage.error(res.error?.message || '加载用户列表失败')
    }
  } catch {
    // handled by interceptor
  } finally {
    tableLoading.value = false
  }
}

async function showStats(row) {
  statsVisible.value = true
  stats.value = null
  try {
    const res = await fetchUserStats(row.user_id)
    if (res.success) {
      stats.value = res.data
    }
  } catch {
    statsVisible.value = false
  }
}

function showResetDialog(row) {
  resetForm.userId = row.user_id
  resetForm.username = row.username
  resetForm.newPassword = ''
  resetVisible.value = true
}

async function doResetPassword() {
  if (resetForm.newPassword.length < 6) {
    ElMessage.warning('密码至少 6 位')
    return
  }
  resetLoading.value = true
  try {
    const res = await resetUserPassword(resetForm.userId, resetForm.newPassword)
    if (res.success) {
      ElMessage.success('密码已重置')
      resetVisible.value = false
    } else {
      ElMessage.error(res.error?.message || '重置失败')
    }
  } catch {
    // handled by interceptor
  } finally {
    resetLoading.value = false
  }
}

async function confirmDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确定要删除用户「${row.username}」吗？其历史数据会被保留但脱敏。`,
      '确认删除',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
    const res = await deleteUser(row.user_id)
    if (res.success) {
      ElMessage.success('用户已删除')
      loadUsers()
    } else {
      ElMessage.error(res.error?.message || '删除失败')
    }
  } catch {
    // cancel or error
  }
}

onMounted(loadUsers)
</script>
