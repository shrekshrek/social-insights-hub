<script setup lang="ts">
import { h, ref, computed, type Component } from 'vue'
import type { TableColumn } from '@nuxt/ui'
import { UButton, UBadge } from '#components'
import { PERMISSIONS } from '~/config/permissions'

definePageMeta({
  layout: 'default',
})

const route = useRoute()
const taskId = Number(route.params.id)
const { currentUserId, hasPermission } = usePermissions()

const { getTask, executeTask, deleteTask, getTaskArticles, getTaskChannelStats } = useNewsTasks()

const { data: task, pending: taskLoading, refresh: refreshTask } = getTask(taskId)
const { data: channelStats, refresh: refreshChannelStats } = getTaskChannelStats(taskId)

type ChannelKey = 'baidu' | 'sogou' | 'bing' | 'wechat_mp'

const channelBreakdown: { key: ChannelKey; label: string }[] = [
  { key: 'baidu', label: '百度' },
  { key: 'sogou', label: '搜狗' },
  { key: 'bing', label: 'Bing' },
  { key: 'wechat_mp', label: '微信公众号' },
]

const getChannelRaw = (key: ChannelKey): number => {
  return channelStats.value?.[key]?.raw ?? 0
}

const getChannelDeduped = (key: ChannelKey): number => {
  return channelStats.value?.[key]?.deduped ?? 0
}

const executing = ref(false)
const refreshing = ref(false)

const currentPage = ref(1)
const pageSize = ref(20)
const relevanceFilter = ref('all')
const tierFilter = ref('all')

const articleParams = computed(() => ({
  page: currentPage.value,
  page_size: pageSize.value,
  ...(relevanceFilter.value !== 'all' ? { relevance: relevanceFilter.value } : {}),
  ...(tierFilter.value !== 'all' ? { source_tier: tierFilter.value } : {}),
}))

const {
  data: articlesData,
  pending: articlesLoading,
  refresh: refreshArticles,
} = getTaskArticles(taskId, articleParams)

const articles = computed(() => articlesData.value?.items || [])
const totalArticles = computed(() => articlesData.value?.total || 0)

// ========== 返回路径 ==========

const backPath = computed(() => {
  const from = route.query.from as string
  const monitorId = route.query.monitor_id as string
  if (from === 'monitor' && monitorId) {
    return `/news-media/monitors/${monitorId}`
  }
  return '/news-media/tasks'
})

// ========== 执行任务 ==========

const handleExecute = async () => {
  executing.value = true
  try {
    await executeTask(taskId)
    await refreshTask()
    await refreshArticles()
    await refreshChannelStats()
  } catch {
    // error already handled
  } finally {
    executing.value = false
  }
}

const handleRefresh = async () => {
  refreshing.value = true
  await Promise.all([refreshTask(), refreshArticles(), refreshChannelStats()])
  refreshing.value = false
}

const handleDelete = async () => {
  if (!task.value) return

  const { $confirm } = useNuxtApp()
  const confirmed = await $confirm({
    title: '删除任务',
    message: `确定要删除任务 "${task.value.name}" 吗？所有相关文章数据也将被删除。`,
    confirmText: '删除',
    cancelText: '取消',
    type: 'error',
  })

  if (!confirmed) return

  try {
    await deleteTask(task.value.id)
    await navigateTo(backPath.value)
  } catch {
    // error handled by apiRequest
  }
}

// ========== 分析报告 ==========

const analysisResult = computed(() => task.value?.analysis_result || null)
const hasMeta = computed(() => !!analysisResult.value?.meta)
const hasInsights = computed(() => {
  const r = analysisResult.value
  return r && (r.coverage || r.sentiment || r.narratives || r.entities)
})

// ========== 辅助函数 ==========

type BadgeColor = 'warning' | 'error' | 'info' | 'success' | 'primary' | 'secondary' | 'neutral'

const getStatusColor = (status: string): BadgeColor => {
  const map: Record<string, BadgeColor> = {
    pending: 'neutral',
    running: 'info',
    completed: 'success',
    failed: 'error',
  }
  return map[status] || 'neutral'
}

const getStatusText = (status: string) => {
  const map: Record<string, string> = {
    pending: '等待中',
    running: '运行中',
    completed: '已完成',
    failed: '失败',
  }
  return map[status] || status
}

