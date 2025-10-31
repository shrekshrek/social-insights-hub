<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <div>
    <!-- 页面标题 -->
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-gray-900 dark:text-gray-100">账户设置</h1>
      <p class="text-gray-600 dark:text-gray-400 mt-1">管理您的账户安全设置</p>
    </div>

    <div class="space-y-6">
      <!-- 修改密码卡片 -->
      <UCard>
        <template #header>
          <h2 class="text-lg font-semibold text-gray-900 dark:text-gray-100">修改密码</h2>
        </template>

        <UForm ref="passwordForm" :schema="passwordSchema" :state="passwordState" @submit="handlePasswordSubmit">
          <div class="space-y-5 md:space-y-6">
            <!-- 当前密码 -->
            <div class="space-y-2">
              <UFormField label="当前密码" name="currentPassword">
                <UInput
                  v-model="passwordState.currentPassword"
                  type="password"
                  placeholder="请输入当前密码"
                  :disabled="passwordLoading"
                  size="lg"
                />
              </UFormField>
            </div>

            <!-- 新密码区域 -->
            <div class="space-y-3 md:space-y-4 pt-4">
              <h4 class="text-sm font-medium text-gray-900 dark:text-gray-100">设置新密码</h4>
              
              <div class="grid grid-cols-1 md:grid-cols-2 gap-3 md:gap-4">
                <UFormField label="新密码" name="newPassword">
                  <UInput
                    v-model="passwordState.newPassword"
                    type="password"
                    placeholder="请输入新密码"
                    :disabled="passwordLoading"
                    size="lg"
                  />
                </UFormField>

                <UFormField label="确认新密码" name="confirmPassword">
                  <UInput
                    v-model="passwordState.confirmPassword"
                    type="password"
                    placeholder="请再次输入新密码"
                    :disabled="passwordLoading"
                    size="lg"
                  />
                </UFormField>
              </div>

              <div class="text-sm text-gray-500 dark:text-gray-400">
                <p>• 密码长度至少8个字符</p>
                <p>• 建议包含字母、数字和特殊字符</p>
              </div>
            </div>

            <div class="flex justify-end pt-4">
              <UButton
                type="submit"
                :loading="passwordLoading"
                icon="i-heroicons-key"
                size="lg"
              >
                更新密码
              </UButton>
            </div>
          </div>
        </UForm>
      </UCard>

      <!-- 账户信息卡片 -->
      <UCard>
        <template #header>
          <h2 class="text-lg font-semibold text-gray-900 dark:text-gray-100">账户信息</h2>
        </template>

        <div class="space-y-4">
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                登录状态
              </label>
              <UBadge color="success" variant="soft">
                已登录
              </UBadge>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                最后登录时间
              </label>
              <p class="text-gray-900 dark:text-gray-100">
                {{ formatDate(new Date()) }}
              </p>
            </div>
          </div>

          <div class="pt-4 border-t border-gray-200 dark:border-gray-700">
            <h3 class="text-sm font-medium text-gray-900 dark:text-gray-100 mb-3">安全操作</h3>
            <div class="flex flex-wrap gap-2">
              <UButton
                variant="outline"
                size="sm"
                icon="i-heroicons-arrow-right-on-rectangle"
                @click="handleSignOut"
              >
                登出所有设备
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

// 页面元数据
definePageMeta({
  title: '账户设置'
})

const { logout } = useAuthApi()
const toast = useToast()

// 修改密码相关
const passwordLoading = ref(false)
const passwordState = ref({
  currentPassword: '',
  newPassword: '',
  confirmPassword: ''
})

// 密码验证规则
const passwordSchema = z.object({
  currentPassword: z.string().min(1, '请输入当前密码'),
  newPassword: z.string().min(8, '新密码至少8个字符'),
  confirmPassword: z.string()
}).refine((data) => data.newPassword === data.confirmPassword, {
  message: '两次输入的密码不一致',
  path: ['confirmPassword']
})

// 格式化日期
const formatDate = (date: Date) => {
  return date.toLocaleString('zh-CN')
}



// 处理密码修改
const handlePasswordSubmit = async () => {
  passwordLoading.value = true
  
  try {
    const { apiRequest } = useApi()
    
    await apiRequest('/auth/change-password', {
      method: 'POST',
      body: {
        current_password: passwordState.value.currentPassword,
        new_password: passwordState.value.newPassword
      }
    })
    
    // 清空表单
    passwordState.value = {
      currentPassword: '',
      newPassword: '',
      confirmPassword: ''
    }
  } catch {
    // 错误已由 useApi 自动处理
  } finally {
    passwordLoading.value = false
  }
}

// 处理登出
const handleSignOut = async () => {
  await logout()
}
</script> 