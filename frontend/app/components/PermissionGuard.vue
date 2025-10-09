<template>
  <div v-if="hasAccess">
    <slot />
  </div>
  <div v-else-if="showFallback">
    <slot name="fallback">
      <div class="text-gray-500 text-sm">
        {{ fallbackMessage }}
      </div>
    </slot>
  </div>
</template>

<script setup lang="ts">
/**
 * 权限守卫组件
 * 
 * 用于在模板中进行权限检查，使用结构化权限格式
 * 遵循KISS原则，专注核心功能
 */

import type { Permission } from '~/types/permissions'

interface Props {
  // 需要的权限（满足任意一个即可）
  permissions?: Permission[]
  // 需要的权限组（必须全部满足）
  requireAll?: Permission[]
  // 是否显示降级内容
  showFallback?: boolean
  // 降级消息
  fallbackMessage?: string
}

const props = withDefaults(defineProps<Props>(), {
  permissions: () => [],
  requireAll: () => [],
  showFallback: false,
  fallbackMessage: '权限不足'
})

const permissionChecker = usePermissions()

// 权限检查逻辑
const hasAccess = computed(() => {
  // 如果没有指定权限要求，默认允许访问
  if (!props.permissions && !props.requireAll) {
    return true
  }

  // 检查是否满足任意一个权限
  if (props.permissions && props.permissions.length > 0) {
    const hasAnyPermission = props.permissions.some(permission => 
      permissionChecker.hasPermission(permission)
    )
    if (hasAnyPermission) return true
  }

  // 检查是否满足所有权限
  if (props.requireAll && props.requireAll.length > 0) {
    const hasAllPermissions = props.requireAll.every(permission => 
      permissionChecker.hasPermission(permission)
    )
    if (hasAllPermissions) return true
  }

  return false
})
</script> 