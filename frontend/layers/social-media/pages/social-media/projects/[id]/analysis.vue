<script setup lang="ts">
import { computed, ref, watch, onMounted, onUnmounted } from 'vue'
import SOVRankingChart from '../../../../analysis/components/project/SOVRankingChart.vue'
import GroupShareTable from '../../../../analysis/components/project/GroupShareTable.vue'
import PlatformDNAChart from '../../../../analysis/components/project/PlatformDNAChart.vue'
import IndustryQuadrantChart from '../../../../analysis/components/project/IndustryQuadrantChart.vue'
import TopicRadarChart from '../../../../analysis/components/project/TopicRadarChart.vue'
import SWOTMatrixChart from '../../../../analysis/components/project/SWOTMatrixChart.vue'
import ProductLineHealthTable from '../../../../analysis/components/project/ProductLineHealthTable.vue'
import PlatformScissorsChart from '../../../../analysis/components/project/PlatformScissorsChart.vue'
import GapAnalysisChart from '../../../../analysis/components/project/GapAnalysisChart.vue'
import PostListModal from '../../../../analysis/components/PostListModal.vue'

definePageMeta({ layout: 'default' })

const toast = useToast()

// ==================== Types (new snapshot contract only) ====================
interface OriginalTerm { text: string; count: number }

interface SourceTask { task_id: number; mentions: number }

interface PostRef { task_id: number; post_id: number }

interface ProjectEntityAttrItem {
  text: string
  mentions: number
  original_terms?: OriginalTerm[]
  post_ids_sample?: PostRef[]
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
  post_ids_sample?: PostRef[]
  platform_distribution?: Record<string, number>
  keyword_distribution?: Record<string, number>
  role_breakdown?: Record<string, number>
  type_breakdown?: Record<string, number>
  top_features?: ProjectEntityAttrItem[]
  top_issues?: ProjectEntityAttrItem[]
}

