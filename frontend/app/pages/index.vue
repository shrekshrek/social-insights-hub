<template>
  <div class="space-y-8">
    <!-- 欢迎横幅 -->
    <UCard class="bg-gradient-to-r from-blue-600 to-indigo-600 border-0">
      <div class="text-center text-white">
        <h1 class="text-4xl font-bold mb-4">{{ appName }}</h1>
        <p class="text-xl text-blue-100 mb-6">
          社交媒体数据智能分析平台
        </p>
        <div class="flex flex-wrap gap-2 justify-center">
          <UBadge color="neutral" variant="solid" size="lg" class="bg-white/20 backdrop-blur-sm text-white">
            🧭 策略研究
          </UBadge>
          <UBadge color="neutral" variant="solid" size="lg" class="bg-white/20 backdrop-blur-sm text-white">
            📡 社媒监测
          </UBadge>
          <UBadge color="neutral" variant="solid" size="lg" class="bg-white/20 backdrop-blur-sm text-white">
            📰 新闻监测
          </UBadge>
          <UBadge color="neutral" variant="solid" size="lg" class="bg-white/20 backdrop-blur-sm text-white">
            🔍 专题研究
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
        </div>
      </div>

      <div v-else class="text-center space-y-6">
        <div class="inline-flex items-center justify-center w-16 h-16 bg-blue-100 dark:bg-blue-900 rounded-full">
          <UIcon name="i-heroicons-user" class="w-8 h-8 text-blue-600 dark:text-blue-400" />
        </div>
        <div>
          <h2 class="text-2xl font-bold text-gray-900 dark:text-white mb-2">开始使用</h2>
          <p class="text-gray-600 dark:text-gray-400">登录账户以访问完整功能</p>
        </div>
        <div class="flex flex-col sm:flex-row gap-4 justify-center">
          <NuxtLink
            to="/login"
            class="inline-flex items-center justify-center gap-2 px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition-colors"
          >
            <UIcon name="i-heroicons-arrow-right-on-rectangle" class="w-5 h-5" />
            立即登录
          </NuxtLink>
        </div>
      </div>
    </UCard>

    <!-- 核心功能 -->
    <div class="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
      <UCard>
        <template #header>
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 bg-yellow-100 dark:bg-yellow-900 rounded-lg flex items-center justify-center">
              <UIcon name="i-heroicons-light-bulb" class="w-5 h-5 text-yellow-600 dark:text-yellow-400" />
            </div>
            <h3 class="text-lg font-semibold text-gray-900 dark:text-white">策略研究</h3>
          </div>
        </template>
        <p class="text-gray-600 dark:text-gray-400">汇聚多渠道数据，LLM 辅助生成品牌策略分析报告</p>
      </UCard>

      <UCard>
        <template #header>
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 bg-blue-100 dark:bg-blue-900 rounded-lg flex items-center justify-center">
              <UIcon name="i-heroicons-signal" class="w-5 h-5 text-blue-600 dark:text-blue-400" />
            </div>
            <h3 class="text-lg font-semibold text-gray-900 dark:text-white">社媒监测</h3>
          </div>
        </template>
        <p class="text-gray-600 dark:text-gray-400">聚合抖音、微博、B站等 7 大平台，追踪品牌声量与舆情动态</p>
      </UCard>

      <UCard>
        <template #header>
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 bg-orange-100 dark:bg-orange-900 rounded-lg flex items-center justify-center">
              <UIcon name="i-heroicons-newspaper" class="w-5 h-5 text-orange-600 dark:text-orange-400" />
            </div>
            <h3 class="text-lg font-semibold text-gray-900 dark:text-white">新闻监测</h3>
          </div>
        </template>
        <p class="text-gray-600 dark:text-gray-400">整合多渠道新闻，自动切片分析，生成新闻舆情报告</p>
      </UCard>

      <UCard>
        <template #header>
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 bg-violet-100 dark:bg-violet-900 rounded-lg flex items-center justify-center">
              <UIcon name="i-heroicons-magnifying-glass" class="w-5 h-5 text-violet-600 dark:text-violet-400" />
            </div>
            <h3 class="text-lg font-semibold text-gray-900 dark:text-white">专题研究</h3>
          </div>
        </template>
        <p class="text-gray-600 dark:text-gray-400">AI agentic 搜索，针对特定议题进行深度信息挖掘与分析</p>
      </UCard>
    </div>
  </div>
</template>

<script setup lang="ts">
const { session, loggedIn } = useUserSession()
const permissions = usePermissions()

const config = useRuntimeConfig()
const appName = computed(() => config.public.appName || '脉图智策')

useHead({
  title: appName.value,
  meta: [
    { name: 'description', content: '社交媒体数据智能分析平台，聚合多平台数据，通过 LLM 提供舆情监测与策略洞察' }
  ]
})
</script>