const getPhaseText = (phase: string | null) => {
  const map: Record<string, string> = { probe: '探测', collect: '全量' }
  return map[phase || ''] || phase || '-'
}

const getPhaseColor = (phase: string | null): BadgeColor => {
  const map: Record<string, BadgeColor> = { probe: 'info', collect: 'warning' }
  return map[phase || ''] || 'neutral'
}

const getRelevanceColor = (relevance: string | null) => {
  const map: Record<string, string> = { high: 'success', medium: 'warning', low: 'neutral' }
  return map[relevance || ''] || 'neutral'
}

const getRelevanceLabel = (relevance: string | null) => {
  const map: Record<string, string> = { high: '高', medium: '中', low: '低' }
  return map[relevance || ''] || (relevance ?? '-')
}

const getSentimentColor = (sentiment: number | null) => {
  if (sentiment === null) return 'neutral'
  if (sentiment > 0) return 'success'
  if (sentiment < 0) return 'error'
  return 'neutral'
}

const getSentimentText = (sentiment: number | null) => {
  if (sentiment === null) return '-'
  if (sentiment > 0) return '正面'
  if (sentiment < 0) return '负面'
  return '中性'
}

const getTierLabel = (tier: string) => {
  const map: Record<string, string> = { tier1: '权威', tier2: '行业', tier3: '其他', wechat_mp: '公众号' }
  return map[tier] || tier
}

const getTierColor = (tier: string) => {
  const map: Record<string, string> = { tier1: 'error', tier2: 'warning', tier3: 'neutral', wechat_mp: 'success' }
  return map[tier] || 'neutral'
}

const getSearchSourceText = (source: string) => {
  const map: Record<string, string> = { baidu: '百度', sogou: '搜狗', bing: 'Bing', wechat_mp: '公众号' }
  return map[source] || source
}

const getSearchSourceColor = (source: string) => {
  const map: Record<string, string> = { baidu: 'info', sogou: 'warning', bing: 'success', wechat_mp: 'success' }
  return map[source] || 'neutral'
}

const getTypeText = (type: string | null) => {
  const map: Record<string, string> = {
    report: '报道',
    opinion: '评论',
    pr: '公关稿',
    analysis: '分析',
  }
  return map[type || ''] || type || '-'
}

