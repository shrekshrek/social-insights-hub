<template>
  <div class="space-y-8">
    <!-- Hero -->
    <UCard class="bg-gradient-to-br from-slate-900 via-blue-900 to-cyan-800 border-0">
      <div class="text-center text-white py-2 space-y-4">
        <h1 v-if="appName" class="text-4xl font-bold tracking-wide">{{ appName }}</h1>
        <p class="text-xl text-white/85 font-light max-w-3xl mx-auto leading-relaxed">
          替广告策略团队把 brief 跑成可交付的策略初稿
        </p>
        <p class="text-sm text-white/60">
          中文社媒数据 · 多层 LLM 分析 · 结论可追溯
        </p>
        <div v-if="!loggedIn" class="pt-2">
          <NuxtLink
            to="/login"
            class="inline-flex items-center justify-center gap-2 px-5 py-2.5 bg-white text-slate-900 hover:bg-white/90 font-medium rounded-lg transition-colors text-sm"
          >
            <UIcon name="i-heroicons-arrow-right-on-rectangle" class="w-4 h-4" />
            登录开始使用
          </NuxtLink>
        </div>
      </div>
    </UCard>

    <!-- 典型场景 -->
    <UCard>
      <template #header>
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 bg-blue-100 dark:bg-blue-900 rounded-lg flex items-center justify-center">
            <UIcon name="i-heroicons-briefcase" class="w-5 h-5 text-blue-600 dark:text-blue-400" />
          </div>
          <div>
            <h2 class="text-xl font-semibold text-gray-900 dark:text-white">典型场景</h2>
            <p class="text-sm text-gray-500 dark:text-gray-400">按你日常的活儿，看 {{ appName }} 怎么接</p>
          </div>
        </div>
      </template>
      <div class="grid md:grid-cols-2 gap-4">
        <div class="flex gap-4 p-4 rounded-lg bg-gray-50 dark:bg-gray-800/50">
          <div class="flex-shrink-0 w-10 h-10 bg-violet-100 dark:bg-violet-900 rounded-lg flex items-center justify-center">
            <UIcon name="i-heroicons-document-text" class="w-5 h-5 text-violet-600 dark:text-violet-400" />
          </div>
          <div>
            <h3 class="font-semibold text-gray-900 dark:text-white mb-1">客户给了一个新 brief</h3>
            <p class="text-sm text-gray-600 dark:text-gray-400">从 brief 解析、多渠道采集到 strategic brief 初稿全流程跑通，evidence 可追溯</p>
          </div>
        </div>
        <div class="flex gap-4 p-4 rounded-lg bg-gray-50 dark:bg-gray-800/50">
          <div class="flex-shrink-0 w-10 h-10 bg-blue-100 dark:bg-blue-900 rounded-lg flex items-center justify-center">
            <UIcon name="i-heroicons-signal" class="w-5 h-5 text-blue-600 dark:text-blue-400" />
          </div>
          <div>
            <h3 class="font-semibold text-gray-900 dark:text-white mb-1">客户问"我们品牌在小红书上声量怎么样"</h3>
            <p class="text-sm text-gray-600 dark:text-gray-400">7 大社媒平台监测 + 切片分析，产出实体/观点/竞品/KOL 结构化结论</p>
          </div>
        </div>
        <div class="flex gap-4 p-4 rounded-lg bg-gray-50 dark:bg-gray-800/50">
          <div class="flex-shrink-0 w-10 h-10 bg-orange-100 dark:bg-orange-900 rounded-lg flex items-center justify-center">
            <UIcon name="i-heroicons-newspaper" class="w-5 h-5 text-orange-600 dark:text-orange-400" />
          </div>
          <div>
            <h3 class="font-semibold text-gray-900 dark:text-white mb-1">想搞清品类格局和竞品最近在做什么</h3>
            <p class="text-sm text-gray-600 dark:text-gray-400">跨社媒+新闻策略研究，自动产出 landscape / agenda map / brand role / big idea</p>
          </div>
        </div>
        <div class="flex gap-4 p-4 rounded-lg bg-gray-50 dark:bg-gray-800/50">
          <div class="flex-shrink-0 w-10 h-10 bg-pink-100 dark:bg-pink-900 rounded-lg flex items-center justify-center">
            <UIcon name="i-heroicons-sparkles" class="w-5 h-5 text-pink-600 dark:text-pink-400" />
          </div>
          <div>
            <h3 class="font-semibold text-gray-900 dark:text-white mb-1">临时要一份行业报告或创意参考</h3>
            <p class="text-sm text-gray-600 dark:text-gray-400">Research Agent 自主搜索权威报告/案例，深度阅读后产出结构化洞察</p>
          </div>
        </div>
      </div>
    </UCard>

    <!-- 为什么选 SIH -->
    <UCard>
      <template #header>
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 bg-emerald-100 dark:bg-emerald-900 rounded-lg flex items-center justify-center">
            <UIcon name="i-heroicons-scale" class="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
          </div>
          <div>
            <h2 class="text-xl font-semibold text-gray-900 dark:text-white">为什么选 {{ appName }}</h2>
            <p class="text-sm text-gray-500 dark:text-gray-400">和你现在可能在用的工具对比，看清差异点</p>
          </div>
        </div>
      </template>
      <div class="overflow-x-auto">
        <table class="w-full text-sm min-w-[760px]">
          <thead>
            <tr class="border-b-2 border-gray-200 dark:border-gray-700">
              <th class="text-left p-3 font-semibold text-gray-700 dark:text-gray-300 w-[20%]">你可能在用</th>
              <th class="text-left p-3 font-semibold text-gray-700 dark:text-gray-300 w-[35%]">它的真实强项</th>
              <th class="text-left p-3 font-semibold text-emerald-700 dark:text-emerald-400 w-[45%]">{{ appName }} 在它做不到的地方</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-200 dark:divide-gray-700">
            <tr>
              <td class="p-3 align-top">
                <div class="flex items-center gap-2">
                  <UIcon name="i-heroicons-chat-bubble-left-right" class="w-4 h-4 text-sky-600 dark:text-sky-400 flex-shrink-0" />
                  <span class="font-medium text-gray-900 dark:text-white">通用 AI 对话</span>
                </div>
                <p class="text-xs text-gray-500 mt-1 ml-6">ChatGPT / Claude</p>
              </td>
              <td class="p-3 text-gray-600 dark:text-gray-400 align-top">顶尖推理深度，单点创意发散和策略思辨能力极强，是最好的"思考伙伴"</td>
              <td class="p-3 text-gray-800 dark:text-gray-200 align-top">
                <span class="font-semibold text-emerald-700 dark:text-emerald-400">几百条原始 UGC 一次跑完结构化分析</span>
                <span class="text-gray-600 dark:text-gray-400">——LLM 只做提取与判断，统计数字由代码聚合，结论可追到每条原文</span>
              </td>
            </tr>
            <tr>
              <td class="p-3 align-top">
                <div class="flex items-center gap-2">
                  <UIcon name="i-heroicons-document-magnifying-glass" class="w-4 h-4 text-violet-600 dark:text-violet-400 flex-shrink-0" />
                  <span class="font-medium text-gray-900 dark:text-white">AI Deep Research</span>
                </div>
                <p class="text-xs text-gray-500 mt-1 ml-6">秘塔 / Kimi / Perplexity</p>
              </td>
              <td class="p-3 text-gray-600 dark:text-gray-400 align-top">公开网信息综述能力强，行业报告/学术资料整合迅速，研究类查询体验最佳</td>
              <td class="p-3 text-gray-800 dark:text-gray-200 align-top">
                <span class="font-semibold text-emerald-700 dark:text-emerald-400">社媒 / 新闻 / 行业报告三条链路分别调优</span>
                <span class="text-gray-600 dark:text-gray-400">——社媒拿到 Deep Research 看不见的中文闭源 UGC，新闻按事件维度切片，行业报告 Agent 深读权威源</span>
              </td>
            </tr>
            <tr>
              <td class="p-3 align-top">
                <div class="flex items-center gap-2">
                  <UIcon name="i-heroicons-chart-bar-square" class="w-4 h-4 text-rose-600 dark:text-rose-400 flex-shrink-0" />
                  <span class="font-medium text-gray-900 dark:text-white">专业数据平台</span>
                </div>
                <p class="text-xs text-gray-500 mt-1 ml-6">Brandwatch / 蝉妈妈</p>
              </td>
              <td class="p-3 text-gray-600 dark:text-gray-400 align-top">数据广度与历史回溯无可替代，仪表盘成熟，AI 分析能力深度集成，行业沉淀十年以上</td>
              <td class="p-3 text-gray-800 dark:text-gray-200 align-top">
                <span class="font-semibold text-emerald-700 dark:text-emerald-400">按品类深度定制的策略生产链路</span>
                <span class="text-gray-600 dark:text-gray-400">——从 brief 解析到 big idea 整套按垂类调优，结论可追溯到原始素材，贴合策略 deck 形态而非数据仪表盘</span>
              </td>
            </tr>
            <tr>
              <td class="p-3 align-top">
                <div class="flex items-center gap-2">
                  <UIcon name="i-heroicons-cursor-arrow-rays" class="w-4 h-4 text-amber-600 dark:text-amber-400 flex-shrink-0" />
                  <span class="font-medium text-gray-900 dark:text-white">通用 Agent</span>
                </div>
                <p class="text-xs text-gray-500 mt-1 ml-6">Manus / Operator</p>
              </td>
              <td class="p-3 text-gray-600 dark:text-gray-400 align-top">任意任务通用执行，零部署即用，新需求即时响应，演进速度快</td>
              <td class="p-3 text-gray-800 dark:text-gray-200 align-top">
                <span class="font-semibold text-emerald-700 dark:text-emerald-400">项目化资产沉淀 + 生产级稳定</span>
                <span class="text-gray-600 dark:text-gray-400">——监测项目持续跑、跨任务实体自动归一，后台并发采集，分析链路可复现可审计</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="mt-5 pt-4 border-t border-gray-200 dark:border-gray-700 space-y-2">
        <p class="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">
          它们各有所长——但<span class="font-semibold text-gray-900 dark:text-white">没有一个</span>同时把<span class="font-semibold text-emerald-700 dark:text-emerald-400">中文闭源 UGC 数据</span>、<span class="font-semibold text-emerald-700 dark:text-emerald-400">多层稳定的 LLM 分析链</span>、<span class="font-semibold text-emerald-700 dark:text-emerald-400">可交付的策略产出</span>串成一条生产线。
        </p>
        <p class="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
          这是 {{ appName }} 唯一在做的事——窄而深的位置，专为广告策略团队的日常生产而设计。
        </p>
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
    { name: 'description', content: '替广告策略团队把 brief 跑成可交付的策略初稿——中文社媒数据、多层 LLM 分析、结论可追溯。' }
  ]
})
</script>
