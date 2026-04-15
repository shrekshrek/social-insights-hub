<template>
  <div class="container mx-auto p-6">
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-3xl font-bold">开发测试页面</h1>
        <p class="text-gray-600 dark:text-gray-400 mt-1">
          认证功能和权限系统的综合测试演示
        </p>
      </div>
      <UBadge color="warning" variant="soft">
        仅开发环境
      </UBadge>
    </div>
    
    <div class="space-y-8">
      <!-- 认证状态测试区 -->
      <UCard>
        <template #header>
          <h2 class="text-xl font-semibold">🔐 认证状态测试</h2>
        </template>

        <ClientOnly>
          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <!-- 认证状态 -->
            <div class="space-y-3">
              <h3 class="font-medium text-gray-900 dark:text-white">认证状态</h3>
              <div class="space-y-2 text-sm">
                <div class="flex justify-between">
                  <span>状态:</span>
                  <UBadge :color="loggedIn ? 'success' : 'error'" size="xs">
                    {{ loggedIn ? 'authenticated' : 'unauthenticated' }}
                  </UBadge>
                </div>
                <div class="flex justify-between">
                  <span>是否认证:</span>
                  <span class="font-mono">{{ loggedIn ? '是' : '否' }}</span>
                </div>
                <div class="flex justify-between">
                  <span>有Token:</span>
                  <span class="font-mono">{{ session?.accessToken ? '是' : '否' }}</span>
                </div>
              </div>
            </div>

            <!-- 用户信息 -->
            <div class="space-y-3">
              <h3 class="font-medium text-gray-900 dark:text-white">用户信息</h3>
              <div v-if="session?.user" class="space-y-2 text-sm">
                <div class="flex justify-between">
                  <span>用户名:</span>
                  <span class="font-mono">{{ session.user.username }}</span>
                </div>
                <div class="flex justify-between">
                  <span>邮箱:</span>
                  <span class="font-mono">{{ session.user.email }}</span>
                </div>
                <div class="flex justify-between">
                  <span>用户ID:</span>
                  <span class="font-mono">{{ session.user.id }}</span>
                </div>
              </div>
              <div v-else class="text-sm text-gray-500">
                未登录
              </div>
            </div>

            <!-- 权限Store状态 -->
            <div class="space-y-3">
              <h3 class="font-medium text-gray-900 dark:text-white">权限Store状态</h3>
              <div class="space-y-2 text-sm">
                <div class="flex justify-between">
                  <span>权限加载状态:</span>
                  <UBadge :color="permissions.permissionsLoaded ? 'success' : 'error'" size="xs">
                    {{ permissions.permissionsLoaded ? '已加载' : '未加载' }}
                  </UBadge>
                </div>
                <div class="flex justify-between">
                  <span>权限数量:</span>
                  <span class="font-mono">{{ (permissions.permissions as any)?.length || 0 }}</span>
                </div>
                <div class="flex justify-between">
                  <span>用户角色:</span>
                  <span class="font-mono">{{ (permissions.currentUserRoles as any)?.join(', ') || '无' }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 测试按钮 -->
          <div class="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
            <div class="flex items-center gap-3">
              <UButton :loading="loginLoading" size="sm" @click="testLogin">
                测试登录
              </UButton>
              <UButton color="error" variant="outline" size="sm" @click="testLogout">
                测试登出
              </UButton>
                             <UButton variant="outline" size="sm" @click="reloadPage">
                 刷新页面
               </UButton>
            </div>
          </div>

          <template #fallback>
            <div class="animate-pulse space-y-4">
              <div class="h-20 bg-gray-200 rounded"/>
              <div class="h-8 bg-gray-200 rounded w-1/3"/>
            </div>
          </template>
        </ClientOnly>
      </UCard>

      <!-- 当前用户权限信息 -->
      <UCard>
        <template #header>
          <h2 class="text-xl font-semibold">👤 当前用户权限信息</h2>
        </template>

        <ClientOnly>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <!-- 角色信息 -->
            <div class="space-y-3">
              <h3 class="font-medium text-gray-900 dark:text-white">用户角色</h3>
              <div v-if="permissions.currentUserRoles.value.length > 0" class="flex flex-wrap gap-2">
                                 <UBadge 
                   v-for="role in permissions.currentUserRoles.value" 
                   :key="role"
                   color="primary"
                   variant="soft"
                 >
                   {{ getRoleLabel(role) }}
                 </UBadge>
              </div>
              <div v-else class="text-sm text-gray-500">
                无角色
              </div>
            </div>

            <!-- 管理员状态 -->
            <div class="space-y-3">
              <h3 class="font-medium text-gray-900 dark:text-white">管理员状态</h3>
              <div class="space-y-2">
                <div class="flex items-center justify-between">
                  <span class="text-sm">是否管理员:</span>
                  <UBadge :color="permissions.hasAdminPermissions ? 'success' : 'neutral'" size="xs">
                    {{ permissions.hasAdminPermissions ? '是' : '否' }}
                  </UBadge>
                </div>
                <div class="flex items-center justify-between">
                  <span class="text-sm">用户ID:</span>
                  <span class="text-sm font-mono">{{ permissions.currentUserId }}</span>
                </div>
              </div>
            </div>
          </div>

          <template #fallback>
            <div class="animate-pulse space-y-4">
              <div class="h-16 bg-gray-200 rounded"/>
            </div>
          </template>
        </ClientOnly>
      </UCard>

      <!-- 权限检查演示 -->
      <UCard>
        <template #header>
          <h2 class="text-xl font-semibold">🛡️ 权限检查演示</h2>
        </template>

        <ClientOnly>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <!-- 用户管理权限 -->
            <div class="space-y-4">
              <h3 class="font-medium text-gray-900 dark:text-white">用户管理权限</h3>
              <div class="space-y-2">
                <PermissionGuard :permissions="[PERMISSIONS.USER_READ]" show-fallback>
                  <UButton size="sm" icon="i-heroicons-eye">查看用户</UButton>
                  <template #fallback>
                    <UButton size="sm" disabled variant="outline">查看用户 (无权限)</UButton>
                  </template>
                </PermissionGuard>
                
                <PermissionGuard :permissions="[PERMISSIONS.USER_WRITE]" show-fallback>
                  <UButton size="sm" icon="i-heroicons-pencil-square">编辑用户</UButton>
                  <template #fallback>
                    <UButton size="sm" disabled variant="outline">编辑用户 (无权限)</UButton>
                  </template>
                </PermissionGuard>
                
                <PermissionGuard :permissions="[PERMISSIONS.USER_DELETE]" show-fallback>
                  <UButton color="error" size="sm" icon="i-heroicons-trash">删除用户</UButton>
                  <template #fallback>
                    <UButton size="sm" disabled variant="outline">删除用户 (无权限)</UButton>
                  </template>
                </PermissionGuard>
              </div>
            </div>

            <!-- 角色管理权限 -->
            <div class="space-y-4">
              <h3 class="font-medium text-gray-900 dark:text-white">角色管理权限</h3>
              <div class="space-y-2">
                <PermissionGuard :permissions="[PERMISSIONS.ROLE_READ]" show-fallback>
                  <UButton size="sm" icon="i-heroicons-eye">查看角色</UButton>
                  <template #fallback>
                    <UButton size="sm" disabled variant="outline">查看角色 (无权限)</UButton>
                  </template>
                </PermissionGuard>
                
                <PermissionGuard :permissions="[PERMISSIONS.ROLE_WRITE]" show-fallback>
                  <UButton size="sm" icon="i-heroicons-pencil-square">编辑角色</UButton>
                  <template #fallback>
                    <UButton size="sm" disabled variant="outline">编辑角色 (无权限)</UButton>
                  </template>
                </PermissionGuard>
                
                <PermissionGuard :permissions="[PERMISSIONS.ROLE_DELETE]" show-fallback>
                  <UButton color="error" size="sm" icon="i-heroicons-trash">删除角色</UButton>
                  <template #fallback>
                    <UButton size="sm" disabled variant="outline">删除角色 (无权限)</UButton>
                  </template>
                </PermissionGuard>
              </div>
            </div>
          </div>

          <!-- 组合权限检查 -->
          <div class="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
            <h3 class="font-medium text-gray-900 dark:text-white mb-4">组合权限检查</h3>
            <div class="space-y-3">
              <!-- 需要多个权限（全部满足） -->
              <div class="flex items-center gap-3">
                <span class="text-sm w-48">高级管理功能 (需要用户+角色权限):</span>
                <PermissionGuard 
                  :require-all="[PERMISSIONS.USER_WRITE, PERMISSIONS.ROLE_WRITE]"
                  show-fallback
                >
                  <UButton size="sm" color="success">有权限</UButton>
                  <template #fallback>
                    <UButton size="sm" disabled variant="outline">无权限</UButton>
                  </template>
                </PermissionGuard>
              </div>
              
              <!-- 需要任意权限 -->
              <div class="flex items-center gap-3">
                <span class="text-sm w-48">管理面板 (任意管理权限):</span>
                <PermissionGuard 
                  :permissions="[PERMISSIONS.USER_READ, PERMISSIONS.ROLE_READ]"
                  show-fallback
                >
                  <UButton size="sm" color="success">有权限</UButton>
                  <template #fallback>
                    <UButton size="sm" disabled variant="outline">无权限</UButton>
                  </template>
                </PermissionGuard>
              </div>
              
              <!-- 管理员权限检查 -->
              <div class="flex items-center gap-3">
                <span class="text-sm w-48">系统设置 (管理员权限):</span>
                <UButton 
                  v-if="permissions.hasAdminPermissions"
                  size="sm" 
                  color="success"
                >
                  有权限
                </UButton>
                <UButton 
                  v-else
                  size="sm" 
                  disabled 
                  variant="outline"
                >
                  无权限
                </UButton>
              </div>
            </div>
          </div>

          <template #fallback>
            <div class="animate-pulse space-y-4">
              <div class="h-32 bg-gray-200 rounded"/>
              <div class="h-16 bg-gray-200 rounded"/>
            </div>
          </template>
        </ClientOnly>
      </UCard>

      <!-- 权限状态一览表 -->
      <UCard>
        <template #header>
          <h2 class="text-xl font-semibold">📊 权限状态一览</h2>
        </template>

        <ClientOnly>
          <div class="overflow-x-auto">
            <table class="min-w-full">
              <thead>
                <tr class="border-b border-gray-200 dark:border-gray-700">
                  <th class="px-4 py-3 text-left text-sm font-medium text-gray-900 dark:text-white">
                    权限名称
                  </th>
                  <th class="px-4 py-3 text-left text-sm font-medium text-gray-900 dark:text-white">
                    权限代码
                  </th>
                  <th class="px-4 py-3 text-left text-sm font-medium text-gray-900 dark:text-white">
                    状态
                  </th>
                  <th class="px-4 py-3 text-left text-sm font-medium text-gray-900 dark:text-white">
                    类型
                  </th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-200 dark:divide-gray-700">
                <tr v-for="item in allPermissions" :key="`${item.key.target}:${item.key.action}`">
                  <td class="px-4 py-3 text-sm text-gray-900 dark:text-white">
                    {{ item.name }}
                  </td>
                  <td class="px-4 py-3 text-sm font-mono text-gray-600 dark:text-gray-400">
                    {{ `${item.key.target}:${item.key.action}` }}
                  </td>
                  <td class="px-4 py-3">
                    <UBadge 
                      :color="permissions.hasPermission(item.key) ? 'success' : 'neutral'"
                      size="sm"
                    >
                      {{ item.hasPermission ? '✓ 有权限' : '✗ 无权限' }}
                    </UBadge>
                  </td>
                  <td class="px-4 py-3">
                    <UBadge 
                      :color="item.type === 'core' ? 'error' : 'primary'"
                      size="sm"
                      variant="soft"
                    >
                      {{ item.type === 'core' ? '核心' : '业务' }}
                    </UBadge>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <template #fallback>
            <div class="animate-pulse space-y-3">
              <div class="h-6 bg-gray-200 rounded w-full"/>
              <div class="h-6 bg-gray-200 rounded w-3/4"/>
              <div class="h-6 bg-gray-200 rounded w-1/2"/>
              <p class="text-sm text-gray-500">加载权限状态中...</p>
            </div>
          </template>
        </ClientOnly>
      </UCard>

      <!-- 测试操作区 -->
      <UCard>
        <template #header>
          <h2 class="text-xl font-semibold">🔧 测试操作</h2>
        </template>

        <div class="space-y-4">
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <h3 class="font-medium text-gray-900 dark:text-white mb-2">认证测试</h3>
              <div class="space-x-2">
                <UButton :loading="loginLoading" size="sm" @click="testLogin">
                  快速登录 (admin)
                </UButton>
                <UButton color="error" variant="outline" size="sm" @click="testLogout">
                  登出
                </UButton>
              </div>
            </div>

            <div>
              <h3 class="font-medium text-gray-900 dark:text-white mb-2">权限测试</h3>
              <div class="space-x-2">
                                 <UButton color="error" variant="outline" size="sm" @click="clearPermissions">
                   清除权限缓存
                 </UButton>
              </div>
            </div>
          </div>

          <!-- 测试结果显示区 -->
          <div v-if="testMessage" class="mt-4 p-3 rounded-lg" :class="testMessageClass">
            <p class="text-sm">{{ testMessage }}</p>
          </div>
        </div>
      </UCard>
    </div>
  </div>
</template>

<script setup lang="ts">
import { PERMISSIONS } from '~/config/permissions'
import { isCorePermission } from '~/app/composables/usePermissions'
import { getRoleLabel } from '~/layers/users/utils/ui-helpers'

// 开发环境检查 - 生产环境下重定向到首页
if (process.env.NODE_ENV === 'production') {
  throw createError({
    statusCode: 404,
    statusMessage: 'Page Not Found'
  })
}

// 页面元数据
definePageMeta({
  title: '开发测试',
  description: '认证和权限系统的综合测试页面'
})

// 认证相关
const { session, loggedIn } = useUserSession()
const { login, logout } = useAuthApi()
const permissions = usePermissions()

// 响应式数据
const loginLoading = ref(false)
const testMessage = ref('')
const testMessageType = ref<'success' | 'error' | 'info'>('info')

// 计算属性
const testMessageClass = computed(() => {
  const baseClass = 'border'
  switch (testMessageType.value) {
    case 'success':
      return `${baseClass} bg-green-50 border-green-200 text-green-800 dark:bg-green-900/20 dark:border-green-800 dark:text-green-200`
    case 'error':
      return `${baseClass} bg-red-50 border-red-200 text-red-800 dark:bg-red-900/20 dark:border-red-800 dark:text-red-200`
    default:
      return `${baseClass} bg-blue-50 border-blue-200 text-blue-800 dark:bg-blue-900/20 dark:border-blue-800 dark:text-blue-200`
  }
})

// 所有权限列表（用于展示）
const allPermissions = computed(() => [
  { 
    key: PERMISSIONS.USER_READ, 
    name: '查看用户',
    hasPermission: permissions.hasPermission(PERMISSIONS.USER_READ),
    type: isCorePermission(PERMISSIONS.USER_READ) ? 'core' : 'business'
  },
  { 
    key: PERMISSIONS.USER_WRITE, 
    name: '编辑用户',
    hasPermission: permissions.hasPermission(PERMISSIONS.USER_WRITE),
    type: isCorePermission(PERMISSIONS.USER_WRITE) ? 'core' : 'business'
  },
  { 
    key: PERMISSIONS.USER_DELETE, 
    name: '删除用户',
    hasPermission: permissions.hasPermission(PERMISSIONS.USER_DELETE),
    type: isCorePermission(PERMISSIONS.USER_DELETE) ? 'core' : 'business'
  },
  { 
    key: PERMISSIONS.ROLE_READ, 
    name: '查看角色',
    hasPermission: permissions.hasPermission(PERMISSIONS.ROLE_READ),
    type: isCorePermission(PERMISSIONS.ROLE_READ) ? 'core' : 'business'
  },
  { 
    key: PERMISSIONS.ROLE_WRITE, 
    name: '编辑角色',
    hasPermission: permissions.hasPermission(PERMISSIONS.ROLE_WRITE),
    type: isCorePermission(PERMISSIONS.ROLE_WRITE) ? 'core' : 'business'
  },
  { 
    key: PERMISSIONS.ROLE_DELETE, 
    name: '删除角色',
    hasPermission: permissions.hasPermission(PERMISSIONS.ROLE_DELETE),
    type: isCorePermission(PERMISSIONS.ROLE_DELETE) ? 'core' : 'business'
  },
  { 
    key: PERMISSIONS.PERMISSION_READ, 
    name: '查看权限',
    hasPermission: permissions.hasPermission(PERMISSIONS.PERMISSION_READ),
    type: isCorePermission(PERMISSIONS.PERMISSION_READ) ? 'core' : 'business'
  },
  { 
    key: PERMISSIONS.PERMISSION_WRITE, 
    name: '编辑权限',
    hasPermission: permissions.hasPermission(PERMISSIONS.PERMISSION_WRITE),
    type: isCorePermission(PERMISSIONS.PERMISSION_WRITE) ? 'core' : 'business'
  },
  { 
    key: PERMISSIONS.PERMISSION_DELETE, 
    name: '删除权限',
    hasPermission: permissions.hasPermission(PERMISSIONS.PERMISSION_DELETE),
    type: isCorePermission(PERMISSIONS.PERMISSION_DELETE) ? 'core' : 'business'
  },
  { 
    key: PERMISSIONS.DASHBOARD_ACCESS, 
    name: '访问工作台',
    hasPermission: permissions.hasPermission(PERMISSIONS.DASHBOARD_ACCESS),
    type: isCorePermission(PERMISSIONS.DASHBOARD_ACCESS) ? 'core' : 'business'
  },
  {
    key: PERMISSIONS.USER_ACCESS,
    name: '访问用户管理',
    hasPermission: permissions.hasPermission(PERMISSIONS.USER_ACCESS),
    type: isCorePermission(PERMISSIONS.USER_ACCESS) ? 'core' : 'business'
  },
  {
    key: PERMISSIONS.ROLE_ACCESS,
    name: '访问角色管理',
    hasPermission: permissions.hasPermission(PERMISSIONS.ROLE_ACCESS),
    type: isCorePermission(PERMISSIONS.ROLE_ACCESS) ? 'core' : 'business'
  },
  {
    key: PERMISSIONS.PERMISSION_ACCESS,
    name: '访问权限管理',
    hasPermission: permissions.hasPermission(PERMISSIONS.PERMISSION_ACCESS),
    type: isCorePermission(PERMISSIONS.PERMISSION_ACCESS) ? 'core' : 'business'
  },
])

// 测试方法
const showTestMessage = (message: string, type: 'success' | 'error' | 'info' = 'info') => {
  testMessage.value = message
  testMessageType.value = type
  // 3秒后自动清除消息
  setTimeout(() => {
    testMessage.value = ''
  }, 3000)
}

const testLogin = async () => {
  loginLoading.value = true
  try {
    // 使用新的 login 方法
    await login({
      username: 'admin',
      password: 'admin123'
    })
    
    // 检查认证状态来判断是否成功
    if (loggedIn.value) {
      console.log('登录成功，认证状态已更新')
      showTestMessage('登录成功！用户信息和权限已更新', 'success')
    } else {
      throw new Error("Authentication failed")
    }
  } catch (error) {
    console.error('登录失败:', error)
    showTestMessage('登录失败，请检查用户名和密码', 'error')
  } finally {
    loginLoading.value = false
  }
}

const testLogout = async () => {
  try {
    await logout()
    console.log('登出成功')
    showTestMessage('登出成功！', 'success')
  } catch (error) {
    console.error('登出失败:', error)
    showTestMessage('登出失败', 'error')
  }
}

const reloadPage = () => {
  // 刷新页面
  window.location.reload()
}

const clearPermissions = () => {
  // 清除权限缓存
  if (import.meta.client) {
    localStorage.removeItem('user_permissions_cache')
  }
  showTestMessage('权限缓存已清除', 'info')
}
</script> 