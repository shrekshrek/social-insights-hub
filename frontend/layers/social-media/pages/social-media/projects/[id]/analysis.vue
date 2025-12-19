<script setup lang="ts">
import { computed, ref, watch, onMounted, onUnmounted } from 'vue'
import ProjectQuadrantChart from '../../../../analysis/components/ProjectQuadrantChart.vue'
import ProjectEntityGraphChart from '../../../../analysis/components/ProjectEntityGraphChart.vue'

definePageMeta({ layout: 'default' })

const toast = useToast()

// ==================== Types (new snapshot contract only) ====================
interface OriginalTerm { text: string; count: number }

interface SourceTask { task_id: number; mentions: number }

interface ProjectEntityAttrItem {
  text: string
  mentions: number
  original_terms?: OriginalTerm[]
  post_ids_sample?: { task_id: number; post_id: number }[]
  platform_distribution?: Record<string, number>
  keyword_distribution?: Record<string, number>
}

interface ProjectTopicOrEntity {
  name: string
  category?: string
  sentiment?: number
  role?: string
  type?: string
  heat: number
  mentions: number
  score: number
  original_terms?: OriginalTerm[]
  source_tasks?: SourceTask[]
  post_ids_sample?: { task_id: number; post_id: number }[]
  platform_distribution?: Record<string, number>
  keyword_distribution?: Record<string, number>
  role_breakdown?: Record<string, number>
  type_breakdown?: Record<string, number>
  top_features?: ProjectEntityAttrItem[]
  top_issues?: ProjectEntityAttrItem[]
}

interface ProjectOverviewData {
  total_volume?: number
  global_sentiment?: number
  platform_volume?: Record<string, number>
  keyword_volume?: Record<string, number>
}

interface ProjectTopicAspectItem {
  category: string
  heat: number
  sentiment: number
  mention_count?: number
  top_keywords?: string[]
  platform_distribution?: Record<string, number>
  keyword_distribution?: Record<string, number>
}

interface ProjectDetailsData {
  top_entities?: ProjectTopicOrEntity[]
  top_topics?: ProjectTopicOrEntity[]
}

type QuadrantLabel = 'Q1_danger' | 'Q2_brand' | 'Q3_complaint' | 'Q4_niche' | 'neutral'
interface ProjectQuadrantPoint {
  task_id: number
  post_id: number
  x: number
  y: number
  quadrant: QuadrantLabel
  label?: string
  platform?: string
  keyword?: string
}
interface ProjectEntityGraphNode {
  id: string
  name: string
  role?: string
  type?: string
  mentions: number
  heat: number
  score: number
  platform_distribution?: Record<string, number>
  keyword_distribution?: Record<string, number>
}
interface ProjectEntityGraphEdge {
  source: string
  target: string
  co_occurrence: number
  jaccard: number
  value: number
  platform_distribution?: Record<string, number>
  keyword_distribution?: Record<string, number>
}
interface ProjectEntityGraphData {
  nodes: ProjectEntityGraphNode[]
  edges: ProjectEntityGraphEdge[]
  params?: { top_n?: number; min_co_occurrence?: number }
}
interface ProjectChartsData {
  quadrant?: ProjectQuadrantPoint[]
  quadrant_summary?: Record<string, number>
  quadrant_summary_by_platform?: Record<string, Record<string, number>>
  quadrant_summary_by_keyword?: Record<string, Record<string, number>>
  quadrant_thresholds?: { avg_cii?: number }
  entity_graph?: ProjectEntityGraphData
}

interface ProjectSnapshotResultData {
  meta?: { project_id: number; generated_at: string }
  overview?: ProjectOverviewData
  charts?: ProjectChartsData
  topic_aspects?: ProjectTopicAspectItem[]
  details?: ProjectDetailsData
  stage2?: {
    status: 'completed' | 'processing' | 'failed' | 'skipped'
    started_at?: string
    updated_at?: string
    steps?: Record<string, { status: 'pending' | 'processing' | 'completed' | 'failed'; llm_used?: boolean }>
    generated_at?: string
    llm?: { used?: boolean }
    category_alignment?: {
      used?: boolean
      category_map?: Record<string, string>
      topic_aspects_aligned?: ProjectTopicAspectItem[]
    }
    alias_normalization?: {
      entities?: {
        used?: boolean
        before_count?: number
        after_count?: number
        entity_mapping?: Record<string, string>
      }
      topics?: {
        used?: boolean
        before_count?: number
        after_count?: number
        topic_mapping_by_category?: Record<string, Record<string, string>>
      }
    }
    details_aligned?: {
      top_entities?: ProjectTopicOrEntity[]
      top_topics?: ProjectTopicOrEntity[]
      topic_aspects_aligned_v2?: ProjectTopicAspectItem[]
    }
    drivers?: {
      min_cell_mentions?: number
      dimensions_top?: string[]
      entity_matrix?: Array<{
        entity: string
        dimensions: Record<string, {
          mentions: number
          pos: number
          neg: number
          sentiment: number
        }>
      }>
    }
  }
  stage3?: {
    status: 'pending' | 'processing' | 'completed' | 'failed'
    started_at?: string
    updated_at?: string
    generated_at?: string
    llm?: { used?: boolean }
    summary?: {
      executive_summary?: string
      differences?: Array<{ dimension?: string; key?: string; insight?: string; evidence?: string }>
      drivers?: Array<{ driver?: string; entities?: string[]; sentiment?: string; evidence?: string }>
      risks?: string[]
      opportunities?: string[]
      next_questions?: string[]
    }
    error?: string
  }
}

interface ProjectSnapshot {
  id: number
  name: string | null
  project_id: number
  user_id: number
  included_task_ids: number[]
  result_data: ProjectSnapshotResultData
  created_at: string
  updated_at: string
}

// ==================== Data Loading ====================
const route = useRoute()
const projectId = computed(() => Number(route.params.id))
const snapshotId = computed(() => route.query.snapshot_id ? Number(route.query.snapshot_id) : null)

