<template>
  <UCard v-if="role" class="shadow-sm">
    <template #header>
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-4">
          <div class="w-12 h-12 rounded-full bg-primary-100 dark:bg-primary-900 flex items-center justify-center">
            <span class="text-lg font-medium text-primary-600 dark:text-primary-400">
              {{ role.display_name.charAt(0).toUpperCase() }}
            </span>
          </div>
          <div>
            <h2 class="text-xl font-semibold text-gray-900 dark:text-gray-100">{{ role.display_name }}</h2>
            <p class="text-gray-500 dark:text-gray-400">{{ role.name }}</p>
            <div class="mt-1">
              <UBadge
                :color="isCoreRole(role.name) ? 'warning' : 'neutral'"
                variant="soft"
                size="sm"
              >
                {{ isCoreRole(role.name) ? '核心角色' : '自定义角色' }}
              </UBadge>
            </div>
          </div>
        </div>
        
        <div class="flex items-center gap-2">
          <UButton
            v-if="canEdit"
            icon="i-heroicons-key"
            variant="outline"
            size="sm"
            color="primary"
            @click="$emit('edit-permissions')"
          >
            编辑权限
          </UButton>
          
          <UButton
            v-if="canEdit && !isCoreRole(role?.name)"
            icon="i-heroicons-pencil-square"
            variant="outline"
            size="sm"
            color="primary"
            @click="$emit('edit')"
          >
            编辑
          </UButton>
          
          <UButton
            v-if="canDelete && !isCoreRole(role?.name)"
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
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">角色名称</label>
          <p class="text-gray-900 dark:text-gray-100 font-medium">{{ role.name }}</p>
        </div>
        
        <div class="space-y-1">
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">显示名称</label>
          <p class="text-gray-900 dark:text-gray-100 font-medium">{{ role.display_name }}</p>
        </div>
        
        <div class="space-y-1">
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">类型</label>
          <UBadge
            :color="isCoreRole(role?.name) ? 'warning' : 'neutral'"
            variant="soft"
            size="sm"
          >
            {{ isCoreRole(role?.name) ? '核心角色' : '自定义角色' }}
          </UBadge>
        </div>
        
        <div class="space-y-1">
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">角色ID</label>
          <p class="text-gray-900 dark:text-gray-100 font-mono text-sm">{{ role.id }}</p>
        </div>
      </div>

      <!-- 描述 -->
      <div class="space-y-1">
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">角色描述</label>
        <p class="text-gray-900 dark:text-gray-100">{{ role.description || '-' }}</p>
      </div>

      <!-- 权限信息 -->
      <div class="space-y-1">
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">权限数量</label>
        <div class="flex items-center gap-2">
          <UBadge color="primary" variant="soft">
            {{ role.permissions?.length || 0 }} 个权限
          </UBadge>
          <span class="text-sm text-gray-500 dark:text-gray-400">
            {{ role.permissions?.length ? '点击"编辑权限"查看详细权限配置' : '该角色暂未分配任何权限' }}
          </span>
        </div>
      </div>

      <!-- 角色管理说明 -->
      <div class="pt-4 border-t border-gray-200 dark:border-gray-700">
        <UAlert
          color="info"
          variant="soft"
          icon="i-heroicons-information-circle"
          title="角色管理说明"
          description="核心角色（super_admin, admin, user）由系统管理，自定义角色可以通过界面编辑。"
        />
      </div>
    </div>
  </UCard>
  
  <UCard v-else>
    <div class="text-center py-8">
      <p class="text-gray-500 dark:text-gray-400">角色信息不存在</p>
    </div>
  </UCard>
</template>

<script setup lang="ts">
import type { Role } from '../types'
import { isCoreRole } from '../utils/permissions'

// Props
interface Props {
  role?: Role | null
  canEdit?: boolean
  canDelete?: boolean
}

const _props = withDefaults(defineProps<Props>(), {
  role: null,
  canEdit: false,
  canDelete: false
})

// Emits
const _emit = defineEmits<{
  'edit': []
  'edit-permissions': []
  'delete': []
}>()

</script> 