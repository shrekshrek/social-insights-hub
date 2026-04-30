<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type { EChartsOption } from 'echarts'
import type {
  NewsSliceEntity,
  NewsSliceEventCluster,
  NewsSliceQuote,
  SpeakerRole,
  TierKey,
} from '../../../../types'
import { PERMISSIONS } from '~/config/permissions'

definePageMeta({ layout: 'default' })

const route = useRoute()
const sliceId = Number(route.params.id)

const { hasPermission } = usePermissions()
const { getSlice, analyzeSlice, deleteSlice: deleteSliceApi } = useNewsSlices()
const { data: slice, pending: loading, refresh } = getSlice(sliceId)

const analyzing = ref(false)

const handleAnalyze = async () => {
  if (!slice.value) return
  analyzing.value = true
  try {
    await analyzeSlice(sliceId, {
      analysis_goal: slice.value.name,
      subject: slice.value.name,
    })
    await refresh()
  } catch {
    // error already handled
  } finally {
    analyzing.value = false
  }
}

const handleDelete = async () => {
  if (!slice.value) return
  const { $confirm } = useNuxtApp()
  const confirmed = await $confirm({
    title: '删除切片',
    message: `确定要删除切片 "${slice.value.name}" 吗？此操作不可恢复。`,
    confirmText: '删除',
    cancelText: '取消',
    type: 'error',
  })
  if (!confirmed) return

  try {
    await deleteSliceApi(sliceId)
    await navigateTo(`/news-media/monitors/${slice.value.monitor_id}`)
  } catch {
    // error already handled
  }
}

// ========== 状态/格式化辅助 ==========

type BadgeColor = 'neutral' | 'primary' | 'secondary' | 'success' | 'info' | 'warning' | 'error'

const statusColor = (s: string): BadgeColor => ({
  pending: 'neutral', analyzing: 'info', completed: 'success', failed: 'error',
} as Record<string, BadgeColor>)[s] || 'neutral'

const statusText = (s: string) => ({
  pending: '待分析', analyzing: '分析中', completed: '已完成', failed: '失败',
} as Record<string, string>)[s] || s

const formatDate = (iso: string) => new Date(iso).toLocaleString('zh-CN', {
  year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
})

const fmtSent = (s: number | null | undefined): string => {
  if (s === null || s === undefined) return '-'
  return s > 0 ? `+${s.toFixed(2)}` : s.toFixed(2)
}

const sentimentClass = (s: number | null | undefined): string => {
  if (s === null || s === undefined) return 'text-gray-400'
  if (s > 0) return 'text-green-600 dark:text-green-400'
  if (s < 0) return 'text-red-600 dark:text-red-400'
  return 'text-gray-600 dark:text-gray-300'
}

const tierLabel = (t: string): string => ({
  tier1: '权威央媒', tier2: '行业门户', tier3: '其他来源', wechat_mp: '微信公众号',
} as Record<string, string>)[t] || t

const tierColor = (t: string): BadgeColor => ({
  tier1: 'error', tier2: 'warning', tier3: 'neutral', wechat_mp: 'success',
} as Record<string, BadgeColor>)[t] || 'neutral'

const speakerRoleLabel = (r: string): string => ({
  official: '官方/监管', executive: '高管', analyst: '分析师', kol: 'KOL', other: '其他',
} as Record<string, string>)[r] || r

const speakerRoleColor = (r: string): BadgeColor => ({
  official: 'error', executive: 'warning', analyst: 'info', kol: 'secondary', other: 'neutral',
} as Record<string, BadgeColor>)[r] || 'neutral'

const entityRoleLabel = (r: string): string => ({
  target: '主体', competitor: '竞品', context: '上下文',
} as Record<string, string>)[r] || r

const entityRoleColor = (r: string): BadgeColor => ({
  target: 'primary', competitor: 'warning', context: 'neutral',
} as Record<string, BadgeColor>)[r] || 'neutral'

// ========== 数据派生 ==========