interface ProjectOverviewData {
  total_volume?: number
  unique_posts?: number
  total_heat?: number
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

interface SOVRankingItem {
  name: string
  parent?: string
  role?: string
  heat: number
  mentions: number
  share: number
  sentiment?: number
  sentiment_distribution?: Record<string, number>
  platform_distribution?: Record<string, number>
  source_tasks?: SourceTask[]
  post_ids_sample?: PostRef[]
}

interface GroupShareItem {
  name: string
  heat: number
  mentions: number
}

interface PlatformDNAItem {
  name: string
  role?: string
  total_mentions: number
  platform_shares: Record<string, number>
}

interface IndustryQuadrantPoint {
  name: string
  role?: string
  heat: number
  sentiment: number
  mentions: number
  source_tasks?: SourceTask[]
  post_ids_sample?: PostRef[]
}

interface ProjectSnapshotLandscapeLayer {
  freshness?: {
    last_7_days_count?: number
    last_30_days_count?: number
    avg_age_days?: number
  }
  overview?: ProjectOverviewData
  sov_ranking?: SOVRankingItem[]
  group_share?: GroupShareItem[]
  platform_dna?: PlatformDNAItem[]
  industry_quadrant?: IndustryQuadrantPoint[]
}

interface ProjectSnapshotIntentLayer {
  topic_aspects?: ProjectTopicAspectItem[]
  topic_radar?: {
    pains?: ProjectTopicOrEntity[]
    gains?: ProjectTopicOrEntity[]
    controversies?: ProjectTopicOrEntity[]
  }
  unmet_needs?: ProjectTopicOrEntity[]
}

interface SWOTItem {
  dimension: string
  target_sentiment: number
  competitor_sentiment: number
  target_mentions: number
  competitor_mentions: number
  delta: number
}

interface SWOTData {
  strengths: SWOTItem[]
  weaknesses: SWOTItem[]
  opportunities: SWOTItem[]
  threats: SWOTItem[]
}

interface ProductLineHealthItem {
  name: string
  heat: number
  mentions: number
  contribution: number
  sentiment: number
  top_pain?: string
  platform_distribution?: Record<string, number>
}

interface ProductLineHealthData {
  subject: string
  total_heat: number
  members: ProductLineHealthItem[]
}

interface PlatformScissorsItem {
  platform: string
  subject_mentions: number
  industry_mentions: number
  subject_share: number
  industry_share: number
  delta: number
}

interface PlatformScissorsData {
  subject_total_mentions: number
  industry_total_mentions: number
  by_platform: PlatformScissorsItem[]
}

interface GapData {
  dimensions: SWOTItem[]
}

interface ProjectSnapshotFocusLayer {
  subject?: string
  targets?: string[]
  competitors?: string[]
  swot?: SWOTData | null
  product_line_health?: ProductLineHealthData | null
  platform_scissors?: PlatformScissorsData | null
  gap?: GapData | null
}

interface ProjectSnapshotLayers {
  landscape?: ProjectSnapshotLandscapeLayer
  intent?: ProjectSnapshotIntentLayer
  focus?: ProjectSnapshotFocusLayer | null
}

interface ProjectSnapshotReport {
  content?: string
}

interface ProjectSnapshotReports {
  landscape_report?: ProjectSnapshotReport | null
  topic_report?: ProjectSnapshotReport | null
  focus_report?: ProjectSnapshotReport | null
}

interface ProjectSnapshotFoundation {
  dedup_stats?: Record<string, unknown>
  aligned_entities?: ProjectTopicOrEntity[]
  aligned_topics?: ProjectTopicOrEntity[]
}

interface ProjectSnapshotResultData {
  meta?: {
    project_id: number
    generated_at: string
    subject?: string | null
    competitors?: string[]
    weights_used?: Record<string, number>
    scope?: Record<string, unknown>
  }
  foundation?: ProjectSnapshotFoundation
  layers?: ProjectSnapshotLayers
  reports?: ProjectSnapshotReports
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
const stage2 = computed(() => snapshotResult.value?.stage2 || null)
const stage3 = computed(() => snapshotResult.value?.stage3 || null)

const meta = computed(() => snapshotResult.value?.meta || null)
const competitors = computed(() => (meta.value?.competitors || []))
const foundation = computed(() => snapshotResult.value?.foundation || null)
const layers = computed(() => snapshotResult.value?.layers || null)
const reports = computed(() => snapshotResult.value?.reports || null)

const landscape = computed<ProjectSnapshotLandscapeLayer | null>(() => layers.value?.landscape || null)
const overview = computed<ProjectOverviewData | null>(() => landscape.value?.overview || null)
const freshness = computed(() => landscape.value?.freshness || null)
const intent = computed(() => layers.value?.intent || null)
const focus = computed<ProjectSnapshotFocusLayer | null>(() => layers.value?.focus || null)
const topEntities = computed<ProjectTopicOrEntity[]>(() => foundation.value?.aligned_entities || [])
const topTopics = computed<ProjectTopicOrEntity[]>(() => foundation.value?.aligned_topics || [])

// ==================== Landscape Layer Data ====================
const sovRanking = computed(() => landscape.value?.sov_ranking || [])
const groupShare = computed(() => landscape.value?.group_share || [])
const platformDNA = computed(() => landscape.value?.platform_dna || [])
const industryQuadrant = computed(() => landscape.value?.industry_quadrant || [])

const selectedLandscapeEntity = ref<string | null>(null)
const handleSelectLandscapeEntity = (item: { name: string } | null) => {
  const name = (item?.name || '').toString().trim()
  if (!name) return
  selectedLandscapeEntity.value = selectedLandscapeEntity.value === name ? null : name
}
const postListModalOpen = ref(false)
const postListModalTitle = ref('')
const postListModalTaskId = ref<number | null>(null)
const postListModalPostIds = ref<number[]>([])

const groupPostIdsByTask = (postRefs?: PostRef[]) => {
  const groups = new Map<number, Set<number>>()
  for (const postRef of postRefs || []) {
    const taskId = Number(postRef?.task_id)
    const postId = Number(postRef?.post_id)
    if (!Number.isFinite(taskId) || !Number.isFinite(postId) || taskId <= 0 || postId <= 0) continue
    if (!groups.has(taskId)) groups.set(taskId, new Set())
    groups.get(taskId)?.add(postId)
  }
  return Array.from(groups.entries())
    .map(([taskId, postIds]) => ({ taskId, postIds: Array.from(postIds) }))
    .sort((a, b) => b.postIds.length - a.postIds.length)
}

const openLandscapePostList = (item: { name?: string; post_ids_sample?: PostRef[] } | null) => {
  if (!item) return
  const name = (item.name || '').toString().trim()
  const groups = groupPostIdsByTask(item.post_ids_sample)
  if (!groups.length) {
    toast.add({
      title: '暂无可追溯帖子',
      description: name ? `${name} 未提供帖子样本` : '未提供帖子样本',
      color: 'warning',
    })
    return
  }
  const primary = groups[0]
  if (!primary) return
  const { taskId, postIds } = primary
  postListModalTaskId.value = taskId
  postListModalPostIds.value = postIds
  postListModalTitle.value = `${name || '实体'} 相关内容（样本） · 任务 #${taskId}`
  postListModalOpen.value = true
}

const openTopicPostList = (item: { name?: string; post_ids_sample?: PostRef[] } | null, type?: string) => {
  if (!item) return
  const name = (item.name || '').toString().trim()
  const groups = groupPostIdsByTask(item.post_ids_sample)
  if (!groups.length) {
    toast.add({
      title: '暂无可追溯帖子',
      description: name ? `${name} 未提供帖子样本` : '未提供帖子样本',
      color: 'warning',
    })
    return
  }
  const primary = groups[0]
  if (!primary) return
  const { taskId, postIds } = primary
  postListModalTaskId.value = taskId
  postListModalPostIds.value = postIds
  const typeLabel = type === 'pain' ? '痛点' : type === 'gain' ? '爽点' : type === 'controversy' ? '争议点' : type === 'unmet' ? '未被满足需求' : '话题'
  postListModalTitle.value = `${typeLabel} · ${name || '话题'} 相关内容（样本） · 任务 #${taskId}`
  postListModalOpen.value = true
}

const openFocusPostList = (item: { name?: string; post_ids_sample?: PostRef[] } | null, type?: string) => {
  if (!item) return
  const name = (item.name || '').toString().trim()
  const groups = groupPostIdsByTask(item.post_ids_sample)
  if (!groups.length) {
    toast.add({
      title: '暂无可追溯帖子',
      description: '聚焦层当前仅对“产品线健康度”提供帖子样本；SWOT/Gap 为竞品集合聚合，暂不支持追溯到帖子。',
      color: 'warning',
    })
    return
  }
  const primary = groups[0]
  if (!primary) return
  const { taskId, postIds } = primary
  postListModalTaskId.value = taskId
  postListModalPostIds.value = postIds
  const typeLabel = type === 'product-line' ? '产品线' : type === 'swot' ? 'SWOT' : type === 'gap' ? 'Gap' : '聚焦层'
  postListModalTitle.value = `${typeLabel} · ${name || '条目'} 相关内容（样本） · 任务 #${taskId}`
  postListModalOpen.value = true
}

const handleSwotSelect = () => {
  toast.add({
    title: '聚焦层维度暂不支持追溯到帖子',
    description: '当前 SWOT 为“竞品集合聚合均值”口径，缺少维度→帖子映射；可先用话题层/证据区验证原话与样本。',
    color: 'warning',
  })
}

const handleGapSelect = () => {
  toast.add({
    title: '聚焦层维度暂不支持追溯到帖子',
    description: '当前 Gap 为“竞品集合聚合均值”口径，缺少维度→帖子映射；可先用话题层/证据区验证原话与样本。',
    color: 'warning',
  })
}

const handleIndustryQuadrantSelect = (item: IndustryQuadrantPoint | null) => {
  if (!item) return
  handleSelectLandscapeEntity(item)
  openLandscapePostList(item)
}

watch(snapshotId, () => {
  selectedLandscapeEntity.value = null
  postListModalOpen.value = false
  postListModalTaskId.value = null
  postListModalPostIds.value = []
  postListModalTitle.value = ''
})

// ==================== Topic Layer Data ====================
const topicRadar = computed(() => intent.value?.topic_radar || null)
const unmetNeeds = computed(() => intent.value?.unmet_needs || [])

// ==================== Focus Layer Data ====================
const swotData = computed(() => focus.value?.swot || null)
const productLineHealth = computed(() => focus.value?.product_line_health || null)
const platformScissors = computed(() => focus.value?.platform_scissors || null)
const gapData = computed(() => focus.value?.gap || null)

const subject = computed(() => (meta.value?.subject || '').toString().trim())
const showFocusLayer = computed(() => Boolean(subject.value))
const showFocusReport = computed(() => Boolean(subject.value))

// 注意：Stage2 完成后 Stage3 仍可能继续生成报告（不应提前停止轮询）
const isPipelineReady = computed(() => stage2.value?.status === 'completed')
const isPipelineRunning = computed(() => {
  const s2 = stage2.value?.status
  const s3 = stage3.value?.status
  return s2 === 'processing' || s3 === 'pending' || s3 === 'processing'
})
const isReportsReady = computed(() => stage3.value?.status === 'completed')
const isReportsFailed = computed(() => stage3.value?.status === 'failed')

const reportLandscape = computed(() => reports.value?.landscape_report?.content || '')
const reportTopic = computed(() => reports.value?.topic_report?.content || '')
const reportFocus = computed(() => reports.value?.focus_report?.content || '')

// ==================== 自动轮询机制（优化：只检查状态，避免页面跳动）====================
let pollTimer: ReturnType<typeof setInterval> | null = null
const lastPolledStatus = ref<{ stage2?: string; stage3?: string }>({})

const { apiRequest } = useApi()

// 轮询时只检查状态，不触发完整数据刷新
const pollStatus = async () => {
  if (!snapshotId.value) return

  try {
    // 使用 apiRequest 获取最新数据（不会触发 useApiData 的响应式更新）
    const freshData = await apiRequest<ProjectSnapshot>(
      `/social-media/analysis/projects/${projectId.value}/snapshots/${snapshotId.value}`
    )
    if (!freshData) return

    const newStage2Status = freshData.result_data?.stage2?.status
    const newStage3Status = freshData.result_data?.stage3?.status
    const oldStage2Status = lastPolledStatus.value.stage2
    const oldStage3Status = lastPolledStatus.value.stage3

    // 更新状态缓存
    lastPolledStatus.value = { stage2: newStage2Status, stage3: newStage3Status }

    // 只有当状态发生变化时，才刷新完整数据（触发图表更新）
    const statusChanged = newStage2Status !== oldStage2Status || newStage3Status !== oldStage3Status
    const isCompleted = newStage3Status === 'completed' || newStage3Status === 'failed'

    if (statusChanged || isCompleted) {
      await refreshSnapshot()
    }
  } catch (e) {
    // 静默失败，避免轮询错误打断用户操作
    console.warn('[Snapshot Poll] Status check failed:', e)
  }
}

const startPolling = () => {
  if (pollTimer) return
  // 初始化状态缓存
  lastPolledStatus.value = {
    stage2: stage2.value?.status,
    stage3: stage3.value?.status,
  }
  pollTimer = setInterval(pollStatus, 3000)
}

const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// 监听 Stage3：报告完成才停止轮询（Stage2 完成并不代表报告已落库）
watch(isReportsReady, (ready, wasReady) => {
  if (ready && !wasReady) {
    stopPolling()
    toast.add({
      title: '报告生成完成',
      description: '项目快照分析已完成',
      color: 'success',
    })
  }
})

watch(isReportsFailed, (failed, wasFailed) => {
  if (failed && !wasFailed) {
    stopPolling()
    toast.add({
      title: '报告生成失败',
      description: stage3.value?.error || '请稍后重试或查看后端日志',
      color: 'error',
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
  if (isPipelineRunning.value) startPolling()
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

const volumeStats = computed(() => {
  const total = overview.value?.total_volume
  const unique = overview.value?.unique_posts
  if (typeof total !== 'number' || typeof unique !== 'number' || total <= 0) return null
  const duplicates = Math.max(total - unique, 0)
  const duplicateRate = total > 0 ? duplicates / total : 0
  return { total, unique, duplicates, duplicateRate }
})

const displayedPlatformVolume = computed(() => sortedPlatformVolume.value.slice(0, 8))
const overflowPlatformVolumeCount = computed(() => Math.max(sortedPlatformVolume.value.length - displayedPlatformVolume.value.length, 0))

const displayedKeywordVolume = computed(() => sortedKeywordVolume.value.slice(0, 12))
const overflowKeywordVolumeCount = computed(() => Math.max(sortedKeywordVolume.value.length - displayedKeywordVolume.value.length, 0))

const formatNumber = (n: number) => {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return n.toString()
}

const formatCompactNumber = (n: number) => {
  if (n >= 10000) return `${(n / 10000).toFixed(1)}w`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return n.toString()
}

const formatDist = (dist?: Record<string, number>) => {
  if (!dist) return '-'
  const entries = Object.entries(dist).sort((a, b) => (b[1] || 0) - (a[1] || 0)).slice(0, 4)
  return entries.map(([k, v]) => `${k}:${v}`).join('，')
}

const takeReportPreview = (text: string, maxLines: number = 18) => {
  const lines = (text || '').toString().split('\n')
  if (lines.length <= maxLines) return text
  return `${lines.slice(0, maxLines).join('\n')}\n…（已折叠）`
}

const isReportLong = (text: string, maxLines: number = 18) => {
  const lines = (text || '').toString().split('\n')
  return lines.length > maxLines
}

const extractQuoteLines = (items: Array<{ name?: string; original_terms?: OriginalTerm[] }>, limit: number = 18) => {
  const lines: string[] = []
  for (const item of items || []) {
    const name = (item?.name || '').toString().trim()
    const ots = item?.original_terms || []
    for (const ot of ots.slice(0, 2)) {
      if (!ot?.text) continue
      lines.push(`${name ? `[${name}] ` : ''}${ot.text}`)
      if (lines.length >= limit) return lines
    }
  }
  return lines
}

type QuoteItem = { name?: string; original_terms?: OriginalTerm[]; role?: string; sentiment?: number }

const reportEvidenceLandscape = computed(() => extractQuoteLines(topEntities.value.slice(0, 20), 18))
const reportEvidenceTopic = computed(() => {
  const radar = (topicRadar.value || {}) as {
    pains?: QuoteItem[]
    gains?: QuoteItem[]
    controversies?: QuoteItem[]
  }
  const unmet = (unmetNeeds.value || []) as QuoteItem[]
  const items: QuoteItem[] = [
    ...(radar.pains || []),
    ...(radar.gains || []),
    ...(radar.controversies || []),
    ...unmet,
  ]
  return extractQuoteLines(items, 18)
})
const reportEvidenceFocus = computed(() => {
  const all = topEntities.value || []
  const targetNeg = all.filter(x => ((x.role || '').toString().toLowerCase().includes('target')) && (Number(x.sentiment || 0) <= -0.1))
  const compPos = all.filter(x => ((x.role || '').toString().toLowerCase().includes('competitor')) && (Number(x.sentiment || 0) >= 0.1))
  return extractQuoteLines([...targetNeg, ...compPos].slice(0, 20), 18)
})


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

const copyText = async (text: string) => {
  const s = (text || '').toString()
  if (!s) return
  try {
    await navigator.clipboard.writeText(s)
    toast.add({ title: '已复制到剪贴板', color: 'success' })
  } catch {
    toast.add({ title: '复制失败', description: '请检查浏览器权限或手动复制', color: 'error' })
  }
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
            项目级合并分析快照
          </p>
          <ClientOnly>
            <div class="flex items-center gap-3 mt-1 text-sm">
              <div v-if="subject" class="flex items-center gap-1.5">
                <span class="text-gray-500">主体:</span>
                <UBadge color="primary" variant="subtle" size="xs">{{ subject }}</UBadge>
              </div>
              <div v-if="competitors?.length" class="flex items-center gap-1.5">
                <span class="text-gray-500">竞品:</span>
                <div class="flex gap-1">
                  <UBadge v-for="c in competitors" :key="c" color="amber" variant="subtle" size="xs">{{ c }}</UBadge>
                </div>
              </div>
              <span v-if="!subject && !competitors?.length" class="text-gray-500">
                全景模式 (Landscape Only)
              </span>
            </div>
          </ClientOnly>
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
              实体归一与观点归一会并行触发；完成后再进行程序化分析与三报告生成。进度以快照自身的执行状态为准。
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
                  <span class="font-medium text-gray-900 dark:text-white">报告生成</span>
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
            为保证口径一致与结论可靠，报告生成完成前将不展示三报告原声与下方指标板块。请稍候并点击右上角“刷新”查看进度。
          </div>
        </section>

        <!-- 报告未完成：不展示下方板块 -->
        <template v-if="isPipelineReady">
        <!-- 三报告（原声展示） -->
        <section class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 space-y-3">
          <div class="flex items-center justify-between gap-4">
            <h2 class="text-lg font-medium text-gray-900 dark:text-white">🧾 三报告（原声）</h2>
            <div class="text-xs text-gray-500 dark:text-gray-400">
              <span class="font-mono">{{ stage3?.status || 'pending' }}</span>
            </div>
          </div>

          <div v-if="!isReportsReady" class="text-xs text-gray-500 dark:text-gray-400">
            报告生成中（或失败）。完成后将展示：行业格局 / 话题洞察 /（可选）战略诊断 的原声内容。
            <span v-if="stage3?.status === 'failed' && stage3?.error" class="ml-2">错误：{{ stage3.error }}</span>
          </div>

          <div v-else class="space-y-4">
            <div class="p-3 rounded bg-gray-50 dark:bg-gray-800">
              <div class="flex items-center justify-between gap-3 mb-2">
                <div class="text-xs text-gray-500 dark:text-gray-400">行业格局（Market Analyst）</div>
                <div class="flex items-center gap-2">
                  <UButton size="xs" variant="ghost" icon="i-heroicons-clipboard" :disabled="!reportLandscape" @click="copyText(reportLandscape)">
                    复制
                  </UButton>
                  <UButton
                    v-if="reportLandscape && isReportLong(reportLandscape)"
                    size="xs"
                    variant="ghost"
                    @click="toggleExpand('report-landscape')"
                  >
                    {{ isExpanded('report-landscape') ? '收起' : '展开全文' }}
                  </UButton>
                  <UButton
                    v-if="reportLandscape && reportEvidenceLandscape.length"
                    size="xs"
                    variant="ghost"
                    @click="toggleExpand('report-landscape-evidence')"
                  >
                    {{ isExpanded('report-landscape-evidence') ? '收起证据' : '查看证据' }}
                  </UButton>
                </div>
              </div>
              <div class="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap leading-relaxed">
                {{ reportLandscape ? (isExpanded('report-landscape') ? reportLandscape : takeReportPreview(reportLandscape)) : '-' }}
              </div>
              <div v-if="reportEvidenceLandscape.length && isExpanded('report-landscape-evidence')" class="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
                <div class="text-xs text-gray-500 dark:text-gray-400 mb-2">证据原话（节选）</div>
                <div class="space-y-1 text-xs text-gray-700 dark:text-gray-300">
                  <div v-for="(line, idx) in reportEvidenceLandscape" :key="`re-land-${idx}`" class="truncate" :title="line">
                    • {{ line }}
                  </div>
                </div>
              </div>
            </div>

            <div class="p-3 rounded bg-gray-50 dark:bg-gray-800">
              <div class="flex items-center justify-between gap-3 mb-2">
                <div class="text-xs text-gray-500 dark:text-gray-400">话题洞察（Product Manager）</div>
                <div class="flex items-center gap-2">
                  <UButton size="xs" variant="ghost" icon="i-heroicons-clipboard" :disabled="!reportTopic" @click="copyText(reportTopic)">
                    复制
                  </UButton>
                  <UButton
                    v-if="reportTopic && isReportLong(reportTopic)"
                    size="xs"
                    variant="ghost"
                    @click="toggleExpand('report-topic')"
                  >
                    {{ isExpanded('report-topic') ? '收起' : '展开全文' }}
                  </UButton>
                  <UButton
                    v-if="reportTopic && reportEvidenceTopic.length"
                    size="xs"
                    variant="ghost"
                    @click="toggleExpand('report-topic-evidence')"
                  >
                    {{ isExpanded('report-topic-evidence') ? '收起证据' : '查看证据' }}
                  </UButton>
                </div>
              </div>
              <div class="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap leading-relaxed">
                {{ reportTopic ? (isExpanded('report-topic') ? reportTopic : takeReportPreview(reportTopic)) : '-' }}
              </div>
              <div v-if="reportEvidenceTopic.length && isExpanded('report-topic-evidence')" class="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
                <div class="text-xs text-gray-500 dark:text-gray-400 mb-2">证据原话（节选）</div>
                <div class="space-y-1 text-xs text-gray-700 dark:text-gray-300">
                  <div v-for="(line, idx) in reportEvidenceTopic" :key="`re-topic-${idx}`" class="truncate" :title="line">
                    • {{ line }}
                  </div>
                </div>
              </div>
            </div>

            <!-- Focus 为空时隐藏“战略诊断” -->
            <div v-if="showFocusReport" class="p-3 rounded bg-gray-50 dark:bg-gray-800">
              <div class="flex items-center justify-between gap-3 mb-2">
                <div class="text-xs text-gray-500 dark:text-gray-400">战略诊断（CSO / AI 顾问）</div>
                <div class="flex items-center gap-2">
                  <UButton size="xs" variant="ghost" icon="i-heroicons-clipboard" :disabled="!reportFocus" @click="copyText(reportFocus)">
                    复制
                  </UButton>
                  <UButton
                    v-if="reportFocus && isReportLong(reportFocus)"
                    size="xs"
                    variant="ghost"
                    @click="toggleExpand('report-focus')"
                  >
                    {{ isExpanded('report-focus') ? '收起' : '展开全文' }}
                  </UButton>
                  <UButton
                    v-if="reportFocus && reportEvidenceFocus.length"
                    size="xs"
                    variant="ghost"
                    @click="toggleExpand('report-focus-evidence')"
                  >
                    {{ isExpanded('report-focus-evidence') ? '收起证据' : '查看证据' }}
                  </UButton>
                </div>
              </div>
              <div v-if="!reportFocus" class="text-xs text-gray-500 dark:text-gray-400">
                Focus 报告为空：可能未配置主体 subject，或输出未满足“营销/产品/公关”三段式硬约束。
              </div>
              <div v-else class="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap leading-relaxed">
                {{ isExpanded('report-focus') ? reportFocus : takeReportPreview(reportFocus) }}
              </div>
              <div v-if="reportEvidenceFocus.length && isExpanded('report-focus-evidence')" class="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
                <div class="text-xs text-gray-500 dark:text-gray-400 mb-2">证据原话（节选）</div>
                <div class="space-y-1 text-xs text-gray-700 dark:text-gray-300">
                  <div v-for="(line, idx) in reportEvidenceFocus" :key="`re-focus-${idx}`" class="truncate" :title="line">
                    • {{ line }}
                  </div>
                </div>
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

          <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            <!-- 内容量 -->
            <div class="space-y-1">
              <div class="text-xs text-gray-500 dark:text-gray-400">去重内容量 (Unique Posts)</div>
              <div class="flex items-baseline gap-2">
                <span class="text-2xl font-mono font-semibold text-gray-900 dark:text-white">
                  {{ typeof overview?.unique_posts === 'number' ? formatNumber(overview.unique_posts) : '-' }}
                </span>
                <span class="text-xs text-gray-500 dark:text-gray-400">帖</span>
              </div>
              <div class="text-xs text-gray-400 mt-1">
                任务汇总：{{ typeof overview?.total_volume === 'number' ? formatNumber(overview.total_volume) : '-' }}
                <template v-if="volumeStats">
                  · 重复：{{ formatNumber(volumeStats.duplicates) }} ({{ (volumeStats.duplicateRate * 100).toFixed(1) }}%)
                </template>
              </div>
            </div>

            <!-- 情感 -->
            <div class="space-y-1">
              <div class="text-xs text-gray-500 dark:text-gray-400">全局情感 (Sentiment)</div>
              <div class="flex items-center gap-2">
                <span 
                  class="text-2xl font-mono font-semibold"
                  :class="(overview?.global_sentiment || 0) >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'"
                >
                  {{ typeof overview?.global_sentiment === 'number' ? overview.global_sentiment.toFixed(2) : '-' }}
                </span>
              </div>
              <div class="text-xs text-gray-400 mt-1">
                NSR 指数（按任务量加权，-1 ~ +1）
              </div>
            </div>

            <!-- 时效性 -->
            <div class="space-y-1">
              <div class="text-xs text-gray-500 dark:text-gray-400">时效性 (Freshness)</div>
              <div class="flex items-baseline gap-2">
                <span class="text-lg font-mono font-semibold text-gray-900 dark:text-white">
                  {{ freshness?.avg_age_days ? freshness.avg_age_days.toFixed(1) : '-' }}
                </span>
                <span class="text-xs text-gray-500">天 (平均)</span>
              </div>
              <div class="flex items-center gap-3 text-xs text-gray-500 dark:text-gray-400 mt-1">
                <div class="flex items-center gap-1" title="最近7天内容数">
                  <span class="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                  7d: <span class="font-mono text-gray-700 dark:text-gray-300">{{ freshness?.last_7_days_count ?? '-' }}</span>
                </div>
                <div class="flex items-center gap-1" title="最近30天内容数">
                  <span class="w-1.5 h-1.5 rounded-full bg-blue-500" />
                  30d: <span class="font-mono text-gray-700 dark:text-gray-300">{{ freshness?.last_30_days_count ?? '-' }}</span>
                </div>
              </div>
            </div>

            <!-- 平台分布 -->
            <div class="space-y-1">
              <div class="text-xs text-gray-500 dark:text-gray-400">平台分布 (Task Volume)</div>
              <div class="flex flex-wrap gap-1.5 mt-1">
                <div 
                  v-for="([k, v]) in displayedPlatformVolume" 
                  :key="k" 
                  class="flex items-center gap-1 text-xs px-1.5 py-0.5 rounded bg-gray-50 dark:bg-gray-800/50 border border-gray-100 dark:border-gray-800"
                >
                  <span class="text-gray-700 dark:text-gray-300">{{ k }}</span>
                  <span class="text-[10px] text-gray-400 font-mono">{{ formatCompactNumber(v) }}</span>
                </div>
                <div
                  v-if="overflowPlatformVolumeCount > 0"
                  class="text-xs px-1.5 py-0.5 rounded bg-gray-50 dark:bg-gray-800/50 border border-gray-100 dark:border-gray-800 text-gray-500 dark:text-gray-400"
                >
                  +{{ overflowPlatformVolumeCount }}
                </div>
                <div v-if="!displayedPlatformVolume.length" class="text-xs text-gray-400 py-1">-</div>
              </div>
            </div>
          </div>

          <!-- 配置回顾：关键词来自任务配置（非内容关键词） -->
          <div class="mt-4 pt-4 border-t border-gray-100 dark:border-gray-800">
            <div class="flex items-center justify-between gap-3">
              <div class="text-xs text-gray-500 dark:text-gray-400">任务关键词 (Task Keyword)</div>
              <div class="text-[10px] text-gray-400 dark:text-gray-500">来自所选任务的 keyword 字段</div>
            </div>
            <div class="flex flex-wrap gap-1.5 mt-2">
              <div
                v-for="([k, v]) in displayedKeywordVolume"
                :key="k"
                class="flex items-center gap-1 text-xs px-1.5 py-0.5 rounded bg-gray-50 dark:bg-gray-800/50 border border-gray-100 dark:border-gray-800"
              >
                <span class="text-gray-700 dark:text-gray-300">{{ k }}</span>
                <span class="text-[10px] text-gray-400 font-mono">{{ formatCompactNumber(v) }}</span>
              </div>
              <div
                v-if="overflowKeywordVolumeCount > 0"
                class="text-xs px-1.5 py-0.5 rounded bg-gray-50 dark:bg-gray-800/50 border border-gray-100 dark:border-gray-800 text-gray-500 dark:text-gray-400"
              >
                +{{ overflowKeywordVolumeCount }}
              </div>
              <div v-if="!displayedKeywordVolume.length" class="text-xs text-gray-400 py-1">-</div>
            </div>
          </div>
        </section>

        <!-- ===== Landscape Layer (大盘层) ===== -->
        <section class="space-y-4">
          <h2 class="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <span class="w-6 h-6 rounded bg-primary-100 dark:bg-primary-900/30 flex items-center justify-center text-xs text-primary-700 dark:text-primary-400">1</span>
            大盘层 (Landscape)
          </h2>
          <p class="text-xs text-gray-500 dark:text-gray-400">上帝视角：全量实体 (Target + Competitor + Context)</p>

          <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <SOVRankingChart
              :data="sovRanking"
              :max-items="15"
              :selected="selectedLandscapeEntity"
              @select="handleSelectLandscapeEntity"
            />
            <IndustryQuadrantChart
              :data="industryQuadrant"
              :selected="selectedLandscapeEntity"
              @select="handleIndustryQuadrantSelect"
            />
          </div>

          <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <GroupShareTable :data="groupShare" :entities="topEntities" :max-items="10" />
            <PlatformDNAChart :data="platformDNA" :max-items="10" />
          </div>
        </section>

        <!-- ===== Topic Layer (话题层) ===== -->
        <section class="space-y-4">
          <h2 class="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <span class="w-6 h-6 rounded bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center text-xs text-amber-700 dark:text-amber-400">2</span>
            话题层 (Topic)
          </h2>
          <p class="text-xs text-gray-500 dark:text-gray-400">产品经理/舆情官视角：全量话题（不区分实体归属）</p>

          <TopicRadarChart
            :pains="topicRadar?.pains"
            :gains="topicRadar?.gains"
            :controversies="topicRadar?.controversies"
            :unmet-needs="unmetNeeds"
            @open-posts="openTopicPostList"
          />
        </section>

        <!-- ===== Focus Layer (聚焦层) - 条件触发 ===== -->
        <section v-if="showFocusLayer" class="space-y-4">
          <h2 class="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <span class="w-6 h-6 rounded bg-rose-100 dark:bg-rose-900/30 flex items-center justify-center text-xs text-rose-700 dark:text-rose-400">3</span>
            聚焦层 (Focus)
          </h2>
          <p class="text-xs text-gray-500 dark:text-gray-400">
            战略官视角：仅限 Target 和 Competitor · 分析主体：<span class="font-medium text-gray-700 dark:text-gray-300">{{ subject }}</span>
          </p>

          <SWOTMatrixChart :data="swotData" :subject="subject" @select="handleSwotSelect" />

          <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <ProductLineHealthTable :data="productLineHealth" @open-posts="(item) => openFocusPostList(item, 'product-line')" />
            <PlatformScissorsChart :data="platformScissors" :subject="subject" />
          </div>

          <GapAnalysisChart :data="gapData" :subject="subject" @select="handleGapSelect" />
        </section>

        <!-- 证据 -->
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

        <PostListModal
          v-if="postListModalTaskId !== null"
          v-model:open="postListModalOpen"
          :task-id="postListModalTaskId"
          :post-ids="postListModalPostIds"
          :title="postListModalTitle"
        />
        </template>
      </div>
    </ClientOnly>
  </div>
</template>
