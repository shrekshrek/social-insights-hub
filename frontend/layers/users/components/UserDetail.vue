<template>
  <UCard v-if="user" class="shadow-sm">
    <template #header>
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-4">
          <UAvatar
            :alt="user.username"
            size="xl"
          >
            {{ user.username.charAt(0).toUpperCase() }}
          </UAvatar>
          <div>
            <h2 class="text-xl font-semibold text-gray-900 dark:text-gray-100">{{ user.username }}</h2>
            <p class="text-gray-500 dark:text-gray-400">{{ user.email }}</p>
            <div class="mt-1">
              <div class="flex flex-wrap gap-1">
                <UBadge
                  v-for="role in user.roles"
                  :key="role"
                  :color="getRoleColor(role)"
                  variant="subtle"
                  size="sm"
                >
                  {{ getRoleLabel(role) }}
                </UBadge>
              </div>
            </div>
          </div>
        </div>
        
        <div class="flex items-center gap-2">
          <UButton
            v-if="canEdit"
            icon="i-heroicons-user-group"
            variant="outline"
            size="sm"
            color="primary"
            @click="$emit('edit-roles')"
          >
            编辑角色
          </UButton>
          
          <UButton
            v-if="canEdit"
            icon="i-heroicons-pencil-square"
            variant="outline"
            size="sm"
            color="primary"
            @click="$emit('edit')"
          >
            编辑
          </UButton>
          
          <UButton
            v-if="canDelete"
            icon="i-heroicons-trash"
            variant="outline"
            size="sm"
            color="error"
            @click="$emit('delete')"
          >
            删除
          </UButton>
        </div>
      </div>
    </template>

    <div class="space-y-6">
      <!-- 基本信息 -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div class="space-y-1">
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">用户名</label>
          <p class="text-gray-900 dark:text-gray-100 font-medium">{{ user.username }}</p>
        </div>
        
        <div class="space-y-1">
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">邮箱</label>
          <p class="text-gray-900 dark:text-gray-100 font-medium">{{ user.email }}</p>
        </div>
        
        <div class="space-y-1">
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">角色</label>
          <div class="flex flex-wrap gap-1">
            <UBadge
              v-for="role in user.roles"
              :key="role"
              :color="getRoleColor(role)"
              variant="subtle"
              size="sm"
            >
              {{ getRoleLabel(role) }}
            </UBadge>
          </div>
        </div>
        
        <div class="space-y-1">
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">用户ID</label>
          <p class="text-gray-900 dark:text-gray-100 font-mono text-sm">{{ user.id }}</p>
        </div>
      </div>

      <!-- 时间信息 -->
      <div class="pt-4 border-t border-gray-200 dark:border-gray-700">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div class="space-y-1">
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">创建时间</label>
            <p class="text-gray-900 dark:text-gray-100">{{ formatDate(user.created_at) }}</p>
          </div>
          
          <div class="space-y-1">
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">更新时间</label>
            <p class="text-gray-900 dark:text-gray-100">{{ formatDate(user.updated_at) }}</p>
          </div>
        </div>
      </div>
    </div>
  </UCard>
  
  <UCard v-else>
    <div class="text-center py-8">
      <p class="text-gray-500 dark:text-gray-400">用户信息不存在</p>
    </div>
  </UCard>
</template>

<script setup lang="ts">
import type { User } from '../types'
import { getRoleColor, getRoleLabel } from '../utils/ui-helpers'

// Props
interface Props {
  user?: User | null
  canEdit?: boolean
  canDelete?: boolean
}

const _props = withDefaults(defineProps<Props>(), {
  user: null,
  canEdit: false,
  canDelete: false
})

// Emits
const _emit = defineEmits<{
  'edit': []
  'edit-roles': []
  'delete': []
}>()

const formatDate = (dateString: string) => {
  return new Date(dateString).toLocaleString('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}
</script> 