const result = computed(() => slice.value?.result_data ?? null)
const descriptive = computed(() => result.value?.descriptive ?? null)
const briefing = computed(() => result.value?.page_synthesis?.briefing ?? null)
const eventTitles = computed(() => result.value?.page_synthesis?.event_titles ?? {})
const entities = computed(() => result.value?.entities ?? [])
const quotes = computed(() => result.value?.quotes ?? [])
const eventClusters = computed(() => result.value?.event_clusters ?? [])
const mediaLandscape = computed(() => result.value?.media_landscape ?? null)
const competitive = computed(() => result.value?.competitive ?? null)

const TIER_KEYS: TierKey[] = ['tier1', 'tier2', 'tier3', 'wechat_mp']

const entitiesByRole = computed(() => {
  const grouped: Record<string, NewsSliceEntity[]> = { target: [], competitor: [], context: [] }
  for (const e of entities.value) {
    if (grouped[e.role]) grouped[e.role]!.push(e)
  }
  return grouped
})

const quotesByRole = computed(() => {
  const grouped: Record<SpeakerRole, NewsSliceQuote[]>
    = { official: [], executive: [], analyst: [], kol: [], other: [] }
  for (const q of quotes.value) {
    if (grouped[q.speaker_role]) grouped[q.speaker_role]!.push(q)
  }
  return grouped
})

const sourcePyramid = computed(() => {
  const pyramid = mediaLandscape.value?.source_pyramid ?? []
  const max = Math.max(...pyramid.map(t => t.article_count), 1)
  return pyramid.map(t => ({
    ...t,
    // 兼容历史 slice：旧 schema 用 representative_titles（已删），新 schema 用 representative_articles
    representative_articles: t.representative_articles ?? [],
    top_source_names: t.top_source_names ?? [],
    widthPct: max > 0 ? Math.max((t.article_count / max) * 100, t.article_count ? 4 : 0) : 0,
  }))
})

const overlapTotal = computed(() => {
  const d = descriptive.value?.cross_task_overlap?.distribution
  if (!d) return 0
  return d.single_task + d.two_tasks + d.three_plus
})

const highOverlapArticles = computed(
  () => descriptive.value?.cross_task_overlap?.high_overlap_articles ?? [],
)

// ========== 文章下钻 modal 状态 ==========

const articleModalOpen = ref(false)
const articleModalIds = ref<number[]>([])
const articleModalTitle = ref<string>('')
const articleModalSubtitle = ref<string>('')

const openArticleModal = (ids: number[], title: string, subtitle = '') => {
  if (ids.length === 0) return
  articleModalIds.value = ids
  articleModalTitle.value = title
  articleModalSubtitle.value = subtitle
  articleModalOpen.value = true
}

// ========== 时序图（coverage + sentiment） ==========

const {
  chartRef: coverageChartRef,
  initChart: initCoverageChart,
  setOption: setCoverageOption,
} = useCharts()
const {
  chartRef: sentimentChartRef,
  initChart: initSentimentChart,
  setOption: setSentimentOption,
} = useCharts()

const renderCoverageTimeseries = () => {
  const ts = descriptive.value?.coverage_timeseries
  if (!ts || ts.length === 0 || !coverageChartRef.value) return
  if (!initCoverageChart()) return
  const dates = ts.map(t => t.date)
  const opt: EChartsOption = {
    animation: false,
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { top: 0, textStyle: { fontSize: 11 } },
    grid: { left: 8, right: 12, top: 30, bottom: 8, containLabel: true },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: {
        fontSize: 11,
        rotate: dates.length > 8 ? 35 : 0,
        margin: 10,
        hideOverlap: true,
      },
    },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      { name: 'tier1 权威', type: 'bar', stack: 'all', data: ts.map(t => t.count_by_tier.tier1), itemStyle: { color: '#ef4444' }, barMaxWidth: 24 },
      { name: 'tier2 行业', type: 'bar', stack: 'all', data: ts.map(t => t.count_by_tier.tier2), itemStyle: { color: '#f59e0b' } },
      { name: 'tier3 其他', type: 'bar', stack: 'all', data: ts.map(t => t.count_by_tier.tier3), itemStyle: { color: '#9ca3af' } },
      { name: '公众号', type: 'bar', stack: 'all', data: ts.map(t => t.count_by_tier.wechat_mp), itemStyle: { color: '#10b981' } },
    ],
  }
  setCoverageOption(opt)
}

