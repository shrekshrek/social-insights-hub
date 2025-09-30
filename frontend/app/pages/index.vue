<template>
  <div class="space-y-8">
    <!-- 欢迎横幅 -->
    <UCard class="bg-gradient-to-r from-blue-600 to-indigo-600 border-0">
      <div class="text-center text-white">
        <h1 class="text-4xl font-bold mb-4">全栈项目脚手架</h1>
        <p class="text-xl text-blue-100 mb-6">
          基于 Nuxt 4 + FastAPI 的现代化全栈开发解决方案
        </p>
        <div class="flex flex-wrap gap-2 justify-center">
          <UBadge color="neutral" variant="solid" size="lg" class="bg-white/20 backdrop-blur-sm text-white">
            🚀 Nuxt 4
          </UBadge>
          <UBadge color="neutral" variant="solid" size="lg" class="bg-white/20 backdrop-blur-sm text-white">
            ⚡ FastAPI
          </UBadge>
          <UBadge color="neutral" variant="solid" size="lg" class="bg-white/20 backdrop-blur-sm text-white">
            🗄️ PostgreSQL
          </UBadge>
          <UBadge color="neutral" variant="solid" size="lg" class="bg-white/20 backdrop-blur-sm text-white">
            🎨 Tailwind CSS
          </UBadge>
        </div>
      </div>
    </UCard>

    <!-- 用户状态区域 -->
    <UCard>
      <div v-if="loggedIn" class="text-center space-y-6">
        <div class="inline-flex items-center justify-center w-16 h-16 bg-green-100 dark:bg-green-900 rounded-full">
          <UIcon name="i-heroicons-check" class="w-8 h-8 text-green-600 dark:text-green-400" />
        </div>
        <div>
          <h2 class="text-2xl font-bold text-gray-900 dark:text-white mb-2">欢迎回来！</h2>
          <p class="text-gray-600 dark:text-gray-400">
            你好，<span class="font-medium text-gray-900 dark:text-white">{{ session?.user?.username || "用户" }}</span>
          </p>
        </div>
        <div class="flex flex-col sm:flex-row gap-4 justify-center">
          <NuxtLink 
            v-if="permissions.canAccessDashboard"
            to="/dashboard"
            class="inline-flex items-center justify-center gap-2 px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition-colors"
          >
            <UIcon name="i-heroicons-squares-2x2" class="w-5 h-5" />
            进入工作台
          </NuxtLink>
          <NuxtLink 
            v-if="permissions.canAccessDashboard"
            to="/charts"
            class="inline-flex items-center justify-center gap-2 px-6 py-3 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 font-medium rounded-lg transition-colors"
          >
            <UIcon name="i-heroicons-chart-bar" class="w-5 h-5" />
            查看图表
          </NuxtLink>
        </div>
      </div>

      <div v-else class="text-center space-y-6">
        <div class="inline-flex items-center justify-center w-16 h-16 bg-blue-100 dark:bg-blue-900 rounded-full">
          <UIcon name="i-heroicons-user" class="w-8 h-8 text-blue-600 dark:text-blue-400" />
        </div>
        <div>
          <h2 class="text-2xl font-bold text-gray-900 dark:text-white mb-2">开始使用</h2>
          <p class="text-gray-600 dark:text-gray-400">登录或注册账户以访问完整功能</p>
        </div>
        <div class="flex flex-col sm:flex-row gap-4 justify-center">
          <NuxtLink 
            to="/login"
            class="inline-flex items-center justify-center gap-2 px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition-colors"
          >
            <UIcon name="i-heroicons-arrow-right-on-rectangle" class="w-5 h-5" />
            立即登录
          </NuxtLink>
          <NuxtLink 
            to="/register"
            class="inline-flex items-center justify-center gap-2 px-6 py-3 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 font-medium rounded-lg transition-colors"
          >
            <UIcon name="i-heroicons-user-plus" class="w-5 h-5" />
            注册账户
          </NuxtLink>
        </div>
      </div>
    </UCard>

    <!-- 功能特性 -->
    <div class="grid md:grid-cols-3 gap-6">
      <UCard>
        <template #header>
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 bg-blue-100 dark:bg-blue-900 rounded-lg flex items-center justify-center">
              <UIcon name="i-heroicons-bolt" class="w-5 h-5 text-blue-600 dark:text-blue-400" />
            </div>
            <h3 class="text-lg font-semibold text-gray-900 dark:text-white">高性能</h3>
          </div>
        </template>
        <p class="text-gray-600 dark:text-gray-400">基于现代化技术栈，提供出色的性能和用户体验</p>
      </UCard>

      <UCard>
        <template #header>
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 bg-green-100 dark:bg-green-900 rounded-lg flex items-center justify-center">
              <UIcon name="i-heroicons-shield-check" class="w-5 h-5 text-green-600 dark:text-green-400" />
            </div>
            <h3 class="text-lg font-semibold text-gray-900 dark:text-white">类型安全</h3>
          </div>
        </template>
        <p class="text-gray-600 dark:text-gray-400">TypeScript 全栈支持，确保代码质量和开发效率</p>
      </UCard>

      <UCard>
        <template #header>
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 bg-purple-100 dark:bg-purple-900 rounded-lg flex items-center justify-center">
              <UIcon name="i-heroicons-beaker" class="w-5 h-5 text-purple-600 dark:text-purple-400" />
            </div>
            <h3 class="text-lg font-semibold text-gray-900 dark:text-white">开箱即用</h3>
          </div>
        </template>
        <p class="text-gray-600 dark:text-gray-400">完整的认证系统、数据库集成和部署配置</p>
      </UCard>
    </div>
  </div>
</template>

<script setup lang="ts">
const { session, loggedIn } = useUserSession();
const permissions = usePermissions();

useHead({
  title: '全栈项目脚手架',
  meta: [
    { name: 'description', content: '基于 Nuxt 4 + FastAPI 的现代化全栈开发解决方案' }
  ]
});
</script>
 