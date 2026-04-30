<script setup lang="ts">
import { h, ref, computed, nextTick, watch, type Component } from 'vue'
import type { TableColumn } from '@nuxt/ui'
import type { EChartsOption } from 'echarts'
import { UButton, UBadge } from '#components'
import { PERMISSIONS } from '~/config/permissions'

definePageMeta({
  layout: 'default',
})

const route = useRoute()
const taskId = Number(route.params.id)
const { currentUserId, hasPermission } = usePermissions()

const { getTask, executeTask, deleteTask, getTaskArticles, getTaskChannelStats } = useNewsTasks()

// silent404: 任务可能被级联删除（Monitor 删除 → news_tasks cascade）导致路由残留。
// 静默处理 404，避免三条并发 404 各弹一条 error toast 触发 vue:error hook 级联
// （error-handler.client.ts 的 toast 再次挂载会把同一个坏 render 再跑一次，形成
// 渲染→error→toast→渲染 的无限循环，最终 Nuxt 显示 500 兜底）。
const { data: task, pending: taskLoading, refresh: refreshTask } = getTask(taskId, { silent404: true })
const { data: channelStats, refresh: refreshChannelStats } = getTaskChannelStats(taskId, { silent404: true })

type ChannelKey = 'baidu' | 'sogou' | 'wechat_mp'

const channelBreakdown: { key: ChannelKey; label: string }[] = [
  { key: 'baidu', label: '百度' },
  { key: 'sogou', label: '搜狗' },
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
} = getTaskArticles(taskId, articleParams, { silent404: true })

const articles = computed(() => articlesData.value?.items || [])
const totalArticles = computed(() => articlesData.value?.total || 0)

// 404 守护：任务已被删除时，提示并跳回列表，避免下游组件在 task=null 时进入
// 无限 error toast → vue:error hook → 再渲染的循环（详见上面 silent404 说明）。
const notFoundRedirected = ref(false)
const toast = useToast()
watch(
  [task, taskLoading],
  ([t, loading]) => {
    if (!loading && t === null && !notFoundRedirected.value) {
      notFoundRedirected.value = true
      toast.add({
        title: '任务不存在',
        description: '该任务可能已被删除，返回任务列表',
        color: 'warning',
      })
      navigateTo('/news-media/tasks')
    }
  },
  { immediate: true },
)

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

// ========== 任务统计（task.analysis_result.meta 由 _compute_task_stats 派生） ==========

const meta = computed(() => task.value?.analysis_result?.meta ?? null)

// 标注派生信号是否可用：collect 完成且至少有一篇被打过 relevance
const hasTagging = computed(() => {
  const m = meta.value
  if (!m) return false
  return m.articles_high + m.articles_medium + m.articles_low > 0
})

type TierKey = 'tier1' | 'tier2' | 'tier3' | 'wechat_mp'
const TIER_KEYS: TierKey[] = ['tier1', 'tier2', 'tier3', 'wechat_mp']

interface TierRow {
  key: TierKey
  count: number
  widthPct: number
  sentiment: number | null
}

const tierRows = computed<TierRow[]>(() => {
  const m = meta.value
  if (!m) return []
  const counts = TIER_KEYS.map(t => m.source_tier_distribution[t] || 0)
  const max = Math.max(...counts, 1)
  return TIER_KEYS.map((t, i) => ({
    key: t,
    count: counts[i] ?? 0,
    widthPct: max > 0 ? Math.max(((counts[i] ?? 0) / max) * 100, counts[i] ? 4 : 0) : 0,
    sentiment: m.sentiment_by_tier[t],
  }))
})

const hasCoverageDays = computed(() => (meta.value?.coverage_by_day?.length ?? 0) > 1)

// Coverage by Day 柱状图
const { chartRef: coverageChartRef, initChart: initCoverageChart, setOption: setCoverageOption }
  = useCharts()

