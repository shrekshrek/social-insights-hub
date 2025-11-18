<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <UButton
          variant="ghost"
          icon="i-heroicons-arrow-left"
          @click="handleBack"
        />
        <div>
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white">创建角色</h1>
          <p class="text-gray-600 dark:text-gray-400 mt-1">创建新的系统角色</p>
        </div>
      </div>

      <div class="flex items-center gap-3">
        <UButton
          variant="outline"
          :disabled="loading"
          @click="handleCancel"
        >
          取消
        </UButton>
        <UButton
          :loading="loading"
          @click="handleFormSubmit"
        >
          创建
        </UButton>
      </div>
    </div>

    <!-- 创建表单 -->
    <UCard>
      <template #header>
        <h2 class="text-lg font-semibold">角色信息</h2>
      </template>

      <RoleForm
        ref="roleFormRef"
        :loading="loading"
        :is-edit="false"
        :hide-actions="true"
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
const roleFormRef = ref<InstanceType<typeof RoleForm> | null>(null)

// 路由
const router = useRouter()

// API
const rbacApi = useRbacApi()

// 返回处理
const handleBack = () => {
  if (window.history.length > 1) {
    router.back()
  } else {
    navigateTo('/rbac/roles')
  }
}

// 表单提交处理
const handleFormSubmit = () => {
  if (roleFormRef.value) {
    roleFormRef.value.handleSubmit()
  }
}

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