const { useApiData } = useApi()
const { data: snapshot, pending: snapshotLoading, refresh: refreshSnapshot } = useApiData<ProjectSnapshot>(
  computed(() => snapshotId.value ? `/social-media/analysis/projects/${projectId.value}/snapshots/${snapshotId.value}` : ''),
  {
    key: computed(() => `project-snapshot-detail-${projectId.value}-${snapshotId.value}`),
    silent404: true,
    immediate: computed(() => Boolean(snapshotId.value)),
    getCachedData: () => undefined,
  }
)

const handleRefresh = async () => {
  if (!snapshotId.value) return
  await refreshSnapshot()
}

// ==================== View Models ====================
const snapshotResult = computed<ProjectSnapshotResultData | null>(() => snapshot.value?.result_data || null)
const overview = computed<ProjectOverviewData | null>(() => snapshotResult.value?.overview || null)
const charts = computed<ProjectChartsData | null>(() => snapshotResult.value?.charts || null)
// 统一展示口径：流水线完成后优先使用“归一后的最终结果”，避免展示原始合并噪声
const alignedDetails = computed(() => stage2.value?.details_aligned || null)
const topicAspects = computed<ProjectTopicAspectItem[]>(() => alignedDetails.value?.topic_aspects_aligned_v2 || snapshotResult.value?.topic_aspects || [])
const topEntities = computed<ProjectTopicOrEntity[]>(() => alignedDetails.value?.top_entities || snapshotResult.value?.details?.top_entities || [])
const topTopics = computed<ProjectTopicOrEntity[]>(() => alignedDetails.value?.top_topics || snapshotResult.value?.details?.top_topics || [])
const stage2 = computed(() => snapshotResult.value?.stage2 || null)
const stage3 = computed(() => snapshotResult.value?.stage3 || null)
const drivers = computed(() => stage2.value?.drivers || null)
const categoryAlignment = computed(() => stage2.value?.category_alignment || null)
const aliasNormalization = computed(() => stage2.value?.alias_normalization || null)
// const alignedDetails = computed(() => stage2.value?.details_aligned || null)

const isPipelineReady = computed(() => stage2.value?.status === 'completed')
const isPipelineRunning = computed(() => stage2.value?.status === 'processing')

// ==================== 自动轮询机制（参考任务级）====================
let pollTimer: ReturnType<typeof setInterval> | null = null

const startPolling = () => {
  if (pollTimer) return
  pollTimer = setInterval(() => {
    refreshSnapshot()
  }, 3000)
}

const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// 监听流水线状态，完成时停止轮询并提示
watch(isPipelineReady, (ready, wasReady) => {
  if (ready && !wasReady) {
    stopPolling()
    toast.add({
      title: '报告生成完成',
      description: '项目快照分析已完成',
      color: 'success',
    })
  }
})

// 监听流水线运行状态，运行中时启动轮询
watch(isPipelineRunning, (running) => {
  if (running) {
    startPolling()
  } else {
    stopPolling()
  }
})

onMounted(() => {
  if (isPipelineRunning.value) {
    startPolling()
  }
})

onUnmounted(() => {
  stopPolling()
})

const sortedPlatformVolume = computed(() => {
  const m = overview.value?.platform_volume || {}
  return Object.entries(m).sort((a, b) => (b[1] || 0) - (a[1] || 0))
})
const sortedKeywordVolume = computed(() => {
  const m = overview.value?.keyword_volume || {}
  return Object.entries(m).sort((a, b) => (b[1] || 0) - (a[1] || 0))
})

const formatDist = (dist?: Record<string, number>) => {
  if (!dist) return '-'
  const entries = Object.entries(dist).sort((a, b) => (b[1] || 0) - (a[1] || 0)).slice(0, 4)
  return entries.map(([k, v]) => `${k}:${v}`).join('，')
}

const quadrantSummary = computed(() => charts.value?.quadrant_summary || null)
const quadrantSummaryByPlatform = computed(() => charts.value?.quadrant_summary_by_platform || {})
const quadrantSummaryByKeyword = computed(() => charts.value?.quadrant_summary_by_keyword || {})
const quadrantAvgCii = computed(() => charts.value?.quadrant_thresholds?.avg_cii)
const entityGraph = computed(() => charts.value?.entity_graph || null)
const sortedQuadrantPlatforms = computed(() => Object.entries(quadrantSummaryByPlatform.value || {}).sort((a, b) => a[0].localeCompare(b[0])))
const sortedQuadrantKeywords = computed(() => Object.entries(quadrantSummaryByKeyword.value || {}).sort((a, b) => a[0].localeCompare(b[0])))

// expand original_terms
const expandedItems = ref<Set<string>>(new Set())
const toggleExpand = (key: string) => {
  const s = new Set(expandedItems.value)
  if (s.has(key)) s.delete(key)
  else s.add(key)
  expandedItems.value = s
}
const isExpanded = (key: string) => expandedItems.value.has(key)

// 状态颜色映射（参考任务级）
const getStatusColor = (status?: string) => {
  const colors: Record<string, string> = {
    pending: 'warning',
    processing: 'info',
    completed: 'success',
    failed: 'error',
    skipped: 'neutral',
  }
  return colors[status || 'pending'] || 'neutral'
}

const getStatusLabel = (status?: string) => {
  const labels: Record<string, string> = {
    pending: '等待中',
    processing: '进行中',
    completed: '已完成',
    failed: '失败',
    skipped: '已跳过',
  }
  return labels[status || 'pending'] || status || 'pending'
}
</script>

