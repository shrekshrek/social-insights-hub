<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">创建用户</h1>
        <p class="text-gray-600 dark:text-gray-400 mt-1">添加新的系统用户</p>
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

    <!-- 创建表单 -->
    <UCard>
      <template #header>
        <h2 class="text-lg font-semibold">用户信息</h2>
      </template>

      <UserForm
        :loading="loading"
        @submit="handleSubmit"
        @cancel="handleCancel"
      />
    </UCard>
  </div>
</template>

<script setup lang="ts">
import type { UserCreate, UserUpdate } from '../../types'

// 页面元数据
definePageMeta({
  title: '创建用户'
})

// 状态管理
const loading = ref(false)

// API 调用
const usersApi = useUsersApi()

// 事件处理
const handleSubmit = async (data: UserCreate | UserUpdate) => {
  // 在创建页面，data 总是 UserCreate 类型
  const createData = data as UserCreate
  loading.value = true
  try {
    await usersApi.createUser(createData)
    navigateTo('/users')
  } catch {
    // 错误已由 useApi 自动处理
  } finally {
    loading.value = false
  }
}

const handleCancel = () => {
  navigateTo('/users')
}
</script> 