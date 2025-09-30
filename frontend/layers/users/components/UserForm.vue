<template>
  <UForm 
    :schema="schema" 
    :state="formState" 
    class="space-y-6"
    @submit="handleSubmit"
  >
    <!-- 基本信息 -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <UFormField label="用户名" name="username">
        <UInput 
          v-model="formState.username" 
          placeholder="请输入用户名"
          :disabled="loading"
        />
      </UFormField>

      <UFormField label="邮箱" name="email">
        <UInput 
          v-model="formState.email" 
          type="email"
          placeholder="请输入邮箱"
          :disabled="loading"
        />
      </UFormField>
    </div>

    <!-- 密码设置 -->
    <div class="space-y-4">
      <h3 class="text-lg font-medium text-gray-900 dark:text-white border-b border-gray-200 dark:border-gray-700 pb-2">
        {{ isEdit ? '密码设置（可选）' : '密码设置' }}
      </h3>
      
      <template v-if="!isEdit">
        <!-- 创建模式：必填密码 -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <UFormField label="密码" name="password" required>
            <UInput 
              v-model="formState.password" 
              type="password"
              placeholder="请输入密码"
              :disabled="loading"
            />
          </UFormField>

          <UFormField label="确认密码" name="confirmPassword" required>
            <UInput 
              v-model="formState.confirmPassword" 
              type="password"
              placeholder="请再次输入密码"
              :disabled="loading"
            />
          </UFormField>
        </div>
      </template>

      <template v-else>
        <!-- 编辑模式：可选密码 -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <UFormField label="新密码" name="password" help="留空表示不修改密码">
            <UInput 
              v-model="formState.password" 
              type="password"
              placeholder="请输入新密码"
              :disabled="loading"
            />
          </UFormField>

          <UFormField 
            v-if="formState.password" 
            label="确认新密码" 
            name="confirmPassword"
            required
          >
            <UInput 
              v-model="formState.confirmPassword" 
              type="password"
              placeholder="请再次输入新密码"
              :disabled="loading"
            />
          </UFormField>
        </div>
      </template>
    </div>

    <!-- 操作按钮 -->
    <div class="flex justify-end gap-3 pt-6 border-t border-gray-200 dark:border-gray-700">
      <UButton 
        variant="outline" 
        :disabled="loading"
        @click="$emit('cancel')"
      >
        取消
      </UButton>
      
      <UButton 
        type="submit" 
        :loading="loading"
        color="primary"
      >
        {{ isEdit ? '更新用户' : '创建用户' }}
      </UButton>
    </div>
  </UForm>
</template>

<script setup lang="ts">
import { z } from 'zod'
import type { User, UserCreate, UserUpdate } from '../types'

// Props
interface Props {
  user?: User | null
  loading?: boolean
  isEdit?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  user: null,
  loading: false,
  isEdit: false
})

// Emits
const emit = defineEmits<{
  'submit': [data: (UserCreate & { role_ids?: number[] }) | UserUpdate]
  'cancel': []
}>()

// 表单状态
const formState = reactive({
  username: '',
  email: '',
  password: '',
  confirmPassword: ''
})

// 表单验证规则
const schema = z.object({
  username: z.string().min(3, '用户名至少3个字符').max(50, '用户名最多50个字符'),
  email: z.string().email('请输入有效的邮箱地址'),
  password: props.isEdit ? z.string().optional() : z.string().min(8, '密码至少8个字符'),
  confirmPassword: props.isEdit ? z.string().optional() : z.string()
}).refine((data) => {
  // 创建模式：密码必须匹配
  if (!props.isEdit && data.password !== data.confirmPassword) {
    return false
  }
  // 编辑模式：如果输入了密码，则必须匹配
  if (props.isEdit && data.password && data.password !== data.confirmPassword) {
    return false
  }
  // 编辑模式：如果输入了密码，长度必须至少8位
  if (props.isEdit && data.password && data.password.length < 8) {
    return false
  }
  return true
}, {
  message: props.isEdit ? '两次输入的密码不一致，或密码少于8个字符' : '两次输入的密码不一致',
  path: ['confirmPassword']
})

// 初始化表单数据
watch(() => props.user, (user) => {
  if (user) {
    formState.username = user.username
    formState.email = user.email
    formState.password = ''
    formState.confirmPassword = ''
  }
}, { immediate: true })

// 提交处理
const handleSubmit = async () => {
  try {
    if (props.isEdit) {
      // 编辑模式：只提交有变化的字段
      const updateData: UserUpdate = {}
      
      if (formState.username !== props.user?.username) {
        updateData.username = formState.username
      }
      
      if (formState.email !== props.user?.email) {
        updateData.email = formState.email
      }
      
      if (formState.password && formState.password.trim()) {
        updateData.password = formState.password
      }
      
      emit('submit', updateData)
    } else {
      // 创建模式：提交所有必需字段
      const createData: UserCreate = {
        username: formState.username,
        email: formState.email,
        password: formState.password
      }
      
      emit('submit', createData)
    }
  } catch (error) {
    console.error('表单提交失败:', error)
  }
}

// 重置表单
const resetForm = () => {
  formState.username = ''
  formState.email = ''
  formState.password = ''
  formState.confirmPassword = ''
}

// 暴露方法
defineExpose({
  resetForm
})
</script> 
