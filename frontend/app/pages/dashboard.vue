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

    <!-- 业务模块入口 -->
    <UCard>
      <template #header>
        <h2 class="text-lg font-semibold">业务模块</h2>
      </template>

      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <NuxtLink
          v-if="hasPermission(PERMISSIONS.SOCIAL_MONITOR_ACCESS)"
          to="/social-media/monitors"
          class="flex items-center gap-3 p-4 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
        >
          <UIcon name="i-heroicons-signal" class="w-6 h-6 text-blue-600" />
          <div>
            <div class="font-medium">社媒监测</div>
            <div class="text-sm text-gray-500">监测项目与舆情分析</div>
          </div>
        </NuxtLink>

        <NuxtLink
          v-if="hasPermission(PERMISSIONS.SOCIAL_TASK_ACCESS)"
          to="/social-media/tasks"
          class="flex items-center gap-3 p-4 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
        >
          <UIcon name="i-heroicons-arrow-down-tray" class="w-6 h-6 text-sky-600" />
          <div>
            <div class="font-medium">社媒采集</div>
            <div class="text-sm text-gray-500">数据采集任务管理</div>
          </div>
        </NuxtLink>

        <NuxtLink
          v-if="hasPermission(PERMISSIONS.NEWS_MONITOR_ACCESS)"
          to="/news-media/monitors"
          class="flex items-center gap-3 p-4 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
        >
          <UIcon name="i-heroicons-newspaper" class="w-6 h-6 text-orange-600" />
          <div>
            <div class="font-medium">新闻监测</div>
            <div class="text-sm text-gray-500">新闻舆情追踪分析</div>
          </div>
        </NuxtLink>

        <NuxtLink
          v-if="hasPermission(PERMISSIONS.STRATEGY_ACCESS)"
          to="/strategies"
          class="flex items-center gap-3 p-4 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
        >
          <UIcon name="i-heroicons-light-bulb" class="w-6 h-6 text-yellow-600" />
          <div>
            <div class="font-medium">策略研究</div>
            <div class="text-sm text-gray-500">多渠道策略报告生成</div>
          </div>
        </NuxtLink>

        <NuxtLink
          v-if="hasPermission(PERMISSIONS.RESEARCH_AGENT_ACCESS)"
          to="/research-agent"
          class="flex items-center gap-3 p-4 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
        >
          <UIcon name="i-heroicons-magnifying-glass" class="w-6 h-6 text-violet-600" />
          <div>
            <div class="font-medium">专题研究</div>
            <div class="text-sm text-gray-500">AI 深度搜索分析</div>
          </div>
        </NuxtLink>

        <NuxtLink
          v-if="hasPermission(PERMISSIONS.ANALYSIS_ACCESS)"
          to="/jobs"
          class="flex items-center gap-3 p-4 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
        >
          <UIcon name="i-heroicons-cpu-chip" class="w-6 h-6 text-purple-600" />
          <div>
            <div class="font-medium">AI 统计</div>
            <div class="text-sm text-gray-500">分析任务与成本追踪</div>
          </div>
        </NuxtLink>

        <NuxtLink
          v-if="hasPermission(PERMISSIONS.KB_ACCESS)"
          to="/knowledge-base"
          class="flex items-center gap-3 p-4 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
        >
          <UIcon name="i-heroicons-book-open" class="w-6 h-6 text-green-600" />
          <div>
            <div class="font-medium">市场知识库</div>
            <div class="text-sm text-gray-500">文档管理与 RAG 检索</div>
          </div>
        </NuxtLink>
      </div>
    </UCard>

    <!-- 系统管理入口 -->
    <UCard v-if="permissions.hasAdminPermissions">
      <template #header>
        <h2 class="text-lg font-semibold">系统管理</h2>
      </template>

      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
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
import { getRoleColor, getRoleLabel } from '~/layers/users/utils/ui-helpers'
import { PERMISSIONS } from '~/config/permissions'

const { session } = useUserSession()
const { logout } = useAuthApi()
const permissions = usePermissions()
const { hasPermission } = permissions

const getGreeting = () => {
  const hour = new Date().getHours()
  if (hour < 6) return '夜深了'
  if (hour < 12) return '早上好'
  if (hour < 18) return '下午好'
  return '晚上好'
}

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
