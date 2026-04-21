<template>
  <div class="space-y-8">
    <!-- 欢迎横幅 -->
    <UCard class="bg-gradient-to-br from-gray-900 to-black border-0">
      <div class="text-center text-white py-4">
        <h1 v-if="appName" class="text-4xl font-bold tracking-wide mb-4">{{ appName }}</h1>
        <p class="text-xl text-white/70 font-light">
          AI 驱动的品牌策略与创意研究平台
        </p>
      </div>
    </UCard>

    <!-- 登录引导（仅未登录显示） -->
    <UCard v-if="!loggedIn">
      <div class="text-center space-y-6">
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

    <!-- 平台能力亮点 -->
    <UCard>
      <template #header>
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 bg-emerald-100 dark:bg-emerald-900 rounded-lg flex items-center justify-center">
            <UIcon name="i-heroicons-star" class="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
          </div>
          <div>
            <h2 class="text-xl font-semibold text-gray-900 dark:text-white">平台能力亮点</h2>
            <p class="text-sm text-gray-500 dark:text-gray-400">面向广告策略研究场景的工程化 AI 系统</p>
          </div>
        </div>
      </template>
      <div class="grid sm:grid-cols-2 gap-4">
        <div class="flex gap-4 p-4 rounded-lg bg-gray-50 dark:bg-gray-800/50">
          <div class="flex-shrink-0 w-10 h-10 bg-emerald-100 dark:bg-emerald-900 rounded-lg flex items-center justify-center">
            <UIcon name="i-heroicons-rectangle-stack" class="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
          </div>
          <div>
            <h3 class="font-semibold text-gray-900 dark:text-white mb-1">三源交叉验证</h3>
            <p class="text-sm text-gray-600 dark:text-gray-400">消费者声音（社媒）+ 媒体事实（新闻）+ 行业报告（Research Agent）多源交叉，降低单一视角偏差</p>
          </div>
        </div>
        <div class="flex gap-4 p-4 rounded-lg bg-gray-50 dark:bg-gray-800/50">
          <div class="flex-shrink-0 w-10 h-10 bg-indigo-100 dark:bg-indigo-900 rounded-lg flex items-center justify-center">
            <UIcon name="i-heroicons-sparkles" class="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
          </div>
          <div>
            <h3 class="font-semibold text-gray-900 dark:text-white mb-1">从 Brief 到 Big Idea</h3>
            <p class="text-sm text-gray-600 dark:text-gray-400">AI 贯穿策略研究全流程，多层分析链路沉淀可追溯的结构化产出，不是零散工具拼接</p>
          </div>
        </div>
        <div class="flex gap-4 p-4 rounded-lg bg-gray-50 dark:bg-gray-800/50">
          <div class="flex-shrink-0 w-10 h-10 bg-amber-100 dark:bg-amber-900 rounded-lg flex items-center justify-center">
            <UIcon name="i-heroicons-shield-check" class="w-5 h-5 text-amber-600 dark:text-amber-400" />
          </div>
          <div>
            <h3 class="font-semibold text-gray-900 dark:text-white mb-1">采集前可校准</h3>
            <p class="text-sm text-gray-600 dark:text-gray-400">Probe/Collect 两段式采集，搜索方向先审核再全量执行，避免黑盒一把过</p>
          </div>
        </div>
        <div class="flex gap-4 p-4 rounded-lg bg-gray-50 dark:bg-gray-800/50">
          <div class="flex-shrink-0 w-10 h-10 bg-teal-100 dark:bg-teal-900 rounded-lg flex items-center justify-center">
            <UIcon name="i-heroicons-banknotes" class="w-5 h-5 text-teal-600 dark:text-teal-400" />
          </div>
          <div>
            <h3 class="font-semibold text-gray-900 dark:text-white mb-1">成本透明可控</h3>
            <p class="text-sm text-gray-600 dark:text-gray-400">每次 LLM 调用 token 账单入库，Prompt Cache 命中率 93%+，项目成本可预测</p>
          </div>
        </div>
      </div>
    </UCard>

    <!-- 在 AI 工具生态中的位置 -->
    <UCard>
      <template #header>
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 bg-slate-100 dark:bg-slate-800 rounded-lg flex items-center justify-center">
            <UIcon name="i-heroicons-squares-plus" class="w-5 h-5 text-slate-600 dark:text-slate-400" />
          </div>
          <div>
            <h2 class="text-xl font-semibold text-gray-900 dark:text-white">在 AI 工具生态中的位置</h2>
            <p class="text-sm text-gray-500 dark:text-gray-400">不同工具面向不同场景 · {{ appName }} 聚焦广告策略研究的生产系统</p>
          </div>
        </div>
      </template>
      <div class="grid md:grid-cols-3 gap-4">
        <div class="p-4 rounded-lg bg-gray-50 dark:bg-gray-800/50">
          <div class="flex items-center gap-2 mb-2">
            <div class="w-10 h-10 bg-sky-100 dark:bg-sky-900 rounded-lg flex items-center justify-center">
              <UIcon name="i-heroicons-chat-bubble-left-right" class="w-5 h-5 text-sky-600 dark:text-sky-400" />
            </div>
            <h3 class="font-semibold text-gray-900 dark:text-white">通用 AI 对话</h3>
          </div>
          <p class="text-xs text-gray-500 dark:text-gray-400 mb-2">ChatGPT / Claude 等：擅长单次创意发散与推理</p>
          <p class="text-sm text-gray-700 dark:text-gray-300 pt-2 border-t border-gray-200 dark:border-gray-700">
            <span class="font-medium text-gray-900 dark:text-white">{{ appName }}</span> 把这类推理能力嵌入多层分析链路，服务多项目并行的策略生产
          </p>
        </div>
        <div class="p-4 rounded-lg bg-gray-50 dark:bg-gray-800/50">
          <div class="flex items-center gap-2 mb-2">
            <div class="w-10 h-10 bg-violet-100 dark:bg-violet-900 rounded-lg flex items-center justify-center">
              <UIcon name="i-heroicons-document-magnifying-glass" class="w-5 h-5 text-violet-600 dark:text-violet-400" />
            </div>
            <h3 class="font-semibold text-gray-900 dark:text-white">AI Deep Research</h3>
          </div>
          <p class="text-xs text-gray-500 dark:text-gray-400 mb-2">OpenAI / Perplexity 等：擅长一次性自主研究</p>
          <p class="text-sm text-gray-700 dark:text-gray-300 pt-2 border-t border-gray-200 dark:border-gray-700">
            <span class="font-medium text-gray-900 dark:text-white">{{ appName }}</span> 把类似能力沉淀为可重现、可中途校准、结论可追溯的工程化研究流程
          </p>
        </div>
        <div class="p-4 rounded-lg bg-gray-50 dark:bg-gray-800/50">
          <div class="flex items-center gap-2 mb-2">
            <div class="w-10 h-10 bg-rose-100 dark:bg-rose-900 rounded-lg flex items-center justify-center">
              <UIcon name="i-heroicons-chart-bar-square" class="w-5 h-5 text-rose-600 dark:text-rose-400" />
            </div>
            <h3 class="font-semibold text-gray-900 dark:text-white">专业数据平台</h3>
          </div>
          <p class="text-xs text-gray-500 dark:text-gray-400 mb-2">Brandwatch / 蝉妈妈等：擅长多平台数据聚合</p>
          <p class="text-sm text-gray-700 dark:text-gray-300 pt-2 border-t border-gray-200 dark:border-gray-700">
            <span class="font-medium text-gray-900 dark:text-white">{{ appName }}</span> 把数据、多层 LLM 分析与人机协作整合为端到端的策略研究引擎
          </p>
        </div>
      </div>
    </UCard>
  </div>
</template>

<script setup lang="ts">
const { loggedIn } = useUserSession()

const config = useRuntimeConfig()
const appName = computed(() => (config.public.appName as string) || '')

useHead({
  title: appName.value || undefined,
  meta: [
    { name: 'description', content: 'AI 驱动的品牌策略与创意研究平台：多渠道数据聚合、行业报告搜索、创意案例检索，辅助品牌策略决策与创意策划。' }
  ]
})
</script>
