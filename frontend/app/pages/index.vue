<template>
  <div class="space-y-8">
    <!-- 欢迎横幅 -->
    <UCard class="bg-gradient-to-r from-blue-600 to-indigo-600 border-0">
      <div class="text-center text-white">
        <h1 v-if="appName" class="text-4xl font-bold mb-4">{{ appName }}</h1>
        <p class="text-xl text-blue-100 mb-6">
          AI 驱动的品牌策略与创意研究平台
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
            🔍 行业研究
          </UBadge>
          <UBadge color="neutral" variant="solid" size="lg" class="bg-white/20 backdrop-blur-sm text-white">
            🎨 创意研究
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
    <div class="grid md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-6">
      <UCard>
        <template #header>
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 bg-yellow-100 dark:bg-yellow-900 rounded-lg flex items-center justify-center">
              <UIcon name="i-heroicons-light-bulb" class="w-5 h-5 text-yellow-600 dark:text-yellow-400" />
            </div>
            <h3 class="text-lg font-semibold text-gray-900 dark:text-white">策略研究</h3>
          </div>
        </template>
        <p class="text-gray-600 dark:text-gray-400">汇聚多渠道数据，LLM 辅助生成品牌策略与市场报告</p>
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
        <p class="text-gray-600 dark:text-gray-400">聚合小红书、抖音、微博等 7 大平台，追踪品牌声量与舆情动态</p>
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
        <p class="text-gray-600 dark:text-gray-400">整合多渠道新闻（包括公众号），自动切片分析，生成新闻舆情报告</p>
      </UCard>

      <UCard>
        <template #header>
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 bg-violet-100 dark:bg-violet-900 rounded-lg flex items-center justify-center">
              <UIcon name="i-heroicons-magnifying-glass" class="w-5 h-5 text-violet-600 dark:text-violet-400" />
            </div>
            <h3 class="text-lg font-semibold text-gray-900 dark:text-white">行业研究</h3>
          </div>
        </template>
        <p class="text-gray-600 dark:text-gray-400">Agentic 搜索权威报告与数据，深度阅读后生成结构化行业洞察</p>
      </UCard>

      <UCard>
        <template #header>
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 bg-pink-100 dark:bg-pink-900 rounded-lg flex items-center justify-center">
              <UIcon name="i-heroicons-sparkles" class="w-5 h-5 text-pink-600 dark:text-pink-400" />
            </div>
            <h3 class="text-lg font-semibold text-gray-900 dark:text-white">创意研究</h3>
          </div>
        </template>
        <p class="text-gray-600 dark:text-gray-400">检索 campaign 案例与创意评论，提炼视觉/文案钩子与传播机制</p>
      </UCard>
    </div>
  </div>
</template>

<script setup lang="ts">
const { session, loggedIn } = useUserSession()
const permissions = usePermissions()

const config = useRuntimeConfig()
const appName = computed(() => (config.public.appName as string) || '')

useHead({
  title: appName.value || undefined,
  meta: [
    { name: 'description', content: 'AI 驱动的品牌策略与创意研究平台：多渠道数据聚合、行业报告搜索、创意案例检索，辅助品牌策略决策与创意策划。' }
  ]
})
</script>