<template>
  <div class="space-y-6">
    <!-- Page Header -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <UButton variant="ghost" icon="i-heroicons-arrow-left" :to="`/social-media/projects/${projectId}`" />
        <div>
          <ClientOnly>
            <h1 class="text-xl font-semibold text-gray-900 dark:text-white">
              {{ snapshot?.name || `快照 ${snapshotId}` }}
            </h1>
            <template #fallback>
              <h1 class="text-xl font-semibold text-gray-900 dark:text-white">
                {{ `快照 ${snapshotId}` }}
              </h1>
            </template>
          </ClientOnly>
          <p class="text-sm text-gray-500 dark:text-gray-400">
            项目级合并分析快照（新方案）
          </p>
        </div>
      </div>
      <ClientOnly>
        <UButton icon="i-heroicons-arrow-path" variant="ghost" :loading="snapshotLoading" @click="handleRefresh">
          刷新
        </UButton>
      </ClientOnly>
    </div>

    <ClientOnly>
      <template #fallback>
        <div class="text-center py-12 text-gray-400">加载中...</div>
      </template>

      <div v-if="snapshotLoading" class="text-center py-12 text-gray-400">加载中...</div>
      <div v-else-if="!snapshotId" class="text-center py-12 text-gray-400">未指定快照 ID，请从项目详情页选择快照查看</div>
      <div v-else-if="!snapshot" class="text-center py-12 text-gray-400">快照不存在或已删除</div>

      <div v-else class="space-y-6">
        <!-- 分析报告（生成进度） -->
        <section class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
          <div class="flex items-center justify-between gap-4 mb-2">
            <h2 class="text-lg font-medium text-gray-900 dark:text-white">🧾 分析报告</h2>
            <div class="text-xs text-gray-500 dark:text-gray-400">
              <span class="font-mono">snapshot_id={{ snapshot.id }}</span>
            </div>
          </div>
          <div class="text-sm text-gray-700 dark:text-gray-300">
            <div class="text-xs text-gray-500 dark:text-gray-400">
              实体归一与观点归一会并行触发；完成后再进行程序化分析与总分析。进度以快照自身的执行状态为准。
            </div>
            <div v-if="stage2?.steps" class="mt-3 grid grid-cols-1 md:grid-cols-2 gap-2">
              <div class="p-3 rounded bg-gray-50 dark:bg-gray-800 flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <span class="font-medium text-gray-900 dark:text-white">实体归一化</span>
                  <span v-if="(stage2.steps as any).entity_normalization?.job_id" class="text-xs text-gray-400 font-mono">
                    job={{ (stage2.steps as any).entity_normalization.job_id }}
                  </span>
                </div>
                <UBadge :color="getStatusColor((stage2.steps as any).entity_normalization?.status)" variant="solid" size="xs">
                  {{ getStatusLabel((stage2.steps as any).entity_normalization?.status) }}
                </UBadge>
              </div>
              <div class="p-3 rounded bg-gray-50 dark:bg-gray-800 flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <span class="font-medium text-gray-900 dark:text-white">观点归一化</span>
                  <span v-if="(stage2.steps as any).opinion_normalization?.job_id" class="text-xs text-gray-400 font-mono">
                    job={{ (stage2.steps as any).opinion_normalization.job_id }}
                  </span>
                </div>
                <UBadge :color="getStatusColor((stage2.steps as any).opinion_normalization?.status)" variant="solid" size="xs">
                  {{ getStatusLabel((stage2.steps as any).opinion_normalization?.status) }}
                </UBadge>
              </div>
              <div class="p-3 rounded bg-gray-50 dark:bg-gray-800 flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <span class="font-medium text-gray-900 dark:text-white">程序化分析</span>
                </div>
                <UBadge :color="getStatusColor((stage2.steps as any).derived_analysis?.status)" variant="solid" size="xs">
                  {{ getStatusLabel((stage2.steps as any).derived_analysis?.status) }}
                </UBadge>
              </div>
              <div class="p-3 rounded bg-gray-50 dark:bg-gray-800 flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <span class="font-medium text-gray-900 dark:text-white">总分析</span>
                  <span v-if="(stage2.steps as any).summary?.job_id" class="text-xs text-gray-400 font-mono">
                    job={{ (stage2.steps as any).summary.job_id }}
                  </span>
                </div>
                <UBadge :color="getStatusColor(stage3?.status || (stage2.steps as any).summary?.status)" variant="solid" size="xs">
                  {{ getStatusLabel(stage3?.status || (stage2.steps as any).summary?.status) }}
                </UBadge>
              </div>
            </div>
          </div>

          <div v-if="!isPipelineReady" class="mt-4 text-xs text-gray-500 dark:text-gray-400">
            为保证口径一致与结论可靠，报告生成完成前将不展示概览/差异/归因/证据内容。请稍候并点击右上角“刷新”查看进度。
          </div>
        </section>

        <!-- 报告未完成：不展示下方板块 -->
        <template v-if="isPipelineReady">
        <!-- 总分析（完成后展示） -->
        <section class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 space-y-3">
          <div class="flex items-center justify-between gap-4">
            <h2 class="text-lg font-medium text-gray-900 dark:text-white">🧠 总分析</h2>
            <div class="text-xs text-gray-500 dark:text-gray-400">
              <span class="font-mono">{{ stage3?.status || 'pending' }}</span>
            </div>
          </div>

          <div v-if="stage3?.status !== 'completed'" class="text-xs text-gray-500 dark:text-gray-400">
            总结生成中（或失败）。完成后将展示“执行摘要/差异/驱动因素/风险与机会”等结论。
          </div>

          <div v-else class="space-y-3">
            <div class="p-3 rounded bg-gray-50 dark:bg-gray-800">
              <div class="text-xs text-gray-500 dark:text-gray-400 mb-2">执行摘要</div>
              <div class="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap">
                {{ stage3?.summary?.executive_summary || '-' }}
              </div>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div class="p-3 rounded bg-gray-50 dark:bg-gray-800">
                <div class="text-xs text-gray-500 dark:text-gray-400 mb-2">平台/关键词差异</div>
                <div v-if="stage3?.summary?.differences?.length" class="space-y-2">
                  <div v-for="(d, idx) in stage3.summary.differences.slice(0, 8)" :key="`diff-${idx}`" class="p-2 rounded bg-white/60 dark:bg-gray-900/30">
                    <div class="text-sm text-gray-900 dark:text-white font-medium">
                      {{ d.dimension }} · {{ d.key }}
                    </div>
                    <div class="text-xs text-gray-600 dark:text-gray-300 mt-1">{{ d.insight }}</div>
                    <div v-if="d.evidence" class="text-xs text-gray-400 mt-1">证据：{{ d.evidence }}</div>
                  </div>
                </div>
                <div v-else class="text-xs text-gray-400">暂无</div>
              </div>

              <div class="p-3 rounded bg-gray-50 dark:bg-gray-800">
                <div class="text-xs text-gray-500 dark:text-gray-400 mb-2">驱动因素</div>
                <div v-if="stage3?.summary?.drivers?.length" class="space-y-2">
                  <div v-for="(d, idx) in stage3.summary.drivers.slice(0, 8)" :key="`drv-${idx}`" class="p-2 rounded bg-white/60 dark:bg-gray-900/30">
                    <div class="text-sm text-gray-900 dark:text-white font-medium">{{ d.driver }}</div>
                    <div class="text-xs text-gray-600 dark:text-gray-300 mt-1">实体：{{ (d.entities || []).slice(0, 6).join('、') || '-' }}</div>
                    <div class="text-xs text-gray-600 dark:text-gray-300 mt-1">倾向：{{ d.sentiment || '-' }}</div>
                    <div v-if="d.evidence" class="text-xs text-gray-400 mt-1">证据：{{ d.evidence }}</div>
                  </div>
                </div>
                <div v-else class="text-xs text-gray-400">暂无</div>
              </div>
            </div>
          </div>
        </section>

        <!-- 1) 概览 -->
        <section class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
          <div class="flex items-center justify-between gap-4 mb-4">
            <h2 class="text-lg font-medium text-gray-900 dark:text-white">🌍 概览</h2>
            <div class="text-xs text-gray-500 dark:text-gray-400">
              <span class="font-mono">snapshot_id={{ snapshot.id }}</span>
              <span class="mx-2">·</span>
              <span>任务数 {{ snapshot.included_task_ids?.length || 0 }}</span>
            </div>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
            <div>
              <div class="text-gray-500 dark:text-gray-400">总声量</div>
              <div class="text-gray-900 dark:text-white font-mono text-lg">{{ overview?.total_volume ?? '-' }}</div>
            </div>
            <div>
              <div class="text-gray-500 dark:text-gray-400">全局情感</div>
              <div class="text-gray-900 dark:text-white font-mono text-lg">
                {{ typeof overview?.global_sentiment === 'number' ? overview.global_sentiment.toFixed(2) : '-' }}
              </div>
            </div>
            <div>
              <div class="text-gray-500 dark:text-gray-400">平台/关键词构成</div>
              <div class="text-gray-900 dark:text-white text-xs mt-1">
                <div>平台：{{ sortedPlatformVolume.length ? sortedPlatformVolume.slice(0, 6).map(([k, v]) => `${k}:${v}`).join('，') : '-' }}</div>
                <div class="mt-1">关键词：{{ sortedKeywordVolume.length ? sortedKeywordVolume.slice(0, 6).map(([k, v]) => `${k}:${v}`).join('，') : '-' }}</div>
              </div>
            </div>
          </div>
        </section>

        <!-- 2) 差异（平台/关键词） -->
        <section class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 space-y-4">
          <h2 class="text-lg font-medium text-gray-900 dark:text-white">🧭 差异（平台 / 关键词）</h2>

          <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <ProjectQuadrantChart
              v-if="charts?.quadrant?.length"
              :points="charts?.quadrant"
              :avg-cii="quadrantAvgCii"
            />
            <div v-else class="text-sm text-gray-400 py-4">暂无 quadrant 点位数据（任务级 charts.quadrant 可能缺失）。</div>

            <ProjectEntityGraphChart v-if="entityGraph?.nodes?.length" :data="entityGraph" />
            <div v-else class="text-sm text-gray-400 py-4">暂无实体共现网络数据（实体不足或共现阈值过滤后为空）。</div>
          </div>

          <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div class="p-3 rounded bg-gray-50 dark:bg-gray-800">
              <div class="text-sm font-medium text-gray-900 dark:text-white mb-2">四象限汇总（全局）</div>
              <div v-if="quadrantSummary" class="text-xs text-gray-600 dark:text-gray-300 grid grid-cols-2 gap-2">
                <div>爆雷区(Q1)：{{ quadrantSummary.Q1_danger ?? 0 }}</div>
                <div>品牌区(Q2)：{{ quadrantSummary.Q2_brand ?? 0 }}</div>
                <div>吐槽区(Q3)：{{ quadrantSummary.Q3_complaint ?? 0 }}</div>
                <div>自嗨区(Q4)：{{ quadrantSummary.Q4_niche ?? 0 }}</div>
                <div>中性：{{ quadrantSummary.neutral ?? 0 }}</div>
                <div>avg CII：{{ typeof quadrantAvgCii === 'number' ? quadrantAvgCii.toFixed(2) : '-' }}</div>
              </div>
              <div v-else class="text-xs text-gray-400">暂无汇总</div>
            </div>

            <div class="p-3 rounded bg-gray-50 dark:bg-gray-800">
              <div class="text-sm font-medium text-gray-900 dark:text-white mb-2">四象限差异（平台/关键词）</div>
              <div class="text-xs text-gray-600 dark:text-gray-300 space-y-2">
                <div>
                  <div class="text-gray-500 dark:text-gray-400 mb-1">按平台</div>
                  <div v-if="sortedQuadrantPlatforms.length" class="overflow-x-auto">
                    <table class="min-w-full text-xs">
                      <thead>
                        <tr class="text-left text-gray-500 dark:text-gray-400">
                          <th class="py-1 pr-3">平台</th><th class="py-1 pr-3">Q1</th><th class="py-1 pr-3">Q2</th><th class="py-1 pr-3">Q3</th><th class="py-1 pr-3">Q4</th><th class="py-1 pr-3">N</th>
                        </tr>
                      </thead>
                      <tbody class="text-gray-700 dark:text-gray-300">
                        <tr v-for="[p, s] in sortedQuadrantPlatforms" :key="`qp-${p}`" class="border-t border-gray-100 dark:border-gray-700">
                          <td class="py-1 pr-3">{{ p }}</td>
                          <td class="py-1 pr-3 font-mono">{{ s.Q1_danger ?? 0 }}</td>
                          <td class="py-1 pr-3 font-mono">{{ s.Q2_brand ?? 0 }}</td>
                          <td class="py-1 pr-3 font-mono">{{ s.Q3_complaint ?? 0 }}</td>
                          <td class="py-1 pr-3 font-mono">{{ s.Q4_niche ?? 0 }}</td>
                          <td class="py-1 pr-3 font-mono">{{ (s.Q1_danger ?? 0) + (s.Q2_brand ?? 0) + (s.Q3_complaint ?? 0) + (s.Q4_niche ?? 0) + (s.neutral ?? 0) }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <div v-else class="text-gray-400">暂无</div>
                </div>
                <div>
                  <div class="text-gray-500 dark:text-gray-400 mb-1">按关键词</div>
                  <div v-if="sortedQuadrantKeywords.length" class="overflow-x-auto">
                    <table class="min-w-full text-xs">
                      <thead>
                        <tr class="text-left text-gray-500 dark:text-gray-400">
                          <th class="py-1 pr-3">关键词</th><th class="py-1 pr-3">Q1</th><th class="py-1 pr-3">Q2</th><th class="py-1 pr-3">Q3</th><th class="py-1 pr-3">Q4</th><th class="py-1 pr-3">N</th>
                        </tr>
                      </thead>
                      <tbody class="text-gray-700 dark:text-gray-300">
                        <tr v-for="[k, s] in sortedQuadrantKeywords" :key="`qk-${k}`" class="border-t border-gray-100 dark:border-gray-700">
                          <td class="py-1 pr-3">{{ k || '-' }}</td>
                          <td class="py-1 pr-3 font-mono">{{ s.Q1_danger ?? 0 }}</td>
                          <td class="py-1 pr-3 font-mono">{{ s.Q2_brand ?? 0 }}</td>
                          <td class="py-1 pr-3 font-mono">{{ s.Q3_complaint ?? 0 }}</td>
                          <td class="py-1 pr-3 font-mono">{{ s.Q4_niche ?? 0 }}</td>
                          <td class="py-1 pr-3 font-mono">{{ (s.Q1_danger ?? 0) + (s.Q2_brand ?? 0) + (s.Q3_complaint ?? 0) + (s.Q4_niche ?? 0) + (s.neutral ?? 0) }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <div v-else class="text-gray-400">暂无</div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- 3) 归因 -->
        <section class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 space-y-4">
          <h2 class="text-lg font-medium text-gray-900 dark:text-white">🧩 归因</h2>

          <!-- 归因矩阵（基于归一结果） -->
          <div class="p-3 rounded bg-gray-50 dark:bg-gray-800">
            <div class="flex items-center justify-between mb-2">
              <div class="text-sm font-medium text-gray-900 dark:text-white">归因矩阵</div>
              <div class="text-xs text-gray-500 dark:text-gray-400">
                <span v-if="stage2?.status">状态：{{ stage2.status }}</span>
                <span v-if="stage2?.llm?.used !== undefined"> · LLM={{ stage2.llm.used ? '是' : '否' }}</span>
              </div>
            </div>
            <div v-if="drivers && drivers.dimensions_top?.length && drivers.entity_matrix?.length" class="overflow-x-auto">
              <table class="min-w-full text-xs">
                <thead>
                  <tr class="text-left text-gray-500 dark:text-gray-400">
                    <th class="py-1 pr-3">实体</th>
                    <th v-for="d in drivers.dimensions_top" :key="`dim-${d}`" class="py-1 pr-3">
                      {{ d }}
                    </th>
                  </tr>
                </thead>
                <tbody class="text-gray-700 dark:text-gray-300">
                  <tr v-for="row in drivers.entity_matrix.slice(0, 12)" :key="`m2-${row.entity}`" class="border-t border-gray-100 dark:border-gray-700">
                    <td class="py-1 pr-3 font-medium whitespace-nowrap">{{ row.entity }}</td>
                    <td
                      v-for="d in drivers.dimensions_top"
                      :key="`cell-${row.entity}-${d}`"
                      class="py-1 pr-3 font-mono whitespace-nowrap"
                      :class="[
                        ((row.dimensions?.[d]?.mentions || 0) < (drivers.min_cell_mentions || 5)) ? 'text-gray-300 dark:text-gray-600' : '',
                        ((row.dimensions?.[d]?.mentions || 0) >= (drivers.min_cell_mentions || 5) && (row.dimensions?.[d]?.sentiment || 0) < 0) ? 'text-red-600 dark:text-red-400' : '',
                        ((row.dimensions?.[d]?.mentions || 0) >= (drivers.min_cell_mentions || 5) && (row.dimensions?.[d]?.sentiment || 0) > 0) ? 'text-green-600 dark:text-green-400' : '',
                      ]"
                      :title="`mentions=${row.dimensions?.[d]?.mentions || 0}, sentiment=${row.dimensions?.[d]?.sentiment ?? 0}`"
                    >
                      <span v-if="(row.dimensions?.[d]?.mentions || 0) >= (drivers.min_cell_mentions || 5)">
                        {{ (row.dimensions?.[d]?.sentiment ?? 0).toFixed(2) }} ({{ row.dimensions?.[d]?.mentions || 0 }})
                      </span>
                      <span v-else>N/A</span>
                    </td>
                  </tr>
                </tbody>
              </table>
              <div class="text-xs text-gray-400 mt-2">
                说明：单元格显示为 <span class="font-mono">sentiment (mentions)</span>；当 mentions &lt; {{ drivers.min_cell_mentions || 5 }} 时按 N/A 灰显，避免小样本误导。
              </div>
            </div>
            <div v-else class="text-xs text-gray-500 dark:text-gray-400">
              已生成报告，但缺少归因矩阵数据（可能是实体属性不足）。
            </div>
          </div>

          <!-- 实体/观点全局别名归一 -->
          <div class="p-3 rounded bg-gray-50 dark:bg-gray-800">
            <div class="flex items-center justify-between mb-2">
              <div class="text-sm font-medium text-gray-900 dark:text-white">全局别名归一</div>
              <div class="text-xs text-gray-500 dark:text-gray-400">
                <span v-if="aliasNormalization?.entities?.used !== undefined">实体 LLM={{ aliasNormalization.entities.used ? '是' : '否' }}</span>
                <span v-if="aliasNormalization?.topics?.used !== undefined"> · 观点 LLM={{ aliasNormalization.topics.used ? '是' : '否' }}</span>
              </div>
            </div>
            <div v-if="aliasNormalization" class="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div class="p-3 rounded bg-white/60 dark:bg-gray-900/30">
                <div class="text-xs text-gray-500 dark:text-gray-400 mb-2">合并效果</div>
                <div class="text-sm text-gray-700 dark:text-gray-300 space-y-1">
                  <div>
                    实体：{{ aliasNormalization?.entities?.before_count ?? '-' }} → {{ aliasNormalization?.entities?.after_count ?? '-' }}
                  </div>
                  <div>
                    观点：{{ aliasNormalization?.topics?.before_count ?? '-' }} → {{ aliasNormalization?.topics?.after_count ?? '-' }}
                  </div>
                </div>
                <div class="text-xs text-gray-400 mt-2">
                  说明：本阶段用于把跨任务的同义项合并（先程序、后 LLM 复核；LLM 不可用自动降级）。
                </div>
              </div>

              <div class="p-3 rounded bg-white/60 dark:bg-gray-900/30">
                <div class="text-xs text-gray-500 dark:text-gray-400 mb-2">实体映射抽样（原名 → 标准名）</div>
                <div v-if="aliasNormalization?.entities?.entity_mapping && Object.keys(aliasNormalization.entities.entity_mapping).length" class="overflow-x-auto">
                  <table class="min-w-full text-xs">
                    <thead>
                      <tr class="text-left text-gray-500 dark:text-gray-400">
                        <th class="py-1 pr-3">原名</th>
                        <th class="py-1 pr-3">标准名</th>
                      </tr>
                    </thead>
                    <tbody class="text-gray-700 dark:text-gray-300">
                      <tr
                        v-for="([k, v], idx) in Object.entries(aliasNormalization.entities.entity_mapping).slice(0, 15)"
                        :key="`emap-${idx}`"
                        class="border-t border-gray-100 dark:border-gray-700"
                      >
                        <td class="py-1 pr-3">{{ k }}</td>
                        <td class="py-1 pr-3 font-medium">{{ v }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div v-else class="text-xs text-gray-400">暂无映射</div>
              </div>
            </div>
            <div v-else class="text-xs text-gray-500 dark:text-gray-400">
              暂无别名归一信息
            </div>
          </div>

          <!-- 观点类目对齐（观点归一的一部分） -->
          <div class="p-3 rounded bg-gray-50 dark:bg-gray-800">
            <div class="flex items-center justify-between mb-2">
              <div class="text-sm font-medium text-gray-900 dark:text-white">类目对齐</div>
              <div class="text-xs text-gray-500 dark:text-gray-400">
                <span v-if="categoryAlignment?.used !== undefined">LLM={{ categoryAlignment.used ? '是' : '否' }}</span>
              </div>
            </div>
            <div v-if="categoryAlignment?.topic_aspects_aligned?.length" class="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div class="p-3 rounded bg-white/60 dark:bg-gray-900/30">
                <div class="text-xs text-gray-500 dark:text-gray-400 mb-2">对齐后的类目聚合</div>
                <div class="space-y-2">
                  <div
                    v-for="(a, idx) in categoryAlignment.topic_aspects_aligned.slice(0, 12)"
                    :key="`aligned-aspect-${idx}`"
                    class="p-3 rounded bg-gray-50 dark:bg-gray-800"
                  >
                    <div class="flex items-start justify-between gap-3">
                      <div class="min-w-0 flex-1">
                        <div class="flex items-center gap-2 flex-wrap">
                          <span class="text-gray-900 dark:text-white font-medium">{{ a.category }}</span>
                          <UBadge v-if="a.sentiment < 0" color="error" variant="subtle" size="xs">偏负</UBadge>
                          <UBadge v-else-if="a.sentiment > 0" color="success" variant="subtle" size="xs">偏正</UBadge>
                          <UBadge v-else color="neutral" variant="subtle" size="xs">中性</UBadge>
                        </div>
                        <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">
                          代表词：{{ (a.top_keywords || []).slice(0, 6).join('、') || '-' }}
                        </div>
                        <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">平台：{{ formatDist(a.platform_distribution) }}</div>
                        <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">关键词：{{ formatDist(a.keyword_distribution) }}</div>
                      </div>
                      <div class="text-right shrink-0">
                        <div class="font-mono font-bold text-gray-900 dark:text-white">{{ Number(a.heat || 0).toFixed(1) }}</div>
                        <div class="text-xs text-gray-500 dark:text-gray-400">heat</div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div class="p-3 rounded bg-white/60 dark:bg-gray-900/30">
                <div class="text-xs text-gray-500 dark:text-gray-400 mb-2">类目映射（原类目 → 标准类目）</div>
                <div v-if="categoryAlignment?.category_map && Object.keys(categoryAlignment.category_map).length" class="overflow-x-auto">
                  <table class="min-w-full text-xs">
                    <thead>
                      <tr class="text-left text-gray-500 dark:text-gray-400">
                        <th class="py-1 pr-3">原类目</th>
                        <th class="py-1 pr-3">标准类目</th>
                      </tr>
                    </thead>
                    <tbody class="text-gray-700 dark:text-gray-300">
                      <tr
                        v-for="(v, k) in categoryAlignment.category_map"
                        :key="`catmap-${k}`"
                        class="border-t border-gray-100 dark:border-gray-700"
                      >
                        <td class="py-1 pr-3">{{ k }}</td>
                        <td class="py-1 pr-3 font-medium">{{ v }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div v-else class="text-xs text-gray-400">
                  LLM 未返回映射或无需对齐（类目较少时可能为空）。
                </div>
              </div>
            </div>
            <div v-else class="text-xs text-gray-500 dark:text-gray-400">
              未生成对齐后的类目聚合（可能是 top_topics 为空或类目不足）。
            </div>
          </div>

          <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div class="p-3 rounded bg-gray-50 dark:bg-gray-800">
              <div class="text-sm font-medium text-gray-900 dark:text-white mb-2">类目概览（原始合并结果）</div>
              <div v-if="topicAspects.length" class="space-y-2">
                <div v-for="(a, idx) in topicAspects.slice(0, 12)" :key="`aspect-${idx}`" class="p-3 rounded bg-white/60 dark:bg-gray-900/30">
                  <div class="flex items-start justify-between gap-3">
                    <div class="min-w-0 flex-1">
                      <div class="flex items-center gap-2 flex-wrap">
                        <span class="text-gray-900 dark:text-white font-medium">{{ a.category }}</span>
                        <UBadge v-if="a.sentiment < 0" color="error" variant="subtle" size="xs">偏负</UBadge>
                        <UBadge v-else-if="a.sentiment > 0" color="success" variant="subtle" size="xs">偏正</UBadge>
                        <UBadge v-else color="neutral" variant="subtle" size="xs">中性</UBadge>
                      </div>
                      <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">代表词：{{ (a.top_keywords || []).slice(0, 6).join('、') || '-' }}</div>
                      <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">平台：{{ formatDist(a.platform_distribution) }}</div>
                      <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">关键词：{{ formatDist(a.keyword_distribution) }}</div>
                    </div>
                    <div class="text-right shrink-0">
                      <div class="font-mono font-bold text-gray-900 dark:text-white">{{ Number(a.heat || 0).toFixed(1) }}</div>
                      <div class="text-xs text-gray-500 dark:text-gray-400">heat</div>
                      <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">情感 {{ Number(a.sentiment || 0).toFixed(2) }}</div>
                    </div>
                  </div>
                </div>
              </div>
              <div v-else class="text-sm text-gray-400 py-4">暂无类目聚合数据</div>
            </div>

            <div class="p-3 rounded bg-gray-50 dark:bg-gray-800">
              <div class="text-sm font-medium text-gray-900 dark:text-white mb-2">Top 实体画像（原始合并结果）</div>
              <div v-if="topEntities.length" class="space-y-2">
                <div v-for="(e, idx) in topEntities.slice(0, 12)" :key="`driver-entity-${idx}`" class="p-3 rounded bg-white/60 dark:bg-gray-900/30">
                  <div class="flex items-start justify-between gap-3">
                    <div class="min-w-0 flex-1">
                      <div class="flex items-center gap-2 flex-wrap">
                        <span class="text-gray-900 dark:text-white font-medium">{{ e.name }}</span>
                        <UBadge v-if="e.role" color="neutral" variant="subtle" size="xs">{{ e.role }}</UBadge>
                        <UBadge v-if="e.type" color="info" variant="subtle" size="xs">{{ e.type }}</UBadge>
                      </div>
                      <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">平台：{{ formatDist(e.platform_distribution) }}</div>
                      <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">关键词：{{ formatDist(e.keyword_distribution) }}</div>
                      <div v-if="e.top_features?.length" class="text-xs text-gray-600 dark:text-gray-300 mt-2">
                        <span class="text-gray-500 dark:text-gray-400">优势：</span>{{ e.top_features.slice(0, 5).map(x => x.text).join('、') }}
                      </div>
                      <div v-if="e.top_issues?.length" class="text-xs text-gray-600 dark:text-gray-300 mt-1">
                        <span class="text-gray-500 dark:text-gray-400">槽点：</span>{{ e.top_issues.slice(0, 5).map(x => x.text).join('、') }}
                      </div>
                    </div>
                    <div class="text-right shrink-0">
                      <div class="font-mono font-bold text-gray-900 dark:text-white">{{ Number(e.score || 0).toFixed(2) }}</div>
                      <div class="text-xs text-gray-500 dark:text-gray-400">提及 {{ e.mentions }}</div>
                    </div>
                  </div>
                </div>
              </div>
              <div v-else class="text-sm text-gray-400 py-4">暂无实体数据</div>
            </div>
          </div>
        </section>

        <!-- 4) 证据 -->
        <section class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 space-y-4">
          <h2 class="text-lg font-medium text-gray-900 dark:text-white">🧾 证据</h2>

          <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div class="p-3 rounded bg-gray-50 dark:bg-gray-800">
              <div class="text-sm font-medium text-gray-900 dark:text-white mb-2">Top 观点（可追溯）</div>
              <div v-if="topTopics.length" class="space-y-2">
                <div v-for="(t, idx) in topTopics.slice(0, 20)" :key="`topic-${idx}`" class="p-3 rounded bg-white/60 dark:bg-gray-900/30">
                  <div class="flex items-start justify-between gap-3">
                    <div class="min-w-0 flex-1">
                      <div class="flex items-center gap-2 flex-wrap">
                        <span class="text-gray-900 dark:text-white font-medium">{{ t.name }}</span>
                        <UBadge v-if="t.category" color="neutral" variant="subtle" size="xs">{{ t.category }}</UBadge>
                        <UBadge v-if="(t.sentiment ?? 0) < 0" color="error" variant="subtle" size="xs">负面</UBadge>
                        <UBadge v-else-if="(t.sentiment ?? 0) > 0" color="success" variant="subtle" size="xs">正面</UBadge>
                        <UBadge v-else color="neutral" variant="subtle" size="xs">中性</UBadge>
                      </div>
                      <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">平台：{{ formatDist(t.platform_distribution) }}</div>
                      <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">关键词：{{ formatDist(t.keyword_distribution) }}</div>
                      <div v-if="t.source_tasks?.length" class="text-xs text-gray-500 dark:text-gray-400 mt-1">
                        来源任务：{{ t.source_tasks.slice(0, 4).map(x => `#${x.task_id}:${x.mentions}`).join('，') }}
                      </div>
                      <div v-if="t.post_ids_sample?.length" class="text-xs text-gray-500 dark:text-gray-400 mt-1">
                        样本帖子：
                        <NuxtLink
                          v-for="(p, pIdx) in t.post_ids_sample.slice(0, 4)"
                          :key="`tp-${idx}-${pIdx}`"
                          class="text-primary-600 dark:text-primary-400 hover:underline mr-2"
                          :to="`/social-media/tasks/${p.task_id}`"
                        >
                          {{ `#${p.task_id}:${p.post_id}` }}
                        </NuxtLink>
                      </div>

                      <div v-if="t.original_terms?.length" class="mt-2">
                        <button class="text-xs text-primary-600 dark:text-primary-400 hover:underline" @click="toggleExpand(`topic-${idx}`)">
                          {{ isExpanded(`topic-${idx}`) ? '收起' : '展开' }} {{ t.original_terms.length }} 个原始词条
                        </button>
                        <div v-if="isExpanded(`topic-${idx}`)" class="mt-2 pl-3 border-l-2 border-gray-200 dark:border-gray-700">
                          <div v-for="(term, tIdx) in t.original_terms.slice(0, 15)" :key="tIdx" class="text-xs text-gray-600 dark:text-gray-400 py-0.5">
                            • {{ term.text }} <span class="text-gray-400">({{ term.count }})</span>
                          </div>
                        </div>
                      </div>
                    </div>
                    <div class="text-right shrink-0">
                      <div class="font-mono font-bold text-gray-900 dark:text-white">{{ Number(t.score || 0).toFixed(2) }}</div>
                      <div class="text-xs text-gray-500 dark:text-gray-400">提及 {{ t.mentions }}</div>
                    </div>
                  </div>
                </div>
              </div>
              <div v-else class="text-sm text-gray-400 py-4">暂无观点数据</div>
            </div>

            <div class="p-3 rounded bg-gray-50 dark:bg-gray-800">
              <div class="text-sm font-medium text-gray-900 dark:text-white mb-2">Top 实体（可追溯）</div>
              <div v-if="topEntities.length" class="space-y-2">
                <div v-for="(e, idx) in topEntities.slice(0, 20)" :key="`entity-${idx}`" class="p-3 rounded bg-white/60 dark:bg-gray-900/30">
                  <div class="flex items-start justify-between gap-3">
                    <div class="min-w-0 flex-1">
                      <div class="flex items-center gap-2 flex-wrap">
                        <span class="text-gray-900 dark:text-white font-medium">{{ e.name }}</span>
                        <UBadge v-if="e.role" color="neutral" variant="subtle" size="xs">{{ e.role }}</UBadge>
                        <UBadge v-if="e.type" color="info" variant="subtle" size="xs">{{ e.type }}</UBadge>
                      </div>
                      <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">平台：{{ formatDist(e.platform_distribution) }}</div>
                      <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">关键词：{{ formatDist(e.keyword_distribution) }}</div>
                      <div v-if="e.source_tasks?.length" class="text-xs text-gray-500 dark:text-gray-400 mt-1">
                        来源任务：{{ e.source_tasks.slice(0, 4).map(x => `#${x.task_id}:${x.mentions}`).join('，') }}
                      </div>
                      <div v-if="e.post_ids_sample?.length" class="text-xs text-gray-500 dark:text-gray-400 mt-1">
                        样本帖子：
                        <NuxtLink
                          v-for="(p, pIdx) in e.post_ids_sample.slice(0, 4)"
                          :key="`ep-${idx}-${pIdx}`"
                          class="text-primary-600 dark:text-primary-400 hover:underline mr-2"
                          :to="`/social-media/tasks/${p.task_id}`"
                        >
                          {{ `#${p.task_id}:${p.post_id}` }}
                        </NuxtLink>
                      </div>
                      <div v-if="e.original_terms?.length" class="mt-2">
                        <button class="text-xs text-primary-600 dark:text-primary-400 hover:underline" @click="toggleExpand(`entity-${idx}`)">
                          {{ isExpanded(`entity-${idx}`) ? '收起' : '展开' }} {{ e.original_terms.length }} 个原始词条
                        </button>
                        <div v-if="isExpanded(`entity-${idx}`)" class="mt-2 pl-3 border-l-2 border-gray-200 dark:border-gray-700">
                          <div v-for="(term, tIdx) in e.original_terms.slice(0, 15)" :key="tIdx" class="text-xs text-gray-600 dark:text-gray-400 py-0.5">
                            • {{ term.text }} <span class="text-gray-400">({{ term.count }})</span>
                          </div>
                        </div>
                      </div>
                    </div>
                    <div class="text-right shrink-0">
                      <div class="font-mono font-bold text-gray-900 dark:text-white">{{ Number(e.score || 0).toFixed(2) }}</div>
                      <div class="text-xs text-gray-500 dark:text-gray-400">提及 {{ e.mentions }}</div>
                    </div>
                  </div>
                </div>
              </div>
              <div v-else class="text-sm text-gray-400 py-4">暂无实体数据</div>
            </div>
          </div>
        </section>
        </template>
      </div>
    </ClientOnly>
  </div>
</template>
