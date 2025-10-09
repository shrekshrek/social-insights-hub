<template>
  <div class="space-y-6">
    <!-- 欢迎信息 -->
    <div>
      <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
        {{ getGreeting() }}，{{ session?.user?.username }}
      </h1>
      <p class="text-gray-600 dark:text-gray-400 mt-1">
        {{ formatDate(new Date()) }}
      </p>
    </div>

    <!-- 用户基本信息 -->
    <UCard>
      <template #header>
        <h2 class="text-lg font-semibold">账户信息</h2>
      </template>

      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            用户名
          </label>
          <p class="text-gray-900 dark:text-gray-100">{{ session?.user?.username }}</p>
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            邮箱
          </label>
          <p class="text-gray-900 dark:text-gray-100">{{ session?.user?.email }}</p>
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            角色
          </label>
          <div class="flex flex-wrap gap-1">
            <UBadge
              v-for="role in session?.user?.roles || ['user']"
              :key="role"
              :color="getRoleColor(role)"
              variant="soft"
              size="sm"
            >
              {{ getRoleLabel(role) }}
            </UBadge>
          </div>
        </div>
      </div>
    </UCard>

    <!-- 快捷操作 -->
    <UCard>
      <template #header>
        <h2 class="text-lg font-semibold">快捷操作</h2>
      </template>

      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <NuxtLink 
          to="/profile" 
          class="flex items-center gap-3 p-4 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
        >
          <UIcon name="i-heroicons-user-circle" class="w-6 h-6 text-blue-600" />
          <div>
            <div class="font-medium">个人资料</div>
            <div class="text-sm text-gray-500">查看和编辑个人信息</div>
          </div>
        </NuxtLink>

        <NuxtLink 
          to="/settings" 
          class="flex items-center gap-3 p-4 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
        >
          <UIcon name="i-heroicons-cog-6-tooth" class="w-6 h-6 text-gray-600" />
          <div>
            <div class="font-medium">账户设置</div>
            <div class="text-sm text-gray-500">管理安全设置</div>
          </div>
        </NuxtLink>

        <NuxtLink 
          to="/charts" 
          class="flex items-center gap-3 p-4 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
        >
          <UIcon name="i-heroicons-chart-bar" class="w-6 h-6 text-purple-600" />
          <div>
            <div class="font-medium">数据图表</div>
            <div class="text-sm text-gray-500">查看数据可视化</div>
          </div>
        </NuxtLink>

        <NuxtLink 
          v-if="permissions.canAccessUsersPage" 
          to="/users" 
          class="flex items-center gap-3 p-4 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
        >
          <UIcon name="i-heroicons-users" class="w-6 h-6 text-red-600" />
          <div>
            <div class="font-medium">用户管理</div>
            <div class="text-sm text-gray-500">管理系统用户</div>
          </div>
        </NuxtLink>
      </div>
    </UCard>

    <!-- 退出登录 -->
    <div class="flex justify-end">
      <UButton color="error" variant="outline" @click="handleSignOut">
        <UIcon name="i-heroicons-arrow-right-on-rectangle" class="w-4 h-4 mr-2" />
        安全退出
      </UButton>
    </div>
  </div>
</template>

<script setup lang="ts">
// 认证保护已由全局认证守卫处理，无需重复定义
import { getRoleColor, getRoleLabel } from '~/layers/users/utils/ui-helpers'

const { session } = useUserSession()
const { logout } = useAuthApi()
const permissions = usePermissions()

// 获取问候语
const getGreeting = () => {
  const hour = new Date().getHours()
  if (hour < 6) return '夜深了'
  if (hour < 12) return '早上好'
  if (hour < 18) return '下午好'
  return '晚上好'
}

// 格式化日期
const formatDate = (date: Date) => {
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    weekday: 'long'
  })
}

const handleSignOut = async () => {
  await logout()
}
</script> 