const renderCoverageChart = () => {
  const m = meta.value
  if (!m || !m.coverage_by_day || m.coverage_by_day.length === 0) return
  if (!coverageChartRef.value) return
  if (!initCoverageChart()) return

  // 兼容历史数据：旧 task 的 coverage_by_day 缺 count_by_tier 字段，
  // fallback 把整日 count 归到 tier3（重跑 task 后会正确分层）
  const safeTierBreakdown = (d: NewsTaskCoverageDay): { tier1: number; tier2: number; tier3: number; wechat_mp: number } => {
    if (d.count_by_tier) return d.count_by_tier
    return { tier1: 0, tier2: 0, tier3: d.count ?? 0, wechat_mp: 0 }
  }

  const option: EChartsOption = {
    animation: false,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: unknown) => {
        const arr = params as Array<{ name: string; value: number; dataIndex: number }>
        if (!arr || arr.length === 0) return ''
        const day = m.coverage_by_day[arr[0]!.dataIndex]
        if (!day) return ''
        const sent = day.sentiment_avg !== null
          ? `<br/>情感均值：${day.sentiment_avg.toFixed(2)}`
          : ''
        return `${day.date}<br/>报道数：${day.count}${sent}`
      },
    },
    legend: { top: 0, textStyle: { fontSize: 11 } },
    grid: { left: 8, right: 12, top: 30, bottom: 8, containLabel: true },
    xAxis: {
      type: 'category',
      data: m.coverage_by_day.map(d => d.date),
      axisLabel: {
        fontSize: 11,
        rotate: m.coverage_by_day.length > 8 ? 35 : 0,
        margin: 10,
        hideOverlap: true,
      },
    },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      { name: 'tier1 权威', type: 'bar', stack: 'all', data: m.coverage_by_day.map(d => safeTierBreakdown(d).tier1), itemStyle: { color: '#ef4444' }, barMaxWidth: 24 },
      { name: 'tier2 行业', type: 'bar', stack: 'all', data: m.coverage_by_day.map(d => safeTierBreakdown(d).tier2), itemStyle: { color: '#f59e0b' } },
      { name: 'tier3 其他', type: 'bar', stack: 'all', data: m.coverage_by_day.map(d => safeTierBreakdown(d).tier3), itemStyle: { color: '#9ca3af' } },
      { name: '公众号', type: 'bar', stack: 'all', data: m.coverage_by_day.map(d => safeTierBreakdown(d).wechat_mp), itemStyle: { color: '#10b981' } },
    ],
  }
  setCoverageOption(option)
}

watch(
  [meta, coverageChartRef],
  () => {
    if (meta.value && coverageChartRef.value && hasCoverageDays.value) {
      nextTick(renderCoverageChart)
    }
  },
  { immediate: true },
)

const sentimentTextClass = (score: number | null): string => {
  if (score === null) return 'text-gray-400'
  if (score > 0) return 'text-green-600 dark:text-green-400'
  if (score < 0) return 'text-red-600 dark:text-red-400'
  return 'text-gray-600 dark:text-gray-300'
}

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