const formatDate = (dateStr: string | null) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const formatFullDate = (dateStr: string) => {
  return new Date(dateStr).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const formatSentimentScore = (s: number | null | undefined) => {
  if (s === null || s === undefined) return '-'
  return s > 0 ? `+${s.toFixed(2)}` : s.toFixed(2)
}

// ========== 文章表格列 ==========

// 空值统一占位：灰色 "-" 纯文本（不裹 Badge），所有列共享
const emptyCell = () => h('span', { class: 'text-gray-400' }, '-')

const columns = computed<TableColumn<NewsArticle>[]>(() => {
  const Badge = UBadge as Component

  return [
    {
      accessorKey: 'title',
      header: '标题',
      meta: { class: { th: 'w-[280px]', td: 'w-[280px] whitespace-normal' } },
      cell: ({ row }) =>
        h(
          'a',
          {
            href: row.original.url,
            target: '_blank',
            class: 'font-medium leading-snug line-clamp-2 text-blue-600 hover:underline dark:text-blue-400',
            title: row.original.title,
          },
          row.original.title,
        ),
    },
    {
      accessorKey: 'source_name',
      header: '来源',
      meta: { class: { th: 'w-[120px]', td: 'w-[120px]' } },
      cell: ({ row }) => {
        const name = row.original.source_name
        if (!name) return emptyCell()
        return h('div', { class: 'flex items-center gap-1' }, [
          h('span', { class: 'truncate text-sm' }, name),
          h(Badge, { color: getTierColor(row.original.source_tier), size: 'sm' }, () =>
            getTierLabel(row.original.source_tier),
          ),
        ])
      },
    },
    {
      accessorKey: 'search_source',
      header: '搜索渠道',
      meta: { class: { th: 'w-[80px]', td: 'w-[80px]' } },
      cell: ({ row }) => {
        const src = row.original.search_source
        if (!src) return emptyCell()
        return h(Badge, { color: getSearchSourceColor(src), size: 'sm' }, () =>
          getSearchSourceText(src),
        )
      },
    },
    {
      accessorKey: 'relevance',
      header: '相关性',
      meta: { class: { th: 'w-[70px]', td: 'w-[70px]' } },
      cell: ({ row }) =>
        row.original.relevance
          ? h(Badge, { color: getRelevanceColor(row.original.relevance), size: 'sm' }, () =>
              getRelevanceLabel(row.original.relevance),
            )
          : emptyCell(),
    },
    {
      accessorKey: 'sentiment',
      header: '情感',
      meta: { class: { th: 'w-[60px]', td: 'w-[60px]' } },
      cell: ({ row }) => {
        const s = row.original.sentiment
        if (s === null || s === undefined) return emptyCell()
        return h(Badge, { color: getSentimentColor(s), size: 'sm' }, () =>
          getSentimentText(s),
        )
      },
    },
    {
      accessorKey: 'article_type',
      header: '类型',
      meta: { class: { th: 'w-[60px]', td: 'w-[60px]' } },
      cell: ({ row }) => {
        const t = row.original.article_type
        if (!t) return emptyCell()
        return h('span', { class: 'text-sm text-gray-600 dark:text-gray-400' }, getTypeText(t))
      },
    },
    {
      accessorKey: 'summary',
      header: '摘要',
      meta: { class: { th: 'w-[200px]', td: 'w-[200px] whitespace-normal' } },
      cell: ({ row }) => {
        const text = row.original.summary || row.original.snippet
        if (!text) return emptyCell()
        return h(
          'div',
          { class: 'text-sm text-gray-600 dark:text-gray-400 leading-snug line-clamp-2' },
          text,
        )
      },
    },
    {
      accessorKey: 'published_at',
      header: '发布时间',
      meta: { class: { th: 'w-[90px]', td: 'w-[90px]' } },
      cell: ({ row }) => {
        if (!row.original.published_at) return emptyCell()
        return h(
          'span',
          { class: 'text-sm text-gray-500 whitespace-nowrap' },
          formatDate(row.original.published_at),
        )
      },
    },
  ]
})
</script>

<template>
  <div class="space-y-6">
    <div v-if="taskLoading" class="text-center py-8">
      <p class="text-gray-500">加载中...</p>
    </div>

    <template v-else-if="task">
      <!-- 页面头部 -->
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-3">
          <UButton
            variant="ghost"
            icon="i-heroicons-arrow-left"
            :to="backPath"
          />
          <div>
            <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
              {{ task.name }}
            </h1>
            <p class="text-gray-600 dark:text-gray-400 mt-1">
              任务详情
            </p>
          </div>
        </div>

        <ClientOnly>
          <div class="flex items-center gap-3">
            <UButton
              v-if="task.status === 'pending'"
              icon="i-heroicons-play"
              :loading="executing"
              @click="handleExecute"
            >
              执行任务
            </UButton>
            <UButton
              variant="ghost"
              icon="i-heroicons-arrow-path"
              :loading="refreshing"
              @click="handleRefresh"
            >
              刷新
            </UButton>
            <UButton
              v-if="hasPermission(PERMISSIONS.NEWS_TASK_DELETE) || task?.user_id === currentUserId"
              variant="outline"
              icon="i-heroicons-trash"
              color="error"
              @click="handleDelete"
            >
              删除
            </UButton>
          </div>
        </ClientOnly>
      </div>

      <!-- 任务信息卡片 -->
      <UCard>
        <template #header>
          <h2 class="text-lg font-semibold">
            任务信息
          </h2>
        </template>

        <dl class="space-y-2 text-sm">
          <!-- 任务名称 -->
          <div class="flex gap-3">
            <dt class="w-16 shrink-0 text-gray-500 dark:text-gray-400">
              任务名称
            </dt>
            <dd class="text-gray-900 dark:text-white font-medium">
              {{ task.name }}
            </dd>
          </div>

          <!-- 关键词 -->
          <div class="flex gap-3">
            <dt class="w-16 shrink-0 text-gray-500 dark:text-gray-400">
              关键词
            </dt>
            <dd class="text-gray-900 dark:text-white flex-1" :title="task.keywords">
              {{ task.keywords || '-' }}
            </dd>
          </div>

          <!-- 所属项目 -->
          <div class="flex gap-3">
            <dt class="w-16 shrink-0 text-gray-500 dark:text-gray-400">
              所属项目
            </dt>
            <dd>
              <UButton
                v-if="task.monitor_id"
                variant="link"
                size="sm"
                class="p-0 font-normal"
                :to="`/news-media/monitors/${task.monitor_id}`"
              >
                {{ task.monitor_name || '-' }}
              </UButton>
              <span v-else class="text-gray-900 dark:text-white">-</span>
            </dd>
          </div>

          <!-- 元信息 -->
          <div class="grid grid-cols-1 sm:grid-cols-4 gap-x-6 gap-y-2 pt-3 border-t border-gray-100 dark:border-gray-800">
            <div class="flex gap-3">
              <dt class="w-16 shrink-0 text-gray-500 dark:text-gray-400">
                阶段
              </dt>
              <dd>
                <UBadge :color="getPhaseColor(task.phase)" size="sm" variant="subtle">
                  {{ getPhaseText(task.phase) }}
                </UBadge>
              </dd>
            </div>
            <div class="flex gap-3">
              <dt class="w-16 shrink-0 text-gray-500 dark:text-gray-400">
                状态
              </dt>
              <dd>
                <UBadge :color="getStatusColor(task.status)" size="sm" variant="solid">
                  {{ getStatusText(task.status) }}
                </UBadge>
              </dd>
            </div>
            <div class="flex gap-3">
              <dt class="w-16 shrink-0 text-gray-500 dark:text-gray-400">
                文章数
              </dt>
              <dd class="text-gray-900 dark:text-white">
                {{ task.articles_count }}
              </dd>
            </div>
            <div class="flex gap-3">
              <dt class="w-16 shrink-0 text-gray-500 dark:text-gray-400">
                创建者
              </dt>
              <dd class="text-gray-900 dark:text-white">
                {{ task.user_username || '-' }}
              </dd>
            </div>
          </div>

          <!-- 时间信息 -->
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-x-6 gap-y-2 pt-3 border-t border-gray-100 dark:border-gray-800">
            <div class="flex gap-3">
              <dt class="w-16 shrink-0 text-gray-500 dark:text-gray-400">
                创建时间
              </dt>
              <dd class="text-gray-900 dark:text-white">
                {{ formatFullDate(task.created_at) }}
              </dd>
            </div>
          </div>
        </dl>

        <!-- 错误信息 -->
        <UAlert
          v-if="task.status === 'failed' && task.error_message"
          color="error"
          variant="soft"
          title="任务执行失败"
          :description="task.error_message"
          icon="i-heroicons-exclamation-triangle"
          class="mt-4"
        />
      </UCard>

      <!-- 渠道采集量分布（紧凑行内展示） -->
      <div
        v-if="channelStats && (channelStats.raw_total > 0 || channelStats.deduped_total > 0)"
        class="flex items-center gap-x-5 gap-y-2 flex-wrap px-4 py-2.5 rounded-lg border border-gray-200 bg-gray-50/60 dark:border-gray-700 dark:bg-gray-800/50 text-sm"
      >
        <span class="font-medium text-gray-700 dark:text-gray-300 shrink-0">渠道分布</span>

        <span
          v-for="ch in channelBreakdown"
          :key="ch.key"
          class="inline-flex items-baseline gap-1"
          :class="getChannelRaw(ch.key) > 0 ? 'text-gray-700 dark:text-gray-200' : 'text-gray-400 dark:text-gray-500'"
        >
          <span class="text-gray-500 dark:text-gray-400">{{ ch.label }}</span>
          <span class="font-semibold">{{ getChannelRaw(ch.key) }}</span>
          <span class="text-xs text-gray-400">/ 入库 {{ getChannelDeduped(ch.key) }}</span>
        </span>

        <span class="ml-auto text-xs text-gray-500 shrink-0">
          合计 原始 <span class="font-semibold text-gray-900 dark:text-white">{{ channelStats.raw_total }}</span>
          · 入库 <span class="font-semibold text-gray-900 dark:text-white">{{ channelStats.deduped_total }}</span>
        </span>
      </div>

      <!-- 文章列表 -->
      <UCard>
        <template #header>
          <div class="flex items-center justify-between">
            <h2 class="text-lg font-semibold">
              文章列表
              <span class="text-sm font-normal text-gray-500 ml-2">
                共 {{ totalArticles }} 篇
              </span>
            </h2>

            <div class="flex items-center gap-3">
              <USelect
                v-model="relevanceFilter"
                :items="[
                  { label: '全部相关性', value: 'all' },
                  { label: '高', value: 'high' },
                  { label: '中', value: 'medium' },
                  { label: '低', value: 'low' },
                ]"
                value-key="value"
                class="w-32"
              />
              <USelect
                v-model="tierFilter"
                :items="[
                  { label: '全部来源', value: 'all' },
                  { label: '权威央媒', value: 'tier1' },
                  { label: '行业门户', value: 'tier2' },
                  { label: '其他来源', value: 'tier3' },
                  { label: '微信公众号', value: 'wechat_mp' },
                ]"
                value-key="value"
                class="w-32"
              />
            </div>
          </div>
        </template>

        <ClientOnly>
          <template #fallback>
            <div class="text-center py-8">
              <p class="text-gray-600 dark:text-gray-400">加载文章列表中...</p>
            </div>
          </template>

          <UTable
            v-if="!articlesLoading && articles.length > 0"
            :data="articles"
            :columns="columns"
            class="w-full"
            :ui="{ base: 'w-full table-fixed' }"
          />

          <div v-else-if="articlesLoading" class="text-center py-8">
            <p class="text-gray-600 dark:text-gray-400">加载中...</p>
          </div>

          <div v-else class="text-center py-8">
            <p class="text-gray-600 dark:text-gray-400">暂无文章数据</p>
          </div>
        </ClientOnly>

        <template #footer>
          <ClientOnly>
            <template #fallback>
              <div class="flex justify-between items-center">
                <div class="h-4 bg-gray-200 rounded w-32 animate-pulse" />
                <div class="h-8 bg-gray-200 rounded w-64 animate-pulse" />
              </div>
            </template>

            <div class="flex justify-between items-center">
              <div class="text-sm text-gray-500 dark:text-gray-400">
                显示 {{ (currentPage - 1) * pageSize + 1 }} 到
                {{ Math.min(currentPage * pageSize, totalArticles) }} 共
                {{ totalArticles }} 条记录
              </div>
              <UPagination
                v-model:page="currentPage"
                :total="totalArticles"
                :items-per-page="pageSize"
                :sibling-count="2"
              />
            </div>
          </ClientOnly>
        </template>
      </UCard>

      <!-- 分析报告（Probe 摘要 / Collect 完整洞察） -->
      <UCard v-if="hasMeta || hasInsights">
        <template #header>
          <h2 class="text-lg font-semibold">分析报告</h2>
        </template>

        <!-- Meta 概要 -->
        <div v-if="hasMeta" class="mb-6">
          <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 text-sm">
            <div class="p-3 bg-gray-50 dark:bg-gray-800 rounded">
              <span class="text-gray-500">文章总数</span>
              <p class="text-xl font-bold mt-1">{{ analysisResult?.meta?.articles_total ?? '-' }}</p>
            </div>
            <div class="p-3 bg-gray-50 dark:bg-gray-800 rounded">
              <span class="text-gray-500">相关文章</span>
              <p class="text-xl font-bold mt-1">{{ analysisResult?.meta?.articles_analyzed ?? analysisResult?.meta?.articles_relevant ?? '-' }}</p>
            </div>
            <div v-if="analysisResult?.meta?.articles_crawled !== undefined" class="p-3 bg-gray-50 dark:bg-gray-800 rounded">
              <span class="text-gray-500">成功抓取</span>
              <p class="text-xl font-bold mt-1">{{ analysisResult?.meta?.articles_crawled }}</p>
            </div>
            <div v-if="analysisResult?.meta?.source_tier_distribution" class="p-3 bg-gray-50 dark:bg-gray-800 rounded">
              <span class="text-gray-500">来源分布</span>
              <p class="text-sm font-medium mt-1">
                权威 {{ analysisResult.meta.source_tier_distribution.tier1 ?? 0 }} /
                行业 {{ analysisResult.meta.source_tier_distribution.tier2 ?? 0 }} /
                其他 {{ analysisResult.meta.source_tier_distribution.tier3 ?? 0 }} /
                公众号 {{ analysisResult.meta.source_tier_distribution.wechat_mp ?? 0 }}
              </p>
            </div>
          </div>
        </div>

        <!-- 报道覆盖度 -->
        <ClientOnly>
          <div v-if="analysisResult?.coverage" class="mb-6">
            <h3 class="text-base font-semibold mb-3">报道覆盖度</h3>
            <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 text-sm">
              <div class="p-3 bg-blue-50 dark:bg-blue-900/20 rounded">
                <span class="text-gray-500">MCI 指数</span>
                <p class="text-xl font-bold mt-1 text-blue-700 dark:text-blue-400">
                  {{ analysisResult.coverage.media_coverage_index ?? '-' }}
                </p>
              </div>
              <div class="p-3 bg-blue-50 dark:bg-blue-900/20 rounded">
                <span class="text-gray-500">报道强度</span>
                <p class="text-lg font-semibold mt-1">{{ analysisResult.coverage.intensity || '-' }}</p>
              </div>
              <div class="p-3 bg-blue-50 dark:bg-blue-900/20 rounded">
                <span class="text-gray-500">趋势</span>
                <p class="text-lg font-semibold mt-1">{{ analysisResult.coverage.trend || '-' }}</p>
              </div>
            </div>
            <p v-if="analysisResult.coverage.summary" class="mt-3 text-sm text-gray-600 dark:text-gray-400">
              {{ analysisResult.coverage.summary }}
            </p>
          </div>

          <!-- 情感分布 -->
          <div v-if="analysisResult?.sentiment" class="mb-6">
            <h3 class="text-base font-semibold mb-3">情感分布</h3>
            <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 text-sm">
              <div class="p-3 bg-gray-50 dark:bg-gray-800 rounded">
                <span class="text-gray-500">综合情感</span>
                <p class="text-xl font-bold mt-1">{{ formatSentimentScore(analysisResult.sentiment.overall) }}</p>
              </div>
              <div v-if="analysisResult.sentiment.distribution" class="p-3 bg-gray-50 dark:bg-gray-800 rounded">
                <span class="text-gray-500">正/中/负</span>
                <p class="font-medium mt-1">
                  <span class="text-green-600">{{ analysisResult.sentiment.distribution.positive ?? 0 }}</span> /
                  <span class="text-gray-600">{{ analysisResult.sentiment.distribution.neutral ?? 0 }}</span> /
                  <span class="text-red-600">{{ analysisResult.sentiment.distribution.negative ?? 0 }}</span>
                </p>
              </div>
              <div v-if="analysisResult.sentiment.by_source_tier" class="p-3 bg-gray-50 dark:bg-gray-800 rounded col-span-2">
                <span class="text-gray-500">按来源等级</span>
                <p class="font-medium mt-1 text-sm">
                  权威: {{ formatSentimentScore(analysisResult.sentiment.by_source_tier.tier1) }} |
                  行业: {{ formatSentimentScore(analysisResult.sentiment.by_source_tier.tier2) }} |
                  其他: {{ formatSentimentScore(analysisResult.sentiment.by_source_tier.tier3) }}
                </p>
              </div>
            </div>
          </div>

          <!-- 叙事聚类 -->
          <div v-if="analysisResult?.narratives?.length" class="mb-6">
            <h3 class="text-base font-semibold mb-3">叙事主题</h3>
            <div class="space-y-3">
              <div
                v-for="(narrative, idx) in analysisResult.narratives"
                :key="idx"
                class="p-3 border border-gray-200 dark:border-gray-700 rounded"
              >
                <div class="flex items-center justify-between mb-1">
                  <span class="font-medium">{{ narrative.theme }}</span>
                  <div class="flex items-center gap-2 text-sm text-gray-500">
                    <span>{{ narrative.article_count }} 篇</span>
                    <UBadge :color="getSentimentColor(narrative.sentiment)" size="sm">
                      {{ formatSentimentScore(narrative.sentiment) }}
                    </UBadge>
                  </div>
                </div>
                <p class="text-sm text-gray-600 dark:text-gray-400">{{ narrative.summary }}</p>
                <div v-if="narrative.representative_titles?.length" class="mt-2 text-xs text-gray-500">
                  代表文章: {{ narrative.representative_titles.join('、') }}
                </div>
              </div>
            </div>
          </div>

          <!-- 实体全景 -->
          <div v-if="analysisResult?.entities?.length" class="mb-6">
            <h3 class="text-base font-semibold mb-3">实体分析</h3>
            <div class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead>
                  <tr class="border-b dark:border-gray-700">
                    <th class="text-left py-2 px-3">实体</th>
                    <th class="text-left py-2 px-3">角色</th>
                    <th class="text-right py-2 px-3">提及数</th>
                    <th class="text-right py-2 px-3">来源数</th>
                    <th class="text-right py-2 px-3">情感</th>
                    <th class="text-left py-2 px-3">关键论述</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(entity, idx) in analysisResult.entities"
                    :key="idx"
                    class="border-b dark:border-gray-700"
                  >
                    <td class="py-2 px-3 font-medium">{{ entity.name }}</td>
                    <td class="py-2 px-3">
                      <UBadge
                        :color="entity.role === 'target' ? 'primary' : entity.role === 'competitor' ? 'warning' : 'neutral'"
                        size="sm"
                      >
                        {{ entity.role }}
                      </UBadge>
                    </td>
                    <td class="py-2 px-3 text-right">{{ entity.mention_count }}</td>
                    <td class="py-2 px-3 text-right">{{ entity.source_count }}</td>
                    <td class="py-2 px-3 text-right">
                      <UBadge :color="getSentimentColor(entity.sentiment)" size="sm">
                        {{ formatSentimentScore(entity.sentiment) }}
                      </UBadge>
                    </td>
                    <td class="py-2 px-3 text-gray-600 dark:text-gray-400 max-w-[300px]">
                      {{ entity.key_claims?.join('；') || '-' }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- 竞品格局 -->
          <div v-if="analysisResult?.competitive_landscape" class="mb-6">
            <h3 class="text-base font-semibold mb-3">竞品格局</h3>
            <p v-if="analysisResult.competitive_landscape.positioning_summary" class="text-sm text-gray-600 dark:text-gray-400 mb-3">
              {{ analysisResult.competitive_landscape.positioning_summary }}
            </p>
            <div v-if="analysisResult.competitive_landscape.entities_mentioned?.length" class="flex flex-wrap gap-2">
              <div
                v-for="(ce, idx) in analysisResult.competitive_landscape.entities_mentioned"
                :key="idx"
                class="px-3 py-1.5 bg-gray-50 dark:bg-gray-800 rounded text-sm"
              >
                <span class="font-medium">{{ ce.name }}</span>
                <span class="text-gray-500 ml-1">{{ ce.mentions }}次</span>
                <UBadge :color="getSentimentColor(ce.sentiment)" size="sm" class="ml-1">
                  {{ formatSentimentScore(ce.sentiment) }}
                </UBadge>
              </div>
            </div>
          </div>

          <!-- 关键引述 -->
          <div v-if="analysisResult?.key_quotes?.length" class="mb-6">
            <h3 class="text-base font-semibold mb-3">关键引述</h3>
            <div class="space-y-3">
              <div
                v-for="(quote, idx) in analysisResult.key_quotes"
                :key="idx"
                class="p-3 border-l-4 border-blue-400 bg-blue-50 dark:bg-blue-900/20 rounded-r"
              >
                <p class="text-sm italic">&ldquo;{{ quote.quote }}&rdquo;</p>
                <p class="text-xs text-gray-500 mt-1">
                  &mdash; {{ quote.speaker }}
                  <span v-if="quote.source_name" class="ml-1">| {{ quote.source_name }}</span>
                  <span v-if="quote.context" class="ml-1">| {{ quote.context }}</span>
                </p>
              </div>
            </div>
          </div>
        </ClientOnly>
      </UCard>
    </template>

    <div v-else class="text-center py-8">
      <p class="text-gray-500">任务不存在</p>
    </div>
  </div>
</template>
