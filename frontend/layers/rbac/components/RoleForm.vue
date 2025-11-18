<template>
  <UForm 
    :schema="schema" 
    :state="formState" 
    class="space-y-6"
    @submit="handleSubmit"
  >
    <!-- 基本信息 -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <UFormField label="角色名称" name="name">
        <UInput 
          v-model="formState.name" 
          placeholder="请输入角色名称（英文）"
          :disabled="loading"
        />
      </UFormField>

      <UFormField label="显示名称" name="display_name">
        <UInput 
          v-model="formState.display_name" 
          placeholder="请输入显示名称（中文）"
          :disabled="loading"
        />
      </UFormField>

      <div class="md:col-span-2">
        <UFormField label="角色描述" name="description">
          <UTextarea 
            v-model="formState.description" 
            placeholder="请输入角色描述（可选）"
            :disabled="loading"
            :rows="3"
            class="w-full"
          />
        </UFormField>
      </div>
    </div>

    <!-- 操作按钮 -->
    <div v-if="!hideActions" class="flex justify-end gap-3 pt-6 border-t border-gray-200 dark:border-gray-700">
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
        {{ isEdit ? '更新角色' : '创建角色' }}
      </UButton>
    </div>
  </UForm>
</template>

<script setup lang="ts">
import { z } from 'zod'
import type { Role, RoleCreate, RoleUpdate } from '../types'

// Props
interface Props {
  role?: Role | null
  loading?: boolean
  isEdit?: boolean
  hideActions?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  role: null,
  loading: false,
  isEdit: false,
  hideActions: false
})

// Emits
const emit = defineEmits<{
  'submit': [data: RoleCreate | RoleUpdate]
  'cancel': []
}>()

// 表单状态
const formState = reactive({
  name: '',
  display_name: '',
  description: ''
})

// 表单验证规则
const schema = z.object({
  name: z.string().min(2, '角色名称至少2个字符').max(50, '角色名称最多50个字符').regex(/^[a-zA-Z0-9_-]+$/, '角色名称只能包含字母、数字、下划线和横线'),
  display_name: z.string().min(2, '显示名称至少2个字符').max(50, '显示名称最多50个字符'),
  description: z.string().max(200, '描述最多200个字符').optional()
})

// 初始化表单数据
watch(() => props.role, (role) => {
  if (role) {
    formState.name = role.name
    formState.display_name = role.display_name
    formState.description = role.description || ''
  }
}, { immediate: true })

// 提交处理
const handleSubmit = async () => {
  try {
    if (props.isEdit) {
      // 编辑模式：只提交有变化的字段
      const updateData: RoleUpdate = {}
      
      if (formState.name !== props.role?.name) {
        updateData.name = formState.name
      }
      
      if (formState.display_name !== props.role?.display_name) {
        updateData.display_name = formState.display_name
      }
      
      if (formState.description !== (props.role?.description || '')) {
        updateData.description = formState.description || undefined
      }
      
      emit('submit', updateData)
    } else {
      // 创建模式：提交所有字段
      const createData: RoleCreate = {
        name: formState.name,
        display_name: formState.display_name,
        description: formState.description || undefined
      }
      
      emit('submit', createData)
    }
  } catch (error) {
    console.error('表单提交失败:', error)
  }
}

// 重置表单
const resetForm = () => {
  formState.name = ''
  formState.display_name = ''
  formState.description = ''
}

// 暴露方法
defineExpose({
  resetForm,
  handleSubmit
})
</script> 