const getTierColor = (tier: string): BadgeColor => {
  const map: Record<string, BadgeColor> = { tier1: 'error', tier2: 'warning', tier3: 'neutral', wechat_mp: 'success' }
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

      <!-- 任务统计（task.analysis_result.meta 由 _compute_task_stats 派生，纯 SQL） -->
      <UCard v-if="meta">
        <template #header>
          <h2 class="text-lg font-semibold">任务统计</h2>
        </template>

        <ClientOnly>
          <!-- 概要数字 -->
          <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 text-sm">
            <div class="p-3 bg-gray-50 dark:bg-gray-800 rounded">
              <span class="text-gray-500">文章总数</span>
              <p class="text-xl font-bold mt-1">{{ meta.articles_total }}</p>
            </div>
            <div v-if="hasTagging" class="p-3 bg-gray-50 dark:bg-gray-800 rounded">
              <span class="text-gray-500">高/中/低相关</span>
              <p class="text-base font-medium mt-1">
                <span class="text-green-600 dark:text-green-400">{{ meta.articles_high }}</span>
                /
                <span class="text-amber-600 dark:text-amber-400">{{ meta.articles_medium }}</span>
                /
                <span class="text-gray-500">{{ meta.articles_low }}</span>
              </p>
            </div>
            <div v-if="meta.articles_crawled !== undefined" class="p-3 bg-gray-50 dark:bg-gray-800 rounded">
              <span class="text-gray-500">成功抓取</span>
              <p class="text-xl font-bold mt-1">{{ meta.articles_crawled }}</p>
            </div>
            <div v-if="hasTagging && meta.sentiment_overall !== null" class="p-3 bg-gray-50 dark:bg-gray-800 rounded">
              <span class="text-gray-500">综合情感</span>
              <p class="text-xl font-bold mt-1" :class="sentimentTextClass(meta.sentiment_overall)">
                {{ formatSentimentScore(meta.sentiment_overall) }}
              </p>
            </div>
          </div>

          <!-- 媒介金字塔（来源分层 × 情感） -->
          <div v-if="hasTagging" class="mt-6">
            <h3 class="text-base font-semibold mb-3">媒介金字塔</h3>
            <div class="space-y-2">
              <div v-for="row in tierRows" :key="row.key" class="flex items-center gap-3">
                <div class="w-20 shrink-0">
                  <UBadge :color="getTierColor(row.key)" variant="subtle" size="sm">
                    {{ getTierLabel(row.key) }}
                  </UBadge>
                </div>
                <div class="flex-1 bg-gray-100 dark:bg-gray-800 rounded h-8 relative overflow-hidden">
                  <div
                    class="h-full bg-blue-200 dark:bg-blue-900/40 transition-all"
                    :style="{ width: row.widthPct + '%' }"
                  />
                  <div class="absolute inset-0 flex items-center px-3 text-sm">
                    <span class="font-medium">{{ row.count }}</span>
                    <span class="text-gray-500 ml-1">篇</span>
                    <span v-if="row.sentiment !== null" class="ml-auto text-xs">
                      情感
                      <span class="font-medium" :class="sentimentTextClass(row.sentiment)">
                        {{ formatSentimentScore(row.sentiment) }}
                      </span>
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 情感与类型分布 -->
          <div v-if="hasTagging" class="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
            <div class="p-3 bg-gray-50 dark:bg-gray-800 rounded">
              <span class="text-gray-500">情感分布（正/中/负）</span>
              <p class="font-medium mt-1">
                <span class="text-green-600 dark:text-green-400">{{ meta.sentiment_distribution.positive }}</span>
                /
                <span class="text-gray-600 dark:text-gray-300">{{ meta.sentiment_distribution.neutral }}</span>
                /
                <span class="text-red-600 dark:text-red-400">{{ meta.sentiment_distribution.negative }}</span>
              </p>
            </div>
            <div class="p-3 bg-gray-50 dark:bg-gray-800 rounded">
              <span class="text-gray-500">类型分布（报道/评论/PR/分析）</span>
              <p class="font-medium mt-1">
                {{ meta.article_type_distribution.report }} /
                {{ meta.article_type_distribution.opinion }} /
                {{ meta.article_type_distribution.pr }} /
                {{ meta.article_type_distribution.analysis }}
              </p>
            </div>
          </div>

          <!-- 报道时间分布 柱状图 -->
          <div v-if="hasCoverageDays" class="mt-6">
            <h3 class="text-base font-semibold mb-3">报道时间分布</h3>
            <div ref="coverageChartRef" class="w-full h-56" />
          </div>

          <!-- 关键引述墙（task 内 top） -->
          <div v-if="hasTagging && meta.top_quotes.length > 0" class="mt-6">
            <h3 class="text-base font-semibold mb-3">
              关键引述
              <span class="text-xs font-normal text-gray-500 ml-2">
                按来源权威度排（top {{ meta.top_quotes.length }}）
              </span>
            </h3>
            <div class="space-y-3">
              <div
                v-for="(q, idx) in meta.top_quotes"
                :key="idx"
                class="p-3 border-l-4 border-blue-400 bg-blue-50 dark:bg-blue-900/20 rounded-r"
              >
                <p class="text-sm italic">&ldquo;{{ q.quote }}&rdquo;</p>
                <p class="text-xs text-gray-500 mt-1 flex items-center flex-wrap gap-1">
                  <span>&mdash; {{ q.speaker }}</span>
                  <span class="ml-1">| {{ q.source_name }}</span>
                  <UBadge :color="getTierColor(q.source_tier)" size="sm" variant="subtle" class="ml-1">
                    {{ getTierLabel(q.source_tier) }}
                  </UBadge>
                </p>
              </div>
            </div>
          </div>

          <!-- 高频实体（原始计数，未归一） -->
          <div v-if="hasTagging && meta.top_entities_raw.length > 0" class="mt-6">
            <h3 class="text-base font-semibold mb-2">
              高频实体
              <span class="text-xs font-normal text-gray-500 ml-2">
                top {{ meta.top_entities_raw.length }}，原始计数（未跨变体归一，归一在 slice 层）
              </span>
            </h3>
            <div class="flex flex-wrap gap-2">
              <UBadge
                v-for="ent in meta.top_entities_raw"
                :key="ent.name"
                variant="subtle"
              >
                {{ ent.name }} · {{ ent.mention_count }}次
              </UBadge>
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
