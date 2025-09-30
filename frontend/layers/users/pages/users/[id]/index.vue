<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">用户详情</h1>
        <p class="text-gray-600 dark:text-gray-400 mt-1">查看和管理用户信息</p>
      </div>
      
      <UButton
        icon="i-heroicons-arrow-left"
        variant="outline"
        size="sm"
        @click="navigateTo('/users')"
      >
        返回列表
      </UButton>
    </div>

    <!-- 加载状态 -->
    <UCard v-if="pending">
      <div class="text-center py-8">
        <p class="text-gray-600 dark:text-gray-400">加载用户信息中...</p>
      </div>
    </UCard>

    <!-- 错误状态 -->
    <UCard v-else-if="error">
      <div class="text-center py-8">
        <p class="text-red-500 mb-4">{{ error.message || '加载用户信息失败' }}</p>
        <UButton size="sm" @click="refresh()">重试</UButton>
      </div>
    </UCard>
    
    <!-- 用户详情 -->
            <UserDetail
          v-else-if="data"
          :user="data"
          :can-edit="canEdit"
          :can-delete="canDelete"
          @edit="handleEdit"
          @edit-roles="handleEditRoles"
          @delete="handleDelete"
        />
  </div>
</template>

<script setup lang="ts">
// 页面元数据
definePageMeta({
  title: '用户详情'
})

// 路由参数
const route = useRoute()
const userId = computed(() => Number(route.params.id))

// API 调用
const usersApi = useUsersApi()
const { data, pending, error, refresh } = await usersApi.getUser(userId.value)

// 权限检查
const permissions = usePermissions()

const canEdit = computed(() => {
  if (!data.value) return false
  return permissions.canEditUser(data.value)
})

const canDelete = computed(() => {
  if (!data.value) return false
  return permissions.canDeleteUser(data.value)
})

// 事件处理
const handleEdit = () => {
  navigateTo(`/users/${userId.value}/edit`)
}

const handleEditRoles = () => {
  navigateTo(`/users/${userId.value}/roles`)
}

const handleDelete = async () => {
  if (!data.value) return
  
  const { $confirm } = useNuxtApp();
  const confirmed = await $confirm(`确定要删除用户 "${data.value.username}" 吗？`);
  if (!confirmed) return
  
  try {
    await usersApi.deleteUser(data.value.id)
    
    // 显示成功消息
    const toast = useToast()
    toast.add({
      title: '删除成功',
      description: `用户 "${data.value.username}" 已被删除`,
      color: 'success'
    })
    
    navigateTo('/users')
  } catch {
    // 显示错误消息
    const toast = useToast()
    toast.add({
      title: '删除失败',
      description: '无法删除用户，请稍后重试',
      color: 'error'
    })
  }
}

// 监听路由变化
watch(() => route.params.id, async (newId) => {
  if (newId) {
    await refresh()
  }
})
</script> 