<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">创建角色</h1>
        <p class="text-gray-600 dark:text-gray-400 mt-1">创建新的系统角色</p>
      </div>
      
      <UButton
        icon="i-heroicons-arrow-left"
        variant="outline"
        size="sm"
        @click="navigateTo('/rbac/roles')"
      >
        返回列表
      </UButton>
    </div>

    <!-- 创建表单 -->
    <UCard>
      <template #header>
        <h2 class="text-lg font-semibold">角色信息</h2>
      </template>

      <RoleForm
        :loading="loading"
        :is-edit="false"
        @submit="handleSubmit"
        @cancel="handleCancel"
      />
    </UCard>
  </div>
</template>

<script setup lang="ts">
import type { RoleCreate, RoleUpdate } from '../../../types'
import { useRbacApi } from '../../../composables/useRbacApi'
import RoleForm from '../../../components/RoleForm.vue'

// 页面元数据
definePageMeta({
  title: '创建角色'
})

// 状态
const loading = ref(false)

// API
const rbacApi = useRbacApi()

// 处理表单提交
const handleSubmit = async (data: RoleCreate | RoleUpdate) => {
  loading.value = true
  try {
    await rbacApi.createRole(data as RoleCreate)
    navigateTo('/rbac/roles')
  } catch (error) {
    console.error('创建角色失败:', error)
    // 错误已由 useApi 自动处理
  } finally {
    loading.value = false
  }
}

// 处理取消
const handleCancel = () => {
  navigateTo('/rbac/roles')
}
</script> 
