<template>
  <UCard v-if="permission" class="shadow-sm">
    <template #header>
      <div class="space-y-4">
        <!-- 权限基本信息 -->
        <div class="flex items-start gap-4">
          <div class="w-12 h-12 rounded-full bg-success-100 dark:bg-success-900 flex items-center justify-center flex-shrink-0">
            <UIcon name="i-heroicons-shield-check" class="w-6 h-6 text-success-600 dark:text-success-400" />
          </div>
          <div class="flex-1 min-w-0">
            <h2 class="text-xl font-semibold text-gray-900 dark:text-gray-100 break-words">{{ permission.display_name }}</h2>
            <p class="text-gray-500 dark:text-gray-400 text-sm font-mono">{{ permission.target }}:{{ permission.action }}</p>
          </div>
        </div>
        
        <!-- 权限标签 -->
        <div class="flex flex-wrap items-center gap-2">
          <UBadge
            :color="getPermissionTypeColor(permission)"
            variant="soft"
            size="sm"
          >
            {{ getPermissionTypeLabel(permission) }}
          </UBadge>
          <div class="flex items-center space-x-1">
            <UBadge color="primary" variant="soft" size="sm">
              {{ permission.target }}
            </UBadge>
            <span class="text-gray-400 text-xs">:</span>
            <UBadge color="success" variant="soft" size="sm">
              {{ permission.action }}
            </UBadge>
          </div>
        </div>
      </div>
    </template>

    <!-- 代码驱动权限管理说明 -->
    <UAlert
      color="info"
      variant="soft"
      icon="i-heroicons-code-bracket"
      title="权限管理方式"
      description="此权限通过代码定义和管理 (backend/src/rbac/init_data.py)，如需修改请通过开发流程更新代码。"
    />

    <div class="space-y-6">
      <!-- 基本信息 -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div class="space-y-1">
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">权限标识</label>
          <p class="text-gray-900 dark:text-gray-100 font-medium font-mono">{{ permission.target }}:{{ permission.action }}</p>
        </div>
        
        <div class="space-y-1">
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">显示名称</label>
          <p class="text-gray-900 dark:text-gray-100 font-medium">{{ permission.display_name }}</p>
        </div>
        
        <div class="space-y-1">
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">目标</label>
          <UBadge color="primary" variant="soft">
            {{ permission.target }}
          </UBadge>
        </div>
        
        <div class="space-y-1">
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">操作</label>
          <UBadge color="success" variant="soft">
            {{ permission.action }}
          </UBadge>
        </div>
        
        <div class="space-y-1">
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">类型</label>
          <UBadge
            :color="getPermissionTypeColor(permission)"
            variant="soft"
            size="sm"
          >
            {{ getPermissionTypeLabel(permission) }}
          </UBadge>
        </div>
        
        <div class="space-y-1">
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">权限ID</label>
          <p class="text-gray-900 dark:text-gray-100 font-mono text-sm">{{ permission.id }}</p>
        </div>
      </div>

      <!-- 描述 -->
      <div class="space-y-1">
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">权限描述</label>
        <p class="text-gray-900 dark:text-gray-100">{{ permission.description || '-' }}</p>
      </div>

      <!-- RBAC核心权限提示 -->
      <div v-if="permission.target && ['user', 'role', 'permission'].includes(permission.target)" class="space-y-1">
        <UAlert
          color="warning"
          variant="soft"
          icon="i-heroicons-exclamation-triangle"
          title="系统权限"
          description="系统权限由系统自动管理，删除或修改可能影响系统功能，请谨慎操作。"
        />
      </div>

      <!-- 权限管理说明 -->
      <div class="pt-4 border-t border-gray-200 dark:border-gray-700">
        <UAlert
          color="info"
          variant="soft"
          icon="i-heroicons-information-circle"
          title="权限管理说明"
          description="此权限通过代码定义和管理，如需修改请通过开发流程更新代码。"
        />
      </div>
    </div>
  </UCard>
  
  <UCard v-else>
    <div class="text-center py-8">
      <p class="text-gray-500 dark:text-gray-400">权限信息不存在</p>
    </div>
  </UCard>
</template>

<script setup lang="ts">
import type { PermissionWithMeta as Permission } from '../types'

// Props - 简化为只读组件
interface Props {
  permission?: Permission | null
}

const _props = withDefaults(defineProps<Props>(), {
  permission: null
})

// 权限类型分类函数 - 基于业务逻辑而非创建方式
const getPermissionTypeLabel = (permission: Permission): string => {
  // 根据目标模块和操作类型判断权限类别
  if (permission.action === 'access') {
    return '页面访问权限'
  }
  
  if (['user', 'role', 'permission'].includes(permission.target)) {
    return 'RBAC核心权限'
  }
  
  return '业务功能权限'
}

const getPermissionTypeColor = (permission: Permission): "primary" | "secondary" | "success" | "warning" | "error" | "info" | "neutral" => {
  // 根据权限类型返回对应的颜色
  if (permission.action === 'access') {
    return 'info'  // 页面权限用info色
  }
  
  if (['user', 'role', 'permission'].includes(permission.target)) {
    return 'warning'  // RBAC核心权限用warning色
  }
  
  return 'success'  // 业务权限用success色
}

</script> 