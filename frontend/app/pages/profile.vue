<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div>
      <h1 class="text-2xl font-bold text-gray-900 dark:text-gray-100">个人资料</h1>
      <p class="text-gray-600 dark:text-gray-400 mt-1">查看和编辑您的个人信息</p>
    </div>

    <!-- 加载状态 -->
    <UCard v-if="pending">
      <div class="text-center py-8">
        <p class="text-gray-600 dark:text-gray-400">加载中...</p>
      </div>
    </UCard>

    <!-- 错误状态 -->
    <UCard v-else-if="error">
      <div class="text-center py-8">
        <p class="text-red-500 mb-4">{{ error.message || '加载个人信息失败' }}</p>
        <UButton size="sm" @click="refresh()">重试</UButton>
      </div>
    </UCard>

    <!-- 个人资料内容 -->
    <div v-else-if="data" class="space-y-6">
      <!-- 基本信息卡片 -->
      <UCard>
        <template #header>
          <div class="flex items-center justify-between">
            <h2 class="text-lg font-semibold">基本信息</h2>
            <UButton
              variant="outline"
              size="sm"
              icon="i-heroicons-pencil-square"
              @click="isEditing = !isEditing"
            >
              {{ isEditing ? '取消编辑' : '编辑' }}
            </UButton>
          </div>
        </template>

        <div v-if="!isEditing" class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              用户名
            </label>
            <p class="text-gray-900 dark:text-gray-100">{{ data.username }}</p>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              邮箱
            </label>
            <p class="text-gray-900 dark:text-gray-100">{{ data.email }}</p>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              角色
            </label>
            <div class="flex flex-wrap gap-1">
              <UBadge
                v-for="role in data.roles"
                :key="role"
                :color="getRoleColor(role)"
                variant="soft"
                size="sm"
              >
                {{ getRoleLabel(role) }}
              </UBadge>
            </div>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              用户ID
            </label>
            <p class="text-gray-900 dark:text-gray-100">{{ data.id }}</p>
          </div>
        </div>

        <div v-else>
          <!-- 编辑模式 -->
          <UForm ref="form" :schema="schema" :state="formState" @submit="handleSubmit">
            <div class="space-y-4">
              <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <UFormField label="用户名" name="username">
                  <UInput v-model="formState.username" />
                </UFormField>
                <UFormField label="邮箱" name="email">
                  <UInput v-model="formState.email" type="email" />
                </UFormField>
              </div>
              
              <div class="flex justify-end gap-2">
                <UButton
                  variant="outline"
                  :disabled="loading"
                  @click="cancelEdit"
                >
                  取消
                </UButton>
                <UButton
                  type="submit"
                  :loading="loading"
                >
                  保存
                </UButton>
              </div>
            </div>
          </UForm>
        </div>
      </UCard>

      <!-- 账户信息卡片 -->
      <UCard>
        <template #header>
          <h2 class="text-lg font-semibold">账户信息</h2>
        </template>

        <div class="space-y-4">
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                注册时间
              </label>
              <p class="text-gray-900 dark:text-gray-100">
                {{ formatDate(data.created_at) }}
              </p>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                最后更新
              </label>
              <p class="text-gray-900 dark:text-gray-100">
                {{ formatDate(data.updated_at) }}
              </p>
            </div>
          </div>
          
          <!-- 快速链接到设置页面 -->
          <div class="pt-4 border-t border-gray-200 dark:border-gray-700">
            <div class="flex items-center justify-between">
              <div>
                <h3 class="text-sm font-medium text-gray-900 dark:text-gray-100">账户设置</h3>
                <p class="text-sm text-gray-500 dark:text-gray-400">管理密码和安全设置</p>
              </div>
              <UButton
                variant="outline"
                size="sm"
                icon="i-heroicons-cog-6-tooth"
                to="/settings"
              >
                前往设置
              </UButton>
            </div>
          </div>
        </div>
      </UCard>
    </div>
  </div>
</template>

<script setup lang="ts">
import { z } from 'zod'
import { getRoleColor, getRoleLabel } from '~/layers/users/utils/ui-helpers'

// 页面元数据
definePageMeta({
  title: '个人资料'
})

// 获取当前用户信息
const usersApi = useUsersApi()
const toast = useToast()

// 获取用户详细信息
const { data, pending, error, refresh } = await usersApi.getCurrentUser()

// 编辑状态
const isEditing = ref(false)
const loading = ref(false)

// 表单状态
const formState = ref({
  username: '',
  email: ''
})

// 表单验证
const schema = z.object({
  username: z.string().min(3, '用户名至少3个字符').max(50, '用户名最多50个字符'),
  email: z.string().email('请输入有效的邮箱地址')
})

// 初始化表单数据
watch(data, (newData) => {
  if (newData) {
    formState.value = {
      username: newData.username,
      email: newData.email
    }
  }
}, { immediate: true })



// 格式化日期
const formatDate = (dateString: string) => {
  return new Date(dateString).toLocaleString('zh-CN')
}

// 提交表单
const handleSubmit = async () => {
  if (!data.value) return
  
  loading.value = true
  try {
    await usersApi.updateUser(data.value.id, {
      username: formState.value.username,
      email: formState.value.email
    })
    
    toast.add({
      title: '更新成功',
      description: '个人资料已更新',
      color: 'success'
    })
    
    isEditing.value = false
    await refresh()
  } catch (err) {
    toast.add({
      title: '更新失败',
      description: err instanceof Error ? err.message : '请稍后重试',
      color: 'error'
    })
  } finally {
    loading.value = false
  }
}

// 取消编辑
const cancelEdit = () => {
  if (data.value) {
    formState.value = {
      username: data.value.username,
      email: data.value.email
    }
  }
  isEditing.value = false
}
</script> 