const renderSentimentTimeseries = () => {
  const ts = descriptive.value?.sentiment_timeseries
  if (!ts || ts.length === 0 || !sentimentChartRef.value) return
  if (!initSentimentChart()) return
  const dates = ts.map(t => t.date)
  const opt: EChartsOption = {
    animation: false,
    tooltip: { trigger: 'axis' },
    legend: { top: 0, textStyle: { fontSize: 11 } },
    grid: { left: 8, right: 12, top: 30, bottom: 8, containLabel: true },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: {
        fontSize: 11,
        rotate: dates.length > 8 ? 35 : 0,
        margin: 10,
        hideOverlap: true,
      },
    },
    yAxis: { type: 'value', min: -2, max: 2, interval: 1 },
    series: [
      { name: '等权', type: 'line', data: ts.map(t => t.sentiment_avg), itemStyle: { color: '#6366f1' }, lineStyle: { color: '#6366f1' }, smooth: true, connectNulls: true },
      { name: 'tier 加权', type: 'line', data: ts.map(t => t.sentiment_weighted_by_tier), itemStyle: { color: '#ec4899' }, lineStyle: { color: '#ec4899' }, smooth: true, connectNulls: true },
    ],
  }
  setSentimentOption(opt)
}

watch(
  [descriptive, coverageChartRef, sentimentChartRef],
  () => {
    nextTick(() => {
      renderCoverageTimeseries()
      renderSentimentTimeseries()
    })
  },
  { immediate: true },
)

// ========== article_id → title 索引（用于 events / quote 文章引用） ==========
// 从已有的 entities/event_clusters 中提取 article_ids，触发查询；
// 为简化，先不主动加载 article 标题（需要单独 endpoint）。前端展示文章 ID 即可，下钻在后续 P3+ 增强。

// ========== 工具：根据 entity 找代表性 article_ids ==========

const playerRoleColor = (role: string): BadgeColor => entityRoleColor(role)

const formatPct = (v: number) => `${(v * 100).toFixed(1)}%`

// 用于事件展示
const eventTitle = (cluster: NewsSliceEventCluster): string => {
  return eventTitles.value[String(cluster.cluster_id)]?.title || `事件 #${cluster.cluster_id + 1}`
}

const eventFrame = (cluster: NewsSliceEventCluster): string | null => {
  return eventTitles.value[String(cluster.cluster_id)]?.dominant_frame || null
}

// 截断时间戳到 YYYY-MM-DD
const dateOnly = (iso: string | null): string => {
  if (!iso) return '-'
  return iso.length >= 10 ? iso.slice(0, 10) : iso
}

</script>

<template>
  <div class="space-y-6">
    <div v-if="loading" class="text-center py-8">
      <p class="text-gray-500">加载中...</p>
    </div>

    <template v-else-if="slice">
      <!-- 头部 -->
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-3">
          <UButton
            variant="ghost"
            icon="i-heroicons-arrow-left"
            :to="`/news-media/monitors/${slice.monitor_id}`"
          />
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
            切片详情
          </h1>
        </div>

        <ClientOnly>
          <div class="flex items-center gap-3">
            <UButton
              v-if="(slice.status === 'completed' || slice.status === 'failed') && hasPermission(PERMISSIONS.ANALYSIS_WRITE)"
              icon="i-heroicons-sparkles"
              :loading="analyzing"
              @click="handleAnalyze"
            >
              重新分析
            </UButton>
            <UButton
              color="error"
              variant="outline"
              icon="i-heroicons-trash"
              @click="handleDelete"
            >
              删除
            </UButton>
          </div>
        </ClientOnly>
      </div>

      <!-- 基本信息 -->
      <UCard>
        <template #header>
          <h2 class="text-lg font-medium text-gray-900 dark:text-white">基本信息</h2>
        </template>

        <dl class="grid grid-cols-2 lg:grid-cols-4 gap-4 text-sm">
          <div>
            <dt class="text-gray-500">切片名称</dt>
            <dd class="font-medium mt-1">{{ slice.name }}</dd>
          </div>
          <div>
            <dt class="text-gray-500">状态</dt>
            <dd class="mt-1">
              <UBadge :color="statusColor(slice.status)" size="sm" variant="subtle">
                {{ statusText(slice.status) }}
              </UBadge>
            </dd>
          </div>
          <div>
            <dt class="text-gray-500">包含任务</dt>
            <dd class="font-medium mt-1">{{ slice.included_task_ids.length }} 个</dd>
          </div>
          <div>
            <dt class="text-gray-500">创建时间</dt>
            <dd class="mt-1">{{ formatDate(slice.created_at) }}</dd>
          </div>
        </dl>

        <div v-if="slice.error_message" class="mt-4 p-3 bg-red-50 dark:bg-red-900/20 rounded text-sm text-red-600 dark:text-red-400">
          {{ slice.error_message }}
        </div>
      </UCard>

      <UCard v-if="slice.status === 'analyzing'">
        <div class="text-center py-6 text-gray-400 text-sm">正在运行综合分析...</div>
      </UCard>

      <template v-if="slice.status === 'completed' && descriptive">
        <ClientOnly>
          <!-- Briefing 卡（Pass 2 失败时折叠） -->
          <UCard v-if="briefing && (briefing.headline || briefing.key_findings?.length)">
            <template #header>
              <h2 class="text-lg font-medium text-gray-900 dark:text-white">简报</h2>
            </template>
            <p v-if="briefing.headline" class="text-base font-medium mb-3">
              {{ briefing.headline }}
            </p>
            <ul v-if="briefing.key_findings?.length" class="space-y-1.5 text-sm text-gray-700 dark:text-gray-300 list-disc pl-5">
              <li v-for="(kf, idx) in briefing.key_findings" :key="idx">{{ kf }}</li>
            </ul>
            <div v-if="briefing.risks?.length" class="mt-4">
              <p class="text-sm font-medium text-red-600 dark:text-red-400 mb-1.5">风险提示</p>
              <ul class="space-y-1 text-sm text-red-600 dark:text-red-400 list-disc pl-5">
                <li v-for="(r, idx) in briefing.risks" :key="idx">{{ r }}</li>
              </ul>
            </div>
          </UCard>

          <!-- 概要数字 + 跨任务重叠 -->
          <UCard>
            <template #header>
              <h2 class="text-lg font-medium text-gray-900 dark:text-white">数据概要</h2>
            </template>
            <div class="grid grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-3">
              <div class="flex items-baseline gap-2">
                <span class="text-2xl font-mono font-semibold text-gray-900 dark:text-white">
                  {{ descriptive.articles_unique }}
                </span>
                <span class="text-xs text-gray-500">入库文章（去重后）</span>
              </div>
              <div class="flex items-baseline gap-2">
                <span class="text-2xl font-mono font-semibold text-gray-900 dark:text-white">
                  {{ descriptive.articles_filtered }}
                </span>
                <span class="text-xs text-gray-500">参与分析（过滤 low 后）</span>
              </div>
              <div class="flex items-baseline gap-2">
                <span class="text-2xl font-mono font-semibold" :class="sentimentClass(descriptive.sentiment_overall)">
                  {{ fmtSent(descriptive.sentiment_overall) }}
                </span>
                <span class="text-xs text-gray-500">综合情感</span>
              </div>
              <div class="flex items-baseline gap-2">
                <span class="text-2xl font-mono font-semibold">
                  <span class="text-green-600">{{ descriptive.sentiment_distribution.positive }}</span>
                  <span class="text-gray-400 mx-0.5">/</span>
                  <span class="text-gray-600 dark:text-gray-300">{{ descriptive.sentiment_distribution.neutral }}</span>
                  <span class="text-gray-400 mx-0.5">/</span>
                  <span class="text-red-600">{{ descriptive.sentiment_distribution.negative }}</span>
                </span>
                <span class="text-xs text-gray-500">正/中/负</span>
              </div>
            </div>

            <!-- 跨任务重叠 -->
            <div v-if="overlapTotal > 0" class="mt-4 p-3 border border-gray-200 dark:border-gray-700 rounded">
              <p class="text-sm text-gray-500 mb-2">
                跨任务重叠（同一 URL 被几个 task 命中，重叠越高=多角度共同关注）
              </p>
              <div class="flex items-center gap-6 text-sm">
                <span>仅 1 个 task：<strong>{{ descriptive.cross_task_overlap.distribution.single_task }}</strong></span>
                <span class="text-amber-600">2 个 task：<strong>{{ descriptive.cross_task_overlap.distribution.two_tasks }}</strong></span>
                <span class="text-red-600">≥3 个 task：<strong>{{ descriptive.cross_task_overlap.distribution.three_plus }}</strong></span>
              </div>
            </div>
          </UCard>

          <!-- 时序：coverage + sentiment -->
          <UCard v-if="(descriptive.coverage_timeseries?.length ?? 0) > 1">
            <template #header>
              <h2 class="text-lg font-medium text-gray-900 dark:text-white">报道与情感时序</h2>
            </template>
            <div>
              <p class="text-sm text-gray-500 mb-2">报道量（按 tier 着色堆叠）</p>
              <div ref="coverageChartRef" class="w-full h-56" />
            </div>
            <div class="mt-4">
              <p class="text-sm text-gray-500 mb-2">情感（等权 vs tier 加权）</p>
              <div ref="sentimentChartRef" class="w-full h-48" />
            </div>
          </UCard>

          <!-- Source Pyramid -->
          <UCard v-if="sourcePyramid.length">
            <template #header>
              <h2 class="text-lg font-medium text-gray-900 dark:text-white">媒介金字塔</h2>
            </template>
            <div class="space-y-3">
              <div v-for="row in sourcePyramid" :key="row.tier">
                <div class="flex items-center gap-3">
                  <div class="w-24 shrink-0">
                    <UBadge :color="tierColor(row.tier)" variant="subtle" size="sm">
                      {{ tierLabel(row.tier) }}
                    </UBadge>
                  </div>
                  <div class="flex-1 bg-gray-100 dark:bg-gray-800 rounded h-8 relative overflow-hidden">
                    <div
                      class="h-full bg-blue-200 dark:bg-blue-900/40 transition-all"
                      :style="{ width: row.widthPct + '%' }"
                    />
                    <div class="absolute inset-0 flex items-center px-3 text-sm">
                      <span class="font-medium">{{ row.article_count }}</span>
                      <span class="text-gray-500 ml-1">篇</span>
                      <span v-if="row.sentiment_avg !== null" class="ml-auto text-xs">
                        情感
                        <span :class="sentimentClass(row.sentiment_avg)" class="font-medium">
                          {{ fmtSent(row.sentiment_avg) }}
                        </span>
                      </span>
                    </div>
                  </div>
                </div>
                <p v-if="row.top_source_names.length" class="text-xs text-gray-500 mt-1 ml-[6.5rem]">
                  活跃来源：{{ row.top_source_names.join('、') }}
                </p>
                <p v-if="(row.representative_articles?.length ?? 0) > 0" class="text-xs text-gray-400 mt-0.5 ml-[6.5rem] line-clamp-1">
                  <span>代表标题：</span>
                  <template v-for="(art, i) in (row.representative_articles ?? [])" :key="art.article_id">
                    <a
                      :href="art.url"
                      target="_blank"
                      rel="noopener"
                      class="text-blue-600 hover:underline"
                    >
                      {{ art.title }}
                    </a>
                    <span v-if="i < (row.representative_articles?.length ?? 0) - 1" class="mx-1">·</span>
                  </template>
                </p>
              </div>
            </div>
            <div v-if="mediaLandscape?.top_sources?.length" class="mt-4 pt-3 border-t border-gray-100 dark:border-gray-800">
              <p class="text-sm text-gray-500 mb-2">头部来源（top 5）</p>
              <div class="flex flex-wrap gap-2">
                <UBadge
                  v-for="s in mediaLandscape.top_sources"
                  :key="s.name"
                  variant="subtle"
                >
                  {{ s.name }} · {{ s.count }} 篇 · {{ formatPct(s.share) }}
                </UBadge>
              </div>
            </div>
          </UCard>

          <!-- Events Timeline -->
          <UCard v-if="eventClusters.length">
            <template #header>
              <h2 class="text-lg font-medium text-gray-900 dark:text-white">
                事件聚类
                <span class="text-sm font-normal text-gray-500 ml-2">
                  共 {{ eventClusters.length }} 个事件，按 tier 加权热度排序
                </span>
              </h2>
            </template>
            <div class="space-y-1.5">
              <button
                v-for="cluster in eventClusters"
                :key="cluster.cluster_id"
                type="button"
                class="w-full text-left px-3 py-2.5 border border-gray-200 dark:border-gray-700 rounded flex items-center gap-x-3 gap-y-1 flex-wrap hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors cursor-pointer"
                :title="`查看该事件的 ${cluster.article_count} 篇文章`"
                @click="openArticleModal(cluster.article_ids, eventTitle(cluster), `${cluster.article_count} 篇相关文章`)"
              >
                <!-- 标题 + frame -->
                <h3 class="font-medium text-sm">{{ eventTitle(cluster) }}</h3>
                <UBadge v-if="eventFrame(cluster)" variant="subtle" color="info" size="sm">
                  {{ eventFrame(cluster) }}
                </UBadge>

                <!-- 元信息 + 数字（同一行 inline） -->
                <div class="flex items-center gap-x-3 gap-y-1 text-xs text-gray-500 ml-auto flex-wrap">
                  <span>
                    首发
                    <span class="text-gray-700 dark:text-gray-200 font-medium">{{ dateOnly(cluster.first_reported_at) }}</span>
                    <span v-if="cluster.first_reporter" class="text-gray-500">
                      · {{ cluster.first_reporter.source_name }}
                    </span>
                  </span>
                  <span v-if="cluster.peak_date && cluster.peak_date !== dateOnly(cluster.first_reported_at)">
                    峰值 <span class="text-gray-700 dark:text-gray-200">{{ cluster.peak_date }}</span>
                  </span>
                  <span class="text-gray-700 dark:text-gray-200">
                    <strong>{{ cluster.article_count }}</strong> 篇
                  </span>
                  <span>热度 {{ cluster.tier_weighted_score.toFixed(1) }}</span>
                  <span v-if="cluster.in_task_ids.length > 1" class="text-blue-600">
                    跨 {{ cluster.in_task_ids.length }} task
                  </span>
                </div>
              </button>
            </div>
          </UCard>

          <!-- 实体全景（按 role 分组） -->
          <UCard v-if="entities.length">
            <template #header>
              <h2 class="text-lg font-medium text-gray-900 dark:text-white">实体全景</h2>
            </template>
            <div class="space-y-5">
              <template
                v-for="role in (['target', 'competitor', 'context'] as const)"
                :key="role"
              >
                <div v-if="entitiesByRole[role]?.length">
                  <h3 class="text-sm font-semibold mb-3 flex items-center gap-2">
                    <UBadge :color="entityRoleColor(role)" size="sm">
                      {{ entityRoleLabel(role) }}
                    </UBadge>
                    <span class="text-gray-500 font-normal">{{ entitiesByRole[role]?.length ?? 0 }} 个</span>
                  </h3>
                  <div class="overflow-x-auto">
                    <table class="w-full text-sm">
                      <thead>
                        <tr class="border-b border-gray-200 dark:border-gray-700 text-left text-xs text-gray-500">
                          <th class="py-2 px-2 font-medium">名称</th>
                          <th class="py-2 px-2 font-medium text-right">提及</th>
                          <th class="py-2 px-2 font-medium text-right">来源数</th>
                          <th class="py-2 px-2 font-medium text-right">跨 task</th>
                          <th class="py-2 px-2 font-medium text-right">情感</th>
                          <th class="py-2 px-2 font-medium">分层情感（tier1/2/3/MP）</th>
                        </tr>
                      </thead>
                      <tbody class="divide-y divide-gray-100 dark:divide-gray-700/50">
                        <tr
                          v-for="e in entitiesByRole[role]"
                          :key="e.name"
                        >
                          <td class="py-2 px-2 font-medium">{{ e.name }}</td>
                          <td class="py-2 px-2 text-right">
                            <button
                              v-if="e.article_ids.length > 0"
                              type="button"
                              class="text-blue-600 hover:underline cursor-pointer"
                              :title="`查看 ${e.name} 相关的 ${e.mention_count} 篇文章`"
                              @click="openArticleModal(e.article_ids, e.name, `${e.mention_count} 篇相关文章`)"
                            >
                              {{ e.mention_count }}
                            </button>
                            <span v-else>{{ e.mention_count }}</span>
                          </td>
                          <td class="py-2 px-2 text-right">{{ e.source_count }}</td>
                          <td class="py-2 px-2 text-right">{{ e.cross_task_count }}</td>
                          <td class="py-2 px-2 text-right">
                            <span :class="sentimentClass(e.sentiment_avg)">{{ fmtSent(e.sentiment_avg) }}</span>
                          </td>
                          <td class="py-2 px-2 text-xs">
                            <span v-for="t in TIER_KEYS" :key="t" class="mr-3">
                              <span class="text-gray-400">{{ t === 'wechat_mp' ? 'MP' : t.replace('tier', 'T') }}</span>
                              <span :class="sentimentClass(e.sentiment_by_tier[t])" class="ml-1">
                                {{ fmtSent(e.sentiment_by_tier[t]) }}
                              </span>
                            </span>
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              </template>
            </div>
          </UCard>

          <!-- 竞争层 -->
          <UCard v-if="competitive?.players?.length">
            <template #header>
              <h2 class="text-lg font-medium text-gray-900 dark:text-white">竞争层</h2>
            </template>
            <div class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead>
                  <tr class="border-b border-gray-200 dark:border-gray-700 text-left text-xs text-gray-500">
                    <th class="py-2 px-2 font-medium">玩家</th>
                    <th class="py-2 px-2 font-medium">角色</th>
                    <th class="py-2 px-2 font-medium text-right">声量份额</th>
                    <th class="py-2 px-2 font-medium text-right">提及</th>
                    <th class="py-2 px-2 font-medium text-right">情感</th>
                    <th class="py-2 px-2 font-medium text-right">官方引述</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-100 dark:divide-gray-700/50">
                  <tr
                    v-for="p in competitive.players"
                    :key="p.name"
                  >
                    <td class="py-2 px-2 font-medium">{{ p.name }}</td>
                    <td class="py-2 px-2">
                      <UBadge :color="playerRoleColor(p.role)" size="sm">
                        {{ entityRoleLabel(p.role) }}
                      </UBadge>
                    </td>
                    <td class="py-2 px-2 text-right">{{ formatPct(p.tier_weighted_sov) }}</td>
                    <td class="py-2 px-2 text-right">
                      <button
                        v-if="p.article_ids.length > 0"
                        type="button"
                        class="text-blue-600 hover:underline cursor-pointer"
                        :title="`查看 ${p.name} 相关的 ${p.mention_count} 篇文章`"
                        @click="openArticleModal(p.article_ids, p.name, `${p.mention_count} 篇相关文章`)"
                      >
                        {{ p.mention_count }}
                      </button>
                      <span v-else>{{ p.mention_count }}</span>
                    </td>
                    <td class="py-2 px-2 text-right">
                      <span :class="sentimentClass(p.sentiment_avg)">{{ fmtSent(p.sentiment_avg) }}</span>
                    </td>
                    <td class="py-2 px-2 text-right">
                      <template v-for="qs in (competitive.quote_share ?? [])" :key="qs.name">
                        <span v-if="qs.name === p.name">
                          {{ qs.official_quote_count }} / {{ qs.quote_count }}
                        </span>
                      </template>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </UCard>

          <!-- Quote Wall -->
          <UCard v-if="quotes.length">
            <template #header>
              <h2 class="text-lg font-medium text-gray-900 dark:text-white">关键引述</h2>
            </template>
            <div class="space-y-5">
              <template
                v-for="role in (['official', 'executive', 'analyst', 'kol', 'other'] as const)"
                :key="role"
              >
                <div v-if="quotesByRole[role]?.length">
                  <h3 class="text-sm font-semibold mb-3 flex items-center gap-2">
                    <UBadge :color="speakerRoleColor(role)" size="sm">
                      {{ speakerRoleLabel(role) }}
                    </UBadge>
                    <span class="text-gray-500 font-normal">{{ quotesByRole[role]?.length ?? 0 }} 条</span>
                  </h3>
                  <div class="grid grid-cols-1 lg:grid-cols-2 gap-2">
                    <div
                      v-for="(q, idx) in quotesByRole[role]"
                      :key="idx"
                      class="p-3 border-l-4 border-blue-400 bg-blue-50 dark:bg-blue-900/20 rounded-r"
                    >
                      <p class="text-sm italic">&ldquo;{{ q.quote }}&rdquo;</p>
                      <p class="text-xs text-gray-500 mt-1 flex items-center flex-wrap gap-1">
                        <span>&mdash; {{ q.speaker }}</span>
                        <span>| {{ q.source_name }}</span>
                        <UBadge :color="tierColor(q.source_tier)" size="sm" variant="subtle" class="ml-1">
                          {{ tierLabel(q.source_tier) }}
                        </UBadge>
                        <span v-if="q.published_at" class="ml-1">{{ dateOnly(q.published_at) }}</span>
                        <span v-if="q.context" class="ml-1 italic">· {{ q.context }}</span>
                        <button
                          type="button"
                          class="ml-auto text-blue-600 hover:underline cursor-pointer"
                          :title="'查看引述出处原文'"
                          @click="openArticleModal([q.article_id], q.speaker, '引述出处原文')"
                        >
                          查看原文 →
                        </button>
                      </p>
                    </div>
                  </div>
                </div>
              </template>
            </div>
          </UCard>

          <!-- 跨任务重叠详情（折叠） -->
          <UCard v-if="highOverlapArticles.length > 0">
            <template #header>
              <h2 class="text-lg font-medium text-gray-900 dark:text-white">高重叠文章
                <span class="text-sm font-normal text-gray-500 ml-2">
                  被多个 task 同时命中（top {{ highOverlapArticles.length }}）
                </span>
              </h2>
            </template>
            <div class="divide-y divide-gray-100 dark:divide-gray-700/50">
              <div
                v-for="art in highOverlapArticles"
                :key="art.article_id"
                class="flex items-start justify-between gap-3 text-sm py-2"
              >
                <a
                  :href="art.url"
                  target="_blank"
                  rel="noopener"
                  class="flex-1 text-blue-600 hover:underline line-clamp-1"
                >
                  {{ art.title }}
                </a>
                <span class="text-xs text-gray-500 shrink-0">
                  跨 <strong>{{ art.task_count }}</strong> 个 task（{{ art.task_ids.join(', ') }}）
                </span>
              </div>
            </div>
          </UCard>

          <UCard v-if="!entities.length && !eventClusters.length && !quotes.length">
            <div class="text-center py-4 text-gray-400 text-sm">
              分析已完成，但未产出实体/事件/引述（可能是 Pass 1 数据稀疏）
            </div>
          </UCard>
        </ClientOnly>
      </template>
    </template>

    <div v-else class="text-center py-8">
      <p class="text-gray-500">切片不存在</p>
    </div>

    <!-- 文章下钻弹窗（事件聚类 / 实体 / 竞争层共用） -->
    <ArticleListModal
      v-model:open="articleModalOpen"
      :slice-id="sliceId"
      :article-ids="articleModalIds"
      :title="articleModalTitle"
      :subtitle="articleModalSubtitle"
    />
  </div>
</template>
