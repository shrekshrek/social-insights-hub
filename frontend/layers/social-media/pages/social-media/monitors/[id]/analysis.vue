<script setup lang="ts">
import { computed, ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import SOVRankingChart from '../../../../analysis/components/slice/SOVRankingChart.vue'
import GroupShareTable from '../../../../analysis/components/slice/GroupShareTable.vue'
import PlatformDNAChart from '../../../../analysis/components/slice/PlatformDNAChart.vue'
import IndustryQuadrantChart from '../../../../analysis/components/slice/IndustryQuadrantChart.vue'
import TopicRadarChart from '../../../../analysis/components/slice/TopicRadarChart.vue'
import SWOTMatrixChart from '../../../../analysis/components/slice/SWOTMatrixChart.vue'
import ProductLineHealthTable from '../../../../analysis/components/slice/ProductLineHealthTable.vue'
import PlatformScissorsChart from '../../../../analysis/components/slice/PlatformScissorsChart.vue'
import GapAnalysisChart from '../../../../analysis/components/slice/GapAnalysisChart.vue'
import PostListModal from '../../../../analysis/components/shared/PostListModal.vue'
import SpamRatioBar from '../../../../analysis/components/shared/SpamRatioBar.vue'
// MarkdownRenderer 由 ui-kit layer 自动注册
import type { SpamDistribution } from '../../../../analysis/types'

definePageMeta({ layout: 'default' })

const toast = useToast()

// ==================== Types (new slice contract only) ====================
interface OriginalTerm { text: string; count: number }

interface SourceTask { task_id: number; mentions: number }

interface PostRef { task_id: number; post_id: number }

interface SliceEntityAttrItem {
  text: string
  mentions: number
  original_terms?: OriginalTerm[]
  post_ids_sample?: PostRef[]
  platform_distribution?: Record<string, number>
  keyword_distribution?: Record<string, number>
}

interface SliceTopicOrEntity {
  name: string
  category?: string
  sentiment?: number
  /** 有机内容情感（spam_score < 6.0 的原文） */
  organic_sentiment?: number
  /** 推广内容情感（spam_score >= 6.0 的原文） */
  promo_sentiment?: number
  organic_heat?: number
  promo_heat?: number
  role?: string
  type?: string
  heat: number
  mentions: number
  score: number
  original_terms?: OriginalTerm[]
  source_tasks?: SourceTask[]
  post_ids_sample?: PostRef[]
  spam_distribution?: SpamDistribution
  platform_distribution?: Record<string, number>
  keyword_distribution?: Record<string, number>
  role_breakdown?: Record<string, number>
  type_breakdown?: Record<string, number>
  top_features?: SliceEntityAttrItem[]
  top_issues?: SliceEntityAttrItem[]
}

interface SliceOverviewData {
  total_volume?: number
  unique_posts?: number
  total_heat?: number
  total_organic_heat?: number
  total_promo_heat?: number
  global_nsr?: number
  organic_nsr?: number | null
  promo_nsr?: number | null
  platform_volume?: Record<string, number>
  keyword_volume?: Record<string, number>
}

interface SliceTopicAspectItem {
  category: string
  heat: number
  organic_heat?: number
  promo_heat?: number
  sentiment: number
  mention_count?: number
  representative_topics?: string[]
  platform_distribution?: Record<string, number>
  keyword_distribution?: Record<string, number>
}

interface SOVRankingItem {
  name: string
  parent?: string
  role?: string
  heat: number
  organic_heat?: number
  promo_heat?: number
  mentions: number
  share: number
  sentiment?: number
  organic_sentiment?: number
  promo_sentiment?: number
  sentiment_distribution?: Record<string, number>
  platform_distribution?: Record<string, number>
  source_tasks?: SourceTask[]
  post_ids_sample?: PostRef[]
  spam_distribution?: SpamDistribution
}

interface GroupShareItem {
  name: string
  parent?: string
  heat: number
  organic_heat?: number
  promo_heat?: number
  total_heat?: number
  mentions: number
  total_mentions?: number
  share?: number
  role?: string
  sentiment?: number
  organic_sentiment?: number
  promo_sentiment?: number
  contribution?: number
  spam_distribution?: SpamDistribution
  platform_distribution?: Record<string, number>
  organic_platform_distribution?: Record<string, number>
  promo_platform_distribution?: Record<string, number>
  post_ids_sample?: PostRef[]
  source_tasks?: SourceTask[]
  members?: Array<{
    name: string
    heat: number
    mentions: number
    contribution: number
    spam_distribution?: SpamDistribution
  }>
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
  organic_heat?: number
  promo_heat?: number
  sentiment: number
  organic_sentiment?: number
  promo_sentiment?: number
  mentions: number
  source_tasks?: SourceTask[]
  post_ids_sample?: PostRef[]
  spam_distribution?: SpamDistribution
}

interface SliceLandscapeLayer {
  freshness?: {
    last_7_days_count?: number
    last_30_days_count?: number
    avg_age_days?: number
  }
  overview?: SliceOverviewData
  sov_ranking?: SOVRankingItem[]
  group_share?: GroupShareItem[]
  platform_dna?: PlatformDNAItem[]
  platform_dna_grouped?: PlatformDNAItem[]
  industry_quadrant?: IndustryQuadrantPoint[]
}

interface SliceIntentLayer {
  topic_aspects?: SliceTopicAspectItem[]
  topic_radar?: {
    pains?: SliceTopicOrEntity[]
    gains?: SliceTopicOrEntity[]
    controversies?: SliceTopicOrEntity[]
  }
  unmet_needs?: SliceTopicOrEntity[]
}

interface SWOTItem {
  dimension: string
  target_sentiment: number
  competitor_sentiment: number
  target_mentions: number
  competitor_mentions: number
  delta: number
  target_organic_sentiment?: number
  target_promo_sentiment?: number
  competitor_organic_sentiment?: number
  competitor_promo_sentiment?: number
  target_spam_distribution?: SpamDistribution
  competitor_spam_distribution?: SpamDistribution
  post_ids_sample?: PostRef[]
  original_terms?: OriginalTerm[]
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
  organic_sentiment?: number
  promo_sentiment?: number
  top_pain?: string
  platform_distribution?: Record<string, number>
  spam_distribution?: SpamDistribution
  source_tasks?: SourceTask[]
  post_ids_sample?: PostRef[]
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
  subject_organic_mentions?: number
  subject_promo_mentions?: number
  industry_organic_mentions?: number
  industry_promo_mentions?: number
}

interface PlatformScissorsData {
  subject_total_mentions: number
  industry_total_mentions: number
  by_platform: PlatformScissorsItem[]
  subject_total_organic_mentions?: number
  subject_total_promo_mentions?: number
  industry_total_organic_mentions?: number
  industry_total_promo_mentions?: number
}

interface GapData {
  dimensions: SWOTItem[]
}

interface SliceFocusLayer {
  subject?: string
  targets?: string[]
  competitors?: string[]
  swot?: SWOTData | null
  product_line_health?: ProductLineHealthData | null
  platform_scissors?: PlatformScissorsData | null
  gap?: GapData | null
}

interface SliceLayers {
  landscape?: SliceLandscapeLayer
  intent?: SliceIntentLayer
  focus?: SliceFocusLayer | null
}

interface SliceReport {
  content?: string
}

interface SliceReports {
  landscape_report?: SliceReport | null
  topic_report?: SliceReport | null
  focus_report?: SliceReport | null
}

interface SliceFoundation {
  dedup_stats?: Record<string, unknown>
  aligned_entities?: SliceTopicOrEntity[]
  aligned_topics?: SliceTopicOrEntity[]
  drivers?: {
    min_cell_mentions?: number
    dimensions_top?: string[]
    entity_matrix?: Array<{
      entity: string
      dimensions: Record<string, { mentions: number; pos: number; neg: number; sentiment: number }>
    }>
  }
}

interface SliceResultData {
  meta?: {
    monitor_id: number
    generated_at: string
    subject?: string | null
    competitors?: string[]
    weights_used?: Record<string, number>
    scope?: Record<string, unknown>
  }
  foundation?: SliceFoundation
  layers?: SliceLayers
  reports?: SliceReports
  pipeline?: {
    stage1?: {
      status: 'completed'
      completed_at?: string
      entities_count?: number
      topics_count?: number
    }
    stage2?: {
      status: 'completed' | 'processing' | 'failed' | 'skipped'
      started_at?: string
      updated_at?: string
      generated_at?: string
      celery_task_id?: string
      llm?: { used?: boolean }
      steps?: Record<string, { status: 'pending' | 'processing' | 'completed' | 'failed'; llm_used?: boolean; job_id?: number }>
      jobs?: Record<string, number>
      category_alignment?: {
        used?: boolean
        category_map?: Record<string, string>
        topic_aspects_aligned?: SliceTopicAspectItem[]
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
    }
    stage3?: {
      status: 'pending' | 'processing' | 'completed' | 'failed'
      job_id?: number
      started_at?: string
      updated_at?: string
      generated_at?: string
      llm?: { used?: boolean }
      error?: string
    }
  }
}

interface MonitorSlice{
  id: number
  name: string | null
  monitor_id: number
  user_id: number
  included_task_ids: number[]
  result_data: SliceResultData
  created_at: string
  updated_at: string
}

// ==================== Data Loading ====================
const route = useRoute()
const monitorId = computed(() => Number(route.params.id))
const sliceId = computed(() => route.query.slice_id ? Number(route.query.slice_id) : null)

const { useApiData } = useApi()
const { data: slice, pending: sliceLoading, refresh: refreshSlice } = useApiData<MonitorSlice>(
  computed(() => sliceId.value ? `/social-media/analysis/monitors/${monitorId.value}/slices/${sliceId.value}` : ''),
  {
    key: computed(() => `monitor-slice-detail-${monitorId.value}-${sliceId.value}`),
    silent404: true,
    immediate: computed(() => Boolean(sliceId.value)),
    getCachedData: () => undefined,
  }
)

const handleRefresh = async () => {
  if (!sliceId.value) return
  await refreshSlice()
}

// ==================== 切片重命名 ====================
const { renameMonitorSlice } = useAnalysis()
const editingName = ref(false)
const nameInput = ref('')
const renameSaving = ref(false)

const startRename = () => {
  nameInput.value = slice.value?.name || ''
  editingName.value = true
}

const cancelRename = () => {
  editingName.value = false
}

const saveRename = async () => {
  const trimmed = nameInput.value.trim()
  if (!trimmed || !sliceId.value) return
  renameSaving.value = true
  try {
    await renameMonitorSlice(monitorId.value, sliceId.value, trimmed)
    editingName.value = false
    await refreshSlice()
  } catch {
    // apiRequest 已处理错误 toast
  } finally {
    renameSaving.value = false
  }
}

// ==================== View Models ====================
const sliceResult = computed<SliceResultData | null>(() => slice.value?.result_data || null)
const pipeline = computed(() => sliceResult.value?.pipeline || null)
const stage2 = computed(() => pipeline.value?.stage2 || null)
const stage3 = computed(() => pipeline.value?.stage3 || null)

const meta = computed(() => sliceResult.value?.meta || null)
const competitors = computed(() => (meta.value?.competitors || []))
const foundation = computed(() => sliceResult.value?.foundation || null)
const layers = computed(() => sliceResult.value?.layers || null)
const reports = computed(() => sliceResult.value?.reports || null)

const landscape = computed<SliceLandscapeLayer | null>(() => layers.value?.landscape || null)
const overview = computed<SliceOverviewData | null>(() => landscape.value?.overview || null)
const freshness = computed(() => landscape.value?.freshness || null)
const intent = computed(() => layers.value?.intent || null)
const focus = computed<SliceFocusLayer | null>(() => layers.value?.focus || null)
const topEntities = computed<SliceTopicOrEntity[]>(() => foundation.value?.aligned_entities || [])
const topTopics = computed<SliceTopicOrEntity[]>(() => foundation.value?.aligned_topics || [])

/** 切片是否含有 4D spam 数据（用于 PostListModal 推广/有机 tab 显示） */
const hasSliceSpamData = computed(() => topEntities.value.some(e => e.spam_distribution != null))

// ==================== Landscape Layer Data ====================
const sovRanking = computed(() => landscape.value?.sov_ranking || [])
const groupShare = computed(() => landscape.value?.group_share || [])
const platformDNA = computed(() => landscape.value?.platform_dna || [])
const platformDNAGrouped = computed(() => landscape.value?.platform_dna_grouped || [])
const industryQuadrant = computed(() => landscape.value?.industry_quadrant || [])

const selectedLandscapeEntity = ref<string | null>(null)
const handleSelectLandscapeEntity = (item: { name: string } | null) => {
  const name = (item?.name || '').toString().trim()
  if (!name) return
  selectedLandscapeEntity.value = selectedLandscapeEntity.value === name ? null : name
}

// ===== Overlay stacking fix =====
// 从侧边栏再打开 UModal 时，先关闭侧边栏再 nextTick 打开弹窗，避免 overlay z-index/portal 层级问题
const openEntitySamplePosts = async () => {
  const e = entityPanelEntity.value as { post_ids_sample?: PostRef[] } | null
  const refs = (e?.post_ids_sample || []) as PostRef[]
  entityPanelOpen.value = false
  await nextTick()
  openLandscapePostList({ name: entityPanelName.value, post_ids_sample: refs })
}

const openFocusSamplePosts = async () => {
  const dim = (focusPanelItem.value?.dimension || '').toString()
  const refs = (focusPanelItem.value?.post_ids_sample || []) as PostRef[]
  const t = focusPanelType.value || undefined
  focusPanelOpen.value = false
  await nextTick()
  openFocusPostList({ name: dim, post_ids_sample: refs }, t)
}

// ==================== Evidence Panels (统一：先证据，后样本) ====================
const entityPanelOpen = ref(false)
const entityPanelName = ref<string>('')
const entityPanelFallback = ref<{ name: string; role?: string; heat?: number; mentions?: number; sentiment?: number } | null>(null)

const focusPanelOpen = ref(false)
const focusPanelType = ref<'swot' | 'gap' | null>(null)
const focusPanelItem = ref<{
  dimension?: string
  target_sentiment?: number
  competitor_sentiment?: number
  target_mentions?: number
  competitor_mentions?: number
  delta?: number
  target_organic_sentiment?: number
  target_promo_sentiment?: number
  competitor_organic_sentiment?: number
  competitor_promo_sentiment?: number
  target_spam_distribution?: SpamDistribution
  competitor_spam_distribution?: SpamDistribution
  original_terms?: OriginalTerm[]
  post_ids_sample?: PostRef[]
} | null>(null)

// 证据面板（把“证据区”从主页面挪到侧边栏，主页面只保留摘要，减少占用空间）
const evidencePanelOpen = ref(false)

const entityByName = computed(() => {
  const m = new Map<string, SliceTopicOrEntity>()
  for (const e of topEntities.value || []) {
    const name = (e?.name || '').toString().trim()
    if (name) m.set(name, e)
  }
  return m
})

const entityPanelEntity = computed(() => {
  const name = (entityPanelName.value || '').toString().trim()
  if (!name) return null
  return entityByName.value.get(name) || entityPanelFallback.value
})

const openEntityPanel = (
  name: string,
  fallback?: { name: string; role?: string; heat?: number; mentions?: number; sentiment?: number } | null
) => {
  const nm = (name || '').toString().trim()
  if (!nm) return
  entityPanelName.value = nm
  entityPanelFallback.value = fallback || null
  entityPanelOpen.value = true
}

const openFocusDimensionPanel = (
  item: {
    dimension?: string
    target_sentiment?: number
    competitor_sentiment?: number
    target_mentions?: number
    competitor_mentions?: number
    delta?: number
    target_organic_sentiment?: number
    target_promo_sentiment?: number
    competitor_organic_sentiment?: number
    competitor_promo_sentiment?: number
    target_spam_distribution?: SpamDistribution
    competitor_spam_distribution?: SpamDistribution
    original_terms?: OriginalTerm[]
    post_ids_sample?: PostRef[]
  } | null,
  t: 'swot' | 'gap'
) => {
  focusPanelType.value = t
  focusPanelItem.value = item
  focusPanelOpen.value = true
}
const postListModalOpen = ref(false)
const postListModalTitle = ref('')
const postListModalGroups = ref<Array<{ taskId: number; postIds: number[]; label?: string }>>([])

const platformName = (code: string) => {
  // 官方 7 个平台（对齐 backend/src/social_media/monitors/init_data.py）
  const c = (code || '').toString().toLowerCase()
  const mp: Record<string, string> = {
    // 小红书
    xhs: '小红书',
    xiaohongshu: '小红书',
    // 抖音
    dy: '抖音',
    douyin: '抖音',
    // B站
    bili: 'B站',
    bilibili: 'B站',
    // 微博
    wb: '微博',
    weibo: '微博',
    // 快手
    ks: '快手',
    kuaishou: '快手',
    // 知乎
    zhihu: '知乎',
    // 贴吧
    tieba: '贴吧',
  }
  return mp[c] || code
}

const taskDiagById = computed(() => {
  const m = new Map<number, { platform?: string; keyword?: string }>()
  const list =
    meta.value && typeof meta.value === 'object'
      ? (meta.value as Record<string, unknown>)?.task_diagnostics
      : null
  if (Array.isArray(list)) {
    for (const r of list) {
      const tid = Number(r?.task_id)
      if (!Number.isFinite(tid) || tid <= 0) continue
      m.set(tid, {
        platform: (r?.platform || '').toString(),
        keyword: (r?.keyword || '').toString(),
      })
    }
  }
  return m
})

const decorateGroups = (groups: Array<{ taskId: number; postIds: number[] }>) => {
  return groups.map(g => {
    const diag = taskDiagById.value.get(g.taskId)
    const p = diag?.platform ? platformName(diag.platform) : ''
    const kw = (diag?.keyword || '').toString().trim()
    const parts = [`任务 #${g.taskId}`]
    if (p) parts.push(p)
    if (kw) parts.push(kw)
    return {
      ...g,
      label: `${parts.join(' · ')}（${g.postIds.length}条样本）`,
    }
  })
}

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
  const groups = decorateGroups(groupPostIdsByTask(item.post_ids_sample))
  if (!groups.length) {
    toast.add({
      title: '暂无可追溯原文',
      description: name ? `${name} 未提供原文样本` : '未提供原文样本',
      color: 'warning',
    })
    return
  }
  postListModalGroups.value = groups
  postListModalTitle.value = `${name || '实体'} 相关内容（样本）`
  postListModalOpen.value = true
}

const openTopicPostList = (item: { name?: string; post_ids_sample?: PostRef[] } | null, type?: string) => {
  if (!item) return
  const name = (item.name || '').toString().trim()
  const groups = decorateGroups(groupPostIdsByTask(item.post_ids_sample))
  if (!groups.length) {
    toast.add({
      title: '暂无可追溯原文',
      description: name ? `${name} 未提供原文样本` : '未提供原文样本',
      color: 'warning',
    })
    return
  }
  const typeLabel = type === 'pain' ? '痛点' : type === 'gain' ? '爽点' : type === 'controversy' ? '争议点' : type === 'unmet' ? '未被满足需求' : '话题'
  postListModalGroups.value = groups
  postListModalTitle.value = `${typeLabel} · ${name || '话题'} 相关内容（样本）`
  postListModalOpen.value = true
}

const openFocusPostList = (item: { name?: string; post_ids_sample?: PostRef[] } | null, type?: string) => {
  if (!item) return
  const name = (item.name || '').toString().trim()
  const groups = decorateGroups(groupPostIdsByTask(item.post_ids_sample))
  if (!groups.length) {
    toast.add({
      title: '暂无可追溯原文',
      description: name ? `${name} 未提供原文样本（当前为样本口径）` : '未提供原文样本（当前为样本口径）',
      color: 'warning',
    })
    return
  }
  const typeLabel = type === 'product-line' ? '产品线' : type === 'swot' ? 'SWOT' : type === 'gap' ? 'Gap' : '聚焦层'
  postListModalGroups.value = groups
  postListModalTitle.value = `${typeLabel} · ${name || '条目'} 相关内容（样本）`
  postListModalOpen.value = true
}

const handleSwotSelect = (
  item: {
    dimension?: string
    target_sentiment?: number
    competitor_sentiment?: number
    target_mentions?: number
    competitor_mentions?: number
    delta?: number
    target_organic_sentiment?: number
    target_promo_sentiment?: number
    competitor_organic_sentiment?: number
    competitor_promo_sentiment?: number
    target_spam_distribution?: SpamDistribution
    competitor_spam_distribution?: SpamDistribution
    original_terms?: OriginalTerm[]
    post_ids_sample?: PostRef[]
  } | null,
  _type: string
) => {
  // 统一：先看维度证据，再按需打开样本贴
  openFocusDimensionPanel(item, 'swot')
}

const handleGapSelect = (item: {
  dimension?: string
  target_sentiment?: number
  competitor_sentiment?: number
  target_mentions?: number
  competitor_mentions?: number
  delta?: number
  target_organic_sentiment?: number
  target_promo_sentiment?: number
  competitor_organic_sentiment?: number
  competitor_promo_sentiment?: number
  target_spam_distribution?: SpamDistribution
  competitor_spam_distribution?: SpamDistribution
  original_terms?: OriginalTerm[]
  post_ids_sample?: PostRef[]
} | null) => {
  openFocusDimensionPanel(item, 'gap')
}

const handleSOVSelect = (item: { name: string; role?: string; heat?: number; mentions?: number; sentiment?: number } | null) => {
  if (!item) return
  handleSelectLandscapeEntity(item)
  openEntityPanel(item.name, item)
}

const handleIndustryQuadrantSelect = (item: IndustryQuadrantPoint | null) => {
  if (!item) return
  handleSelectLandscapeEntity(item)
  // 统一：先看证据（原话/分布），需要时再点开样本贴
  openEntityPanel(item.name, item)
}

watch(sliceId, () => {
  selectedLandscapeEntity.value = null
  postListModalOpen.value = false
  postListModalGroups.value = []
  postListModalTitle.value = ''
  entityPanelOpen.value = false
  entityPanelName.value = ''
  entityPanelFallback.value = null
  focusPanelOpen.value = false
  focusPanelType.value = null
  focusPanelItem.value = null
})

// ==================== Topic Layer Data ====================
const topicRadar = computed(() => intent.value?.topic_radar || null)
const unmetNeeds = computed(() => intent.value?.unmet_needs || [])

type TopicAspectSortKey = 'heat' | 'sentiment' | 'mention_count'
const topicAspectSort = ref<TopicAspectSortKey>('heat')
const topicAspectSortDir = ref<'desc' | 'asc'>('desc')

const toggleTopicAspectSort = (key: TopicAspectSortKey) => {
  if (topicAspectSort.value === key) {
    topicAspectSortDir.value = topicAspectSortDir.value === 'desc' ? 'asc' : 'desc'
  } else {
    topicAspectSort.value = key
    topicAspectSortDir.value = 'desc'
  }
}

const topicAspects = computed(() => {
  const raw = intent.value?.topic_aspects || []
  return raw.slice().sort((a, b) => {
    let va: number, vb: number
    if (topicAspectSort.value === 'sentiment') {
      va = a.sentiment ?? 0
      vb = b.sentiment ?? 0
    } else if (topicAspectSort.value === 'mention_count') {
      va = a.mention_count ?? 0
      vb = b.mention_count ?? 0
    } else {
      va = a.heat ?? 0
      vb = b.heat ?? 0
    }
    return topicAspectSortDir.value === 'desc' ? vb - va : va - vb
  })
})

// ==================== Drivers / Entity Matrix ====================
const driversData = computed(() => foundation.value?.drivers || null)
const entityMatrix = computed(() => driversData.value?.entity_matrix || [])
const matrixDimensions = computed(() => driversData.value?.dimensions_top || [])

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

// UI states: collapse execution panel, and switch between 3 reports
const execPanelOpen = ref(false)
watch(
  [isPipelineRunning, isReportsReady],
  ([running, reportsReady]) => {
    // 运行中默认展开；完成后默认折叠（但用户可手动再展开）
    if (running) execPanelOpen.value = true
    else if (reportsReady) execPanelOpen.value = false
  },
  { immediate: true }
)

type ReportKey = 'landscape' | 'topic' | 'focus'
const activeReport = ref<ReportKey>('landscape')
watch(
  [showFocusReport, isReportsReady],
  ([canShowFocus]) => {
    if (!canShowFocus && activeReport.value === 'focus') activeReport.value = 'landscape'
  },
  { immediate: true }
)

const activeReportTitle = computed(() => {
  if (activeReport.value === 'landscape') return '行业格局报告'
  if (activeReport.value === 'topic') return '话题洞察报告'
  return '战略诊断报告'
})
const activeReportContent = computed(() => {
  if (activeReport.value === 'landscape') return reportLandscape.value
  if (activeReport.value === 'topic') return reportTopic.value
  return reportFocus.value
})
const activeReportEvidence = computed(() => {
  if (activeReport.value === 'landscape') return reportEvidenceLandscape.value
  if (activeReport.value === 'topic') return reportEvidenceTopic.value
  return reportEvidenceFocus.value
})

// ==================== 自动轮询机制（优化：只检查状态，避免页面跳动）====================
let pollTimer: ReturnType<typeof setInterval> | null = null
const lastPolledStatus = ref<{ stage2?: string; stage3?: string; }>({ })

const { apiRequest, apiDownload, showSuccess, showError } = useApi()

// 轮询时只检查状态，不触发完整数据刷新
const pollStatus = async () => {
  if (!sliceId.value) return

  try {
    // 使用 apiRequest 获取最新数据（不会触发 useApiData 的响应式更新）
    const freshData = await apiRequest<MonitorSlice>(
      `/social-media/analysis/monitors/${monitorId.value}/slices/${sliceId.value}`
    )
    if (!freshData) return

    const newStage2Status = freshData.result_data?.pipeline?.stage2?.status
    const newStage3Status = freshData.result_data?.pipeline?.stage3?.status
    const oldStage2Status = lastPolledStatus.value.stage2
    const oldStage3Status = lastPolledStatus.value.stage3

    // 更新状态缓存
    lastPolledStatus.value = { stage2: newStage2Status, stage3: newStage3Status }

    // 只有当状态发生变化时，才刷新完整数据（触发图表更新）
    const statusChanged = newStage2Status !== oldStage2Status || newStage3Status !== oldStage3Status
    const isCompleted = newStage3Status === 'completed' || newStage3Status === 'failed'

    if (statusChanged || isCompleted) {
      await refreshSlice()
    }
  } catch (e) {
    // 静默失败，避免轮询错误打断用户操作
    console.warn('[Slice Poll] Status check failed:', e)
  }
}

const startPolling = () => {
  if (pollTimer) return
  // 初始化状态缓存
  lastPolledStatus.value = {
    stage2: stage2.value?.status ?? undefined,
    stage3: stage3.value?.status ?? undefined,
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
      description: '项目切片分析已完成',
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

// 报告原文不做“展开/收起”，由 UI 内部滚动承载长文本

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

// ==================== 导出 Word ====================
const exporting = ref(false)
const hasReports = computed(() => Boolean(reports.value?.landscape_report || reports.value?.topic_report))

const handleExport = async () => {
  if (!sliceId.value || exporting.value) return
  exporting.value = true
  try {
    await apiDownload(
      `/social-media/analysis/monitors/${monitorId.value}/slices/${sliceId.value}/export`,
    )
    showSuccess('报告已导出')
  } catch {
    showError('导出失败，请稍后重试')
  } finally {
    exporting.value = false
  }
}
</script>

<template>
  <div class="space-y-6">
    <!-- Page Header -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <UButton variant="ghost" icon="i-heroicons-arrow-left" :to="`/social-media/monitors/${monitorId}`" />
        <div>
          <ClientOnly>
            <div v-if="editingName" class="flex items-center gap-2">
              <UInput
                v-model="nameInput"
                size="lg"
                autofocus
                class="w-64"
                @keyup.enter="saveRename"
                @keyup.escape="cancelRename"
              />
              <UButton
                size="xs"
                icon="i-heroicons-check"
                :loading="renameSaving"
                @click="saveRename"
              />
              <UButton
                size="xs"
                variant="ghost"
                icon="i-heroicons-x-mark"
                :disabled="renameSaving"
                @click="cancelRename"
              />
            </div>
            <div v-else class="flex items-center gap-2 group">
              <h1 class="text-xl font-semibold text-gray-900 dark:text-white">
                {{ slice?.name || `切片 ${sliceId}` }}
              </h1>
              <UButton
                size="xs"
                variant="ghost"
                icon="i-heroicons-pencil-square"
                class="opacity-0 group-hover:opacity-100 transition-opacity"
                @click="startRename"
              />
            </div>
            <template #fallback>
              <h1 class="text-xl font-semibold text-gray-900 dark:text-white">
                {{ `切片 ${sliceId}` }}
              </h1>
            </template>
          </ClientOnly>
          <p class="text-sm text-gray-500 dark:text-gray-400">
            项目级合并分析切片
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
        <UButton icon="i-heroicons-arrow-path" variant="ghost" :loading="sliceLoading" @click="handleRefresh">
          刷新
        </UButton>
      </ClientOnly>
    </div>

    <ClientOnly>
      <template #fallback>
        <div class="text-center py-12 text-gray-400">加载中...</div>
      </template>

      <div v-if="sliceLoading" class="text-center py-12 text-gray-400">加载中...</div>
      <div v-else-if="!sliceId" class="text-center py-12 text-gray-400">未指定切片 ID，请从项目详情页选择切片查看</div>
      <div v-else-if="!slice" class="text-center py-12 text-gray-400">切片不存在或已删除</div>

      <div v-else class="space-y-6">
        <!-- 分析报告（生成进度） -->
        <section class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
          <div class="flex items-center justify-between gap-4 mb-2">
            <h2 class="text-lg font-medium text-gray-900 dark:text-white">🧾 分析报告</h2>
            <div class="text-xs text-gray-500 dark:text-gray-400">
              <span class="font-mono">slice_id={{ slice.id }}</span>
            </div>
          </div>
          <!-- summary row -->
          <div class="flex flex-wrap items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
            <UBadge :color="getStatusColor((stage2?.steps as any)?.entity_normalization?.status)" variant="subtle" size="xs">
              实体归一：{{ getStatusLabel((stage2?.steps as any)?.entity_normalization?.status) }}
            </UBadge>
            <UBadge :color="getStatusColor((stage2?.steps as any)?.opinion_normalization?.status)" variant="subtle" size="xs">
              观点归一：{{ getStatusLabel((stage2?.steps as any)?.opinion_normalization?.status) }}
            </UBadge>
            <UBadge :color="getStatusColor((stage2?.steps as any)?.derived_analysis?.status)" variant="subtle" size="xs">
              程序化：{{ getStatusLabel((stage2?.steps as any)?.derived_analysis?.status) }}
            </UBadge>
            <UBadge :color="getStatusColor(stage3?.status)" variant="subtle" size="xs">
              报告：{{ getStatusLabel(stage3?.status) }}
            </UBadge>
            <span class="ml-auto">
              <UButton
                size="xs"
                variant="ghost"
                @click="execPanelOpen = !execPanelOpen"
              >
                {{ execPanelOpen ? '收起执行记录' : '展开执行记录' }}
              </UButton>
            </span>
          </div>

          <div v-if="execPanelOpen" class="mt-3 text-sm text-gray-700 dark:text-gray-300">
            <div class="text-xs text-gray-500 dark:text-gray-400">
              执行记录用于排查与审计：完成后可折叠，不影响下方阅读。
            </div>
            <div v-if="stage2?.steps" class="mt-3 grid grid-cols-1 md:grid-cols-2 gap-2">
              <!-- Stage1：同步数据聚合 -->
              <div v-if="pipeline?.stage1" class="p-3 rounded bg-gray-50 dark:bg-gray-800 flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <span class="font-medium text-gray-900 dark:text-white">数据聚合</span>
                  <span class="text-xs text-gray-400">{{ pipeline.stage1.entities_count }} 实体 / {{ pipeline.stage1.topics_count }} 话题</span>
                </div>
                <UBadge color="success" variant="solid" size="xs">完成</UBadge>
              </div>
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
                  <span v-if="stage3?.job_id" class="text-xs text-gray-400 font-mono">
                    job={{ stage3.job_id }}
                  </span>
                </div>
                <UBadge :color="getStatusColor(stage3?.status)" variant="solid" size="xs">
                  {{ getStatusLabel(stage3?.status) }}
                </UBadge>
              </div>
            </div>

            <!-- alias_normalization 统计 -->
            <div v-if="stage2?.alias_normalization" class="mt-3 p-3 rounded bg-gray-50 dark:bg-gray-800 space-y-2 text-xs">
              <div class="font-medium text-gray-700 dark:text-gray-300">别名归一化统计</div>
              <div class="grid grid-cols-2 gap-3">
                <div v-if="stage2.alias_normalization.entities">
                  <div class="text-gray-500 dark:text-gray-400 mb-1">实体</div>
                  <div class="flex items-center gap-2">
                    <UBadge :color="stage2.alias_normalization.entities.used ? 'success' : 'neutral'" variant="subtle" size="xs">
                      {{ stage2.alias_normalization.entities.used ? 'LLM 已用' : '未用 LLM' }}
                    </UBadge>
                    <span class="font-mono text-gray-600 dark:text-gray-400">
                      {{ stage2.alias_normalization.entities.before_count ?? '?' }} → {{ stage2.alias_normalization.entities.after_count ?? '?' }}
                    </span>
                  </div>
                  <div
                    v-if="stage2.alias_normalization.entities.entity_mapping && Object.keys(stage2.alias_normalization.entities.entity_mapping).length"
                    class="mt-1 text-gray-500 dark:text-gray-500 truncate"
                    :title="Object.entries(stage2.alias_normalization.entities.entity_mapping).slice(0, 3).map(([k, v]) => `${k} → ${v}`).join('；')"
                  >
                    样例：{{ Object.entries(stage2.alias_normalization.entities.entity_mapping).slice(0, 2).map(([k, v]) => `${k}→${v}`).join('，') }}
                  </div>
                </div>
                <div v-if="stage2.alias_normalization.topics">
                  <div class="text-gray-500 dark:text-gray-400 mb-1">话题</div>
                  <div class="flex items-center gap-2">
                    <UBadge :color="stage2.alias_normalization.topics.used ? 'success' : 'neutral'" variant="subtle" size="xs">
                      {{ stage2.alias_normalization.topics.used ? 'LLM 已用' : '未用 LLM' }}
                    </UBadge>
                    <span class="font-mono text-gray-600 dark:text-gray-400">
                      {{ stage2.alias_normalization.topics.before_count ?? '?' }} → {{ stage2.alias_normalization.topics.after_count ?? '?' }}
                    </span>
                  </div>
                  <div
                    v-if="stage2.alias_normalization.topics.topic_mapping_by_category"
                    class="mt-1 text-gray-500 dark:text-gray-500"
                  >
                    分类数：{{ Object.keys(stage2.alias_normalization.topics.topic_mapping_by_category).length }}
                  </div>
                </div>
              </div>
            </div>

            <!-- category_alignment 统计 -->
            <div v-if="stage2?.category_alignment" class="mt-2 p-3 rounded bg-gray-50 dark:bg-gray-800 space-y-1 text-xs">
              <div class="flex items-center gap-2">
                <span class="font-medium text-gray-700 dark:text-gray-300">话题类别对齐</span>
                <UBadge :color="stage2.category_alignment.used ? 'success' : 'neutral'" variant="subtle" size="xs">
                  {{ stage2.category_alignment.used ? 'LLM 已用' : '未用 LLM' }}
                </UBadge>
                <span v-if="stage2.category_alignment.category_map" class="text-gray-500 dark:text-gray-400 font-mono">
                  映射 {{ Object.keys(stage2.category_alignment.category_map).length }} 个类别
                </span>
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
            <h2 class="text-lg font-medium text-gray-900 dark:text-white">🧾 AI 报告</h2>
            <div class="text-xs text-gray-500 dark:text-gray-400">
              <span class="font-mono">{{ stage3?.status || 'pending' }}</span>
            </div>
          </div>

          <div v-if="!isReportsReady" class="text-xs text-gray-500 dark:text-gray-400">
            报告生成中（或失败）。完成后将展示：行业格局 / 话题洞察 /（可选）战略诊断 的原声内容。
            <span v-if="stage3?.status === 'failed' && stage3?.error" class="ml-2">错误：{{ stage3.error }}</span>
          </div>

          <div v-else class="space-y-3">
            <!-- unified toolbar: tabs + title + actions -->
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div class="flex flex-wrap items-center gap-2">
                <UButton size="xs" :variant="activeReport === 'landscape' ? 'solid' : 'outline'" @click="activeReport = 'landscape'">
                  行业格局
                </UButton>
                <UButton size="xs" :variant="activeReport === 'topic' ? 'solid' : 'outline'" @click="activeReport = 'topic'">
                  话题洞察
                </UButton>
                <UButton
                  v-if="showFocusReport"
                  size="xs"
                  :variant="activeReport === 'focus' ? 'solid' : 'outline'"
                  @click="activeReport = 'focus'"
                >
                  战略诊断
                </UButton>
              </div>

              <div class="flex items-center gap-2">
                <span class="text-xs text-gray-500 dark:text-gray-400 hidden sm:inline">
                  {{ activeReportTitle }}
                </span>
                <UButton size="xs" variant="ghost" icon="i-heroicons-clipboard" :disabled="!activeReportContent" @click="copyText(activeReportContent)">
                  复制
                </UButton>
                <UButton size="xs" variant="ghost" icon="i-heroicons-arrow-down-tray" :loading="exporting" :disabled="!hasReports" @click="handleExport">
                  导出 Word
                </UButton>
                <UButton
                  v-if="activeReportContent && activeReportEvidence.length"
                  size="xs"
                  variant="ghost"
                  @click="toggleExpand(`report-${activeReport}-evidence`)"
                >
                  {{ isExpanded(`report-${activeReport}-evidence`) ? '收起证据' : '查看证据' }}
                </UButton>
              </div>
            </div>

            <div class="p-3 rounded bg-gray-50 dark:bg-gray-800">

              <div v-if="activeReport === 'focus' && !reportFocus" class="text-xs text-gray-500 dark:text-gray-400">
                战略诊断报告为空：可能未配置主体 subject，或输出未满足“营销/产品/公关”三段式硬约束。
              </div>
              <div v-else class="text-sm max-h-[70vh] overflow-y-auto pr-2">
                <MarkdownRenderer v-if="activeReportContent" :content="activeReportContent" />
                <span v-else class="text-gray-500 dark:text-gray-400">-</span>
              </div>

              <div v-if="activeReportEvidence.length && isExpanded(`report-${activeReport}-evidence`)" class="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
                <div class="text-xs text-gray-500 dark:text-gray-400 mb-2">证据原话（节选）</div>
                <div class="space-y-1 text-xs text-gray-700 dark:text-gray-300">
                  <div v-for="(line, idx) in activeReportEvidence" :key="`re-${activeReport}-${idx}`" class="truncate" :title="line">
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
              <span class="font-mono">slice_id={{ slice.id }}</span>
              <span class="mx-2">·</span>
              <span>任务数 {{ slice.included_task_ids?.length || 0 }}</span>
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
                  :class="(overview?.global_nsr || 0) >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'"
                >
                  {{ typeof overview?.global_nsr === 'number' ? overview.global_nsr.toFixed(2) : '-' }}
                </span>
              </div>
              <div class="text-xs text-gray-400 mt-1">
                NSR 指数（按任务量加权，-1 ~ +1）
              </div>
              <!-- 有机/推广 NSR 分层 -->
              <div
                v-if="overview?.organic_nsr != null || overview?.promo_nsr != null"
                class="flex items-center gap-3 mt-1 text-[11px]"
              >
                <span
                  v-if="overview?.organic_nsr != null"
                  class="flex items-center gap-1"
                  title="有机内容 NSR（低推广）"
                >
                  <span class="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                  <span class="text-gray-500 dark:text-gray-400">有机</span>
                  <span
                    class="font-mono"
                    :class="(overview.organic_nsr ?? 0) >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'"
                  >{{ (overview.organic_nsr ?? 0) >= 0 ? '+' : '' }}{{ Number(overview.organic_nsr).toFixed(2) }}</span>
                </span>
                <span
                  v-if="overview?.promo_nsr != null"
                  class="flex items-center gap-1"
                  title="推广内容 NSR（高推广）"
                >
                  <span class="w-1.5 h-1.5 rounded-full bg-amber-500" />
                  <span class="text-gray-500 dark:text-gray-400">推广</span>
                  <span
                    class="font-mono"
                    :class="(overview.promo_nsr ?? 0) >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'"
                  >{{ (overview.promo_nsr ?? 0) >= 0 ? '+' : '' }}{{ Number(overview.promo_nsr).toFixed(2) }}</span>
                </span>
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
              :group-data="groupShare"
              :max-items="15"
              :selected="selectedLandscapeEntity"
              :global-organic-heat="overview?.total_organic_heat"
              :global-promo-heat="overview?.total_promo_heat"
              @select="handleSOVSelect"
            />
            <IndustryQuadrantChart
              :data="industryQuadrant"
              :group-data="groupShare"
              :selected="selectedLandscapeEntity"
              @select="handleIndustryQuadrantSelect"
            />
          </div>

          <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <GroupShareTable :data="groupShare" :entities="topEntities" :max-items="10" />
            <PlatformDNAChart :data="platformDNA" :group-data="platformDNAGrouped" :max-items="10" />
          </div>

          <!-- 维度情感矩阵（entity × dimension 热力表：来自 stage2.drivers.entity_matrix） -->
          <div
            v-if="entityMatrix.length && matrixDimensions.length"
            class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900"
          >
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">维度情感矩阵</h3>
            <div class="overflow-x-auto">
              <table class="text-xs w-full">
                <thead>
                  <tr class="text-left border-b border-gray-100 dark:border-gray-800">
                    <th class="py-2 pr-3 font-medium text-gray-500 dark:text-gray-400 whitespace-nowrap sticky left-0 bg-white dark:bg-gray-900 align-top">实体</th>
                    <th
                      v-for="dim in matrixDimensions.slice(0, 8)"
                      :key="dim"
                      class="py-2 px-2 font-medium text-gray-500 dark:text-gray-400 text-center align-top max-w-[80px]"
                    >
                      {{ dim }}
                    </th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-50 dark:divide-gray-800/50">
                  <tr
                    v-for="row in entityMatrix.slice(0, 10)"
                    :key="row.entity"
                    class="hover:bg-gray-50 dark:hover:bg-gray-800/30 transition-colors"
                  >
                    <td class="py-1.5 pr-3 font-medium text-gray-900 dark:text-white whitespace-nowrap sticky left-0 bg-white dark:bg-gray-900 group-hover:bg-gray-50">{{ row.entity }}</td>
                    <td
                      v-for="dim in matrixDimensions.slice(0, 8)"
                      :key="dim"
                      class="py-1.5 px-1 text-center"
                    >
                      <template v-if="(row.dimensions as Record<string, { mentions: number; sentiment: number; pos: number; neg: number }>)[dim]">
                        <span
                          class="inline-block px-1 py-0.5 rounded text-[10px] font-mono"
                          :class="(row.dimensions as any)[dim].sentiment >= 0.1
                            ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
                            : (row.dimensions as any)[dim].sentiment <= -0.1
                              ? 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-400'
                              : 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'"
                          :title="`提及 ${(row.dimensions as any)[dim].mentions}，正 ${(row.dimensions as any)[dim].pos}，负 ${(row.dimensions as any)[dim].neg}`"
                        >
                          {{ (row.dimensions as any)[dim].sentiment >= 0 ? '+' : '' }}{{ Number((row.dimensions as any)[dim].sentiment).toFixed(1) }}
                        </span>
                      </template>
                      <span v-else class="text-gray-300 dark:text-gray-700">—</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
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

          <!-- 话题分类概览（topic_aspects：按分类聚合的热度/情感/提及） -->
          <div v-if="topicAspects.length" class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">话题分类概览</h3>
            <div class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead>
                  <tr class="text-left text-xs text-gray-500 dark:text-gray-400 border-b border-gray-100 dark:border-gray-800">
                    <th class="py-2 pr-4 font-medium">分类</th>
                    <th
                      class="py-2 pr-4 font-medium text-right cursor-pointer select-none hover:text-gray-700 dark:hover:text-gray-200"
                      @click="toggleTopicAspectSort('heat')"
                    >
                      热度{{ topicAspectSort === 'heat' ? (topicAspectSortDir === 'desc' ? ' ↓' : ' ↑') : '' }}
                    </th>
                    <th
                      class="py-2 pr-4 font-medium text-right cursor-pointer select-none hover:text-gray-700 dark:hover:text-gray-200"
                      @click="toggleTopicAspectSort('sentiment')"
                    >
                      情感{{ topicAspectSort === 'sentiment' ? (topicAspectSortDir === 'desc' ? ' ↓' : ' ↑') : '' }}
                    </th>
                    <th
                      class="py-2 pr-4 font-medium text-right cursor-pointer select-none hover:text-gray-700 dark:hover:text-gray-200"
                      @click="toggleTopicAspectSort('mention_count')"
                    >
                      提及{{ topicAspectSort === 'mention_count' ? (topicAspectSortDir === 'desc' ? ' ↓' : ' ↑') : '' }}
                    </th>
                    <th class="py-2 font-medium">代表话题</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-50 dark:divide-gray-800/50">
                  <tr
                    v-for="aspect in topicAspects.slice(0, 15)"
                    :key="aspect.category"
                    class="hover:bg-gray-50 dark:hover:bg-gray-800/30 transition-colors"
                  >
                    <td class="py-2 pr-4 font-medium text-gray-900 dark:text-white whitespace-nowrap">{{ aspect.category }}</td>
                    <td class="py-2 pr-4 text-right whitespace-nowrap">
                      <div class="flex items-center justify-end gap-2">
                        <span class="font-mono text-gray-700 dark:text-gray-300">{{ formatCompactNumber(aspect.heat) }}</span>
                        <div
                          v-if="(aspect.organic_heat ?? 0) + (aspect.promo_heat ?? 0) > 0"
                          class="flex h-1.5 w-10 rounded-full overflow-hidden"
                          :title="`有机 ${formatCompactNumber(aspect.organic_heat ?? 0)} · 推广 ${formatCompactNumber(aspect.promo_heat ?? 0)}`"
                        >
                          <div class="h-full bg-amber-400" :style="{ flex: aspect.promo_heat ?? 0 }" />
                          <div class="h-full bg-emerald-500" :style="{ flex: aspect.organic_heat ?? 0 }" />
                        </div>
                      </div>
                    </td>
                    <td
                      class="py-2 pr-4 text-right font-mono"
                      :class="aspect.sentiment >= 0.1 ? 'text-emerald-600 dark:text-emerald-400' : aspect.sentiment <= -0.1 ? 'text-rose-600 dark:text-rose-400' : 'text-gray-500 dark:text-gray-400'"
                    >
                      {{ aspect.sentiment >= 0 ? '+' : '' }}{{ aspect.sentiment.toFixed(2) }}
                    </td>
                    <td class="py-2 pr-4 text-right font-mono text-gray-500 dark:text-gray-400">
                      {{ typeof aspect.mention_count === 'number' ? aspect.mention_count : '-' }}
                    </td>
                    <td class="py-2">
                      <div class="flex flex-wrap gap-1">
                        <span
                          v-for="kw in (aspect.representative_topics || []).slice(0, 4)"
                          :key="kw"
                          class="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400"
                        >
                          {{ kw }}
                        </span>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
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
            <ProductLineHealthTable
              :data="productLineHealth"
              @select="(item) => openEntityPanel(item.name, { name: item.name, heat: item.heat, mentions: item.mentions, sentiment: item.sentiment })"
            />
            <PlatformScissorsChart :data="platformScissors" :subject="subject" />
          </div>

          <GapAnalysisChart :data="gapData" :subject="subject" @select="handleGapSelect" />
        </section>

        <!-- 证据（主页面只展示摘要，完整列表放进证据侧边栏，避免占用大量页面空间） -->
        <section class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 space-y-3">
          <div class="flex items-center justify-between gap-3">
            <div>
              <h2 class="text-lg font-medium text-gray-900 dark:text-white">🧾 证据（摘要）</h2>
              <p class="text-xs text-gray-500 dark:text-gray-400 mt-1">
                默认只展示精选原话用于快速核验；需要完整 Top 列表与追溯时再打开证据面板。
              </p>
            </div>
            <UButton
              size="xs"
              color="neutral"
              variant="outline"
              :disabled="!topTopics.length && !topEntities.length"
              :label="`打开证据面板（观点${topTopics.length} / 实体${topEntities.length}）`"
              @click="evidencePanelOpen = true"
            />
          </div>

          <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div class="p-3 rounded bg-gray-50 dark:bg-gray-800">
              <div class="text-sm font-medium text-gray-900 dark:text-white">话题证据原话</div>
              <div class="mt-2 space-y-1 text-xs text-gray-700 dark:text-gray-300">
                <div v-for="(line, idx) in reportEvidenceTopic.slice(0, 6)" :key="`ev-topic-${idx}`" class="line-clamp-2">
                  {{ line }}
                </div>
                <div v-if="!reportEvidenceTopic.length" class="text-gray-400">暂无原话</div>
              </div>
            </div>
            <div class="p-3 rounded bg-gray-50 dark:bg-gray-800">
              <div class="text-sm font-medium text-gray-900 dark:text-white">实体证据原话</div>
              <div class="mt-2 space-y-1 text-xs text-gray-700 dark:text-gray-300">
                <div v-for="(line, idx) in reportEvidenceLandscape.slice(0, 6)" :key="`ev-entity-${idx}`" class="line-clamp-2">
                  {{ line }}
                </div>
                <div v-if="!reportEvidenceLandscape.length" class="text-gray-400">暂无原话</div>
              </div>
            </div>
          </div>
        </section>

        <PostListModal
          v-if="postListModalGroups.length"
          v-model:open="postListModalOpen"
          :groups="postListModalGroups"
          :title="postListModalTitle"
          :has-spam-data="hasSliceSpamData"
        />

        <!-- 证据面板（完整 Top 列表） -->
        <USlideover v-model:open="evidencePanelOpen">
          <template #title>
            <div class="flex items-center gap-2">
              <span class="text-gray-900 dark:text-white font-medium">证据面板</span>
              <UBadge color="neutral" variant="subtle" size="xs">
                观点 {{ topTopics.length }}
              </UBadge>
              <UBadge color="neutral" variant="subtle" size="xs">
                实体 {{ topEntities.length }}
              </UBadge>
            </div>
          </template>
          <template #description>
            <span class="sr-only">查看 Top 观点与 Top 实体的可追溯证据</span>
          </template>
          <template #body>
            <div class="space-y-6">
              <div class="p-3 rounded bg-gray-50 dark:bg-gray-800">
                <div class="flex items-center justify-between gap-2 mb-2">
                  <div class="text-sm font-medium text-gray-900 dark:text-white">Top 观点（可追溯）</div>
                  <div class="text-xs text-gray-500 dark:text-gray-400">点击“查看样本贴”可按需下钻</div>
                </div>
                <div v-if="topTopics.length" class="space-y-2">
                  <div v-for="(t, idx) in topTopics.slice(0, 30)" :key="`topic-${idx}`" class="p-3 rounded bg-white/60 dark:bg-gray-900/30">
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
                        <SpamRatioBar v-if="t.spam_distribution" :spam-distribution="t.spam_distribution" class="mt-1" />
                        <div v-if="t.source_tasks?.length" class="text-xs text-gray-500 dark:text-gray-400 mt-1">
                          来源任务：{{ t.source_tasks.slice(0, 4).map(x => `#${x.task_id}:${x.mentions}`).join('，') }}
                        </div>

                        <div class="mt-2 flex items-center gap-2">
                          <UButton
                            size="xs"
                            color="neutral"
                            variant="outline"
                            :disabled="!t.post_ids_sample?.length"
                            :label="t.post_ids_sample?.length ? `查看样本贴（${t.post_ids_sample.length}）` : '暂无样本贴'"
                            @click="openTopicPostList({ name: t.name, post_ids_sample: t.post_ids_sample || [] }, 'topic')"
                          />
                          <button
                            v-if="t.original_terms?.length"
                            class="text-xs text-primary-600 dark:text-primary-400 hover:underline"
                            @click="toggleExpand(`topic-${idx}`)"
                          >
                            {{ isExpanded(`topic-${idx}`) ? '收起' : '展开' }} 原话（{{ t.original_terms.length }}）
                          </button>
                        </div>

                        <div v-if="t.original_terms?.length && isExpanded(`topic-${idx}`)" class="mt-2 pl-3 border-l-2 border-gray-200 dark:border-gray-700">
                          <div v-for="(term, tIdx) in t.original_terms.slice(0, 15)" :key="tIdx" class="text-xs text-gray-600 dark:text-gray-400 py-0.5">
                            • {{ term.text }} <span class="text-gray-400">({{ term.count }})</span>
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
                <div class="flex items-center justify-between gap-2 mb-2">
                  <div class="text-sm font-medium text-gray-900 dark:text-white">Top 实体（可追溯）</div>
                  <div class="text-xs text-gray-500 dark:text-gray-400">点击实体名可打开实体证据侧边栏</div>
                </div>
                <div v-if="topEntities.length" class="space-y-2">
                  <div v-for="(e, idx) in topEntities.slice(0, 30)" :key="`entity-${idx}`" class="p-3 rounded bg-white/60 dark:bg-gray-900/30">
                    <div class="flex items-start justify-between gap-3">
                      <div class="min-w-0 flex-1">
                        <button class="text-left" @click="openEntityPanel(e.name)">
                          <div class="flex items-center gap-2 flex-wrap">
                            <span class="text-gray-900 dark:text-white font-medium">{{ e.name }}</span>
                            <UBadge v-if="e.role" color="neutral" variant="subtle" size="xs">{{ e.role }}</UBadge>
                            <UBadge v-if="e.type" color="info" variant="subtle" size="xs">{{ e.type }}</UBadge>
                          </div>
                        </button>
                        <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">平台：{{ formatDist(e.platform_distribution) }}</div>
                        <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">关键词：{{ formatDist(e.keyword_distribution) }}</div>
                        <SpamRatioBar v-if="e.spam_distribution" :spam-distribution="e.spam_distribution" class="mt-1" />
                        <div v-if="e.source_tasks?.length" class="text-xs text-gray-500 dark:text-gray-400 mt-1">
                          来源任务：{{ e.source_tasks.slice(0, 4).map(x => `#${x.task_id}:${x.mentions}`).join('，') }}
                        </div>

                        <div class="mt-2 flex items-center gap-2">
                          <UButton
                            size="xs"
                            color="neutral"
                            variant="outline"
                            :disabled="!e.post_ids_sample?.length"
                            :label="e.post_ids_sample?.length ? `查看样本贴（${e.post_ids_sample.length}）` : '暂无样本贴'"
                            @click="openLandscapePostList({ name: e.name, post_ids_sample: e.post_ids_sample || [] })"
                          />
                          <button
                            v-if="e.original_terms?.length"
                            class="text-xs text-primary-600 dark:text-primary-400 hover:underline"
                            @click="toggleExpand(`entity-${idx}`)"
                          >
                            {{ isExpanded(`entity-${idx}`) ? '收起' : '展开' }} 原话（{{ e.original_terms.length }}）
                          </button>
                        </div>

                        <div v-if="e.original_terms?.length && isExpanded(`entity-${idx}`)" class="mt-2 pl-3 border-l-2 border-gray-200 dark:border-gray-700">
                          <div v-for="(term, tIdx) in e.original_terms.slice(0, 15)" :key="tIdx" class="text-xs text-gray-600 dark:text-gray-400 py-0.5">
                            • {{ term.text }} <span class="text-gray-400">({{ term.count }})</span>
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
          </template>
        </USlideover>

        <!-- 实体证据侧边栏（行业象限/大盘实体统一入口：先证据，后样本） -->
        <USlideover v-model:open="entityPanelOpen">
          <template #title>
            <div class="flex items-center gap-2 min-w-0">
              <span class="text-gray-900 dark:text-white font-medium truncate">{{ entityPanelName }}</span>
              <UBadge v-if="(entityPanelEntity as any)?.role" color="neutral" variant="subtle" size="xs">
                {{ (entityPanelEntity as any)?.role }}
              </UBadge>
              <UBadge v-if="(entityPanelEntity as any)?.type" color="info" variant="subtle" size="xs">
                {{ (entityPanelEntity as any)?.type }}
              </UBadge>
              <UBadge v-if="(entityPanelEntity as any)?.parent" color="neutral" variant="subtle" size="xs">
                {{ (entityPanelEntity as any)?.parent }}
              </UBadge>
            </div>
          </template>

          <template #description>
            <span class="sr-only">
              查看实体证据与样本贴入口
            </span>
          </template>

          <template #body>
            <div v-if="entityPanelEntity" class="space-y-4">
              <div class="grid grid-cols-3 gap-3">
                <div class="p-3 rounded-lg bg-gray-50 dark:bg-gray-800">
                  <div class="text-xs text-gray-500 dark:text-gray-400">热度</div>
                  <div class="text-lg font-mono font-semibold text-gray-900 dark:text-white mt-1">
                    {{ formatCompactNumber(Number((entityPanelEntity as any).heat || 0)) }}
                  </div>
                </div>
                <div class="p-3 rounded-lg bg-gray-50 dark:bg-gray-800">
                  <div class="text-xs text-gray-500 dark:text-gray-400">提及</div>
                  <div class="text-lg font-mono font-semibold text-gray-900 dark:text-white mt-1">
                    {{ Number((entityPanelEntity as any).mentions || 0) }}
                  </div>
                </div>
                <div class="p-3 rounded-lg bg-gray-50 dark:bg-gray-800">
                  <div class="text-xs text-gray-500 dark:text-gray-400">情感（总体）</div>
                  <div class="text-lg font-mono font-semibold text-gray-900 dark:text-white mt-1">
                    {{ Number((entityPanelEntity as any).sentiment || 0).toFixed(2) }}
                  </div>
                </div>
              </div>

              <!-- 有机 / 推广分层情感 -->
              <div
                v-if="(entityPanelEntity as any).organic_sentiment != null || (entityPanelEntity as any).promo_sentiment != null"
                class="grid grid-cols-2 gap-3"
              >
                <div class="p-3 rounded-lg bg-emerald-50 dark:bg-emerald-900/15 border border-emerald-100 dark:border-emerald-800/40">
                  <div class="text-xs text-gray-500 dark:text-gray-400">有机情感</div>
                  <div
                    class="text-lg font-mono font-semibold mt-1"
                    :class="Number((entityPanelEntity as any).organic_sentiment || 0) >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'"
                  >
                    {{ (entityPanelEntity as any).organic_sentiment != null
                        ? (Number((entityPanelEntity as any).organic_sentiment) >= 0 ? '+' : '') + Number((entityPanelEntity as any).organic_sentiment).toFixed(2)
                        : '-' }}
                  </div>
                  <div
                    v-if="(entityPanelEntity as any).organic_sentiment != null && Math.abs(Number((entityPanelEntity as any).organic_sentiment) - Number((entityPanelEntity as any).sentiment || 0)) >= 0.1"
                    class="text-[10px] text-amber-600 dark:text-amber-400 mt-0.5"
                  >
                    ⚠ 与总体差距 ≥0.1
                  </div>
                </div>
                <div class="p-3 rounded-lg bg-amber-50 dark:bg-amber-900/15 border border-amber-100 dark:border-amber-800/40">
                  <div class="text-xs text-gray-500 dark:text-gray-400">推广情感</div>
                  <div
                    class="text-lg font-mono font-semibold mt-1"
                    :class="Number((entityPanelEntity as any).promo_sentiment || 0) >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'"
                  >
                    {{ (entityPanelEntity as any).promo_sentiment != null
                        ? (Number((entityPanelEntity as any).promo_sentiment) >= 0 ? '+' : '') + Number((entityPanelEntity as any).promo_sentiment).toFixed(2)
                        : '-' }}
                  </div>
                </div>
              </div>

              <div class="p-3 rounded-lg bg-gray-50 dark:bg-gray-800">
                <div class="text-xs text-gray-500 dark:text-gray-400 mb-1">平台分布</div>
                <div class="text-sm text-gray-900 dark:text-white">
                  {{ formatDist((entityPanelEntity as any).platform_distribution) }}
                </div>
              </div>

              <div class="p-3 rounded-lg bg-gray-50 dark:bg-gray-800">
                <div class="text-xs text-gray-500 dark:text-gray-400 mb-1">关键词分布</div>
                <div class="text-sm text-gray-900 dark:text-white">
                  {{ formatDist((entityPanelEntity as any).keyword_distribution) }}
                </div>
              </div>

              <div v-if="(entityPanelEntity as any).spam_distribution" class="p-3 rounded-lg bg-gray-50 dark:bg-gray-800">
                <div class="text-xs text-gray-500 dark:text-gray-400 mb-1">推广/有机分布</div>
                <SpamRatioBar :spam-distribution="(entityPanelEntity as any).spam_distribution" />
              </div>

              <div v-if="(entityPanelEntity as any).original_terms?.length" class="p-3 rounded-lg bg-gray-50 dark:bg-gray-800">
                <div class="text-xs text-gray-500 dark:text-gray-400 mb-2">
                  用户原话（{{ (entityPanelEntity as any).original_terms.length }}）
                </div>
                <div class="space-y-2 max-h-72 overflow-y-auto">
                  <div
                    v-for="(term, idx) in (entityPanelEntity as any).original_terms.slice(0, 20)"
                    :key="`eot-${idx}`"
                    class="p-2 rounded bg-white dark:bg-gray-700 text-sm"
                  >
                    <div class="text-gray-800 dark:text-gray-200">{{ term.text }}</div>
                    <div class="text-xs text-gray-400 mt-1">出现 {{ term.count }} 次</div>
                  </div>
                </div>
              </div>

              <!-- 来源任务分解 -->
              <div v-if="(entityPanelEntity as any).source_tasks?.length" class="p-3 rounded-lg bg-gray-50 dark:bg-gray-800">
                <div class="text-xs text-gray-500 dark:text-gray-400 mb-2">
                  来源任务（{{ (entityPanelEntity as any).source_tasks.length }}）
                </div>
                <div class="flex flex-wrap gap-1.5">
                  <span
                    v-for="st in (entityPanelEntity as any).source_tasks.slice(0, 8)"
                    :key="st.task_id"
                    class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-white dark:bg-gray-700 text-xs"
                  >
                    <span class="text-gray-500 dark:text-gray-400 font-mono">#{{ st.task_id }}</span>
                    <span class="text-gray-700 dark:text-gray-300 font-mono">{{ st.mentions }}</span>
                  </span>
                </div>
              </div>

              <!-- 角色 / 类型分布 -->
              <div
                v-if="(entityPanelEntity as any).role_breakdown || (entityPanelEntity as any).type_breakdown"
                class="p-3 rounded-lg bg-gray-50 dark:bg-gray-800 space-y-2"
              >
                <div v-if="(entityPanelEntity as any).role_breakdown" class="space-y-1">
                  <div class="text-xs text-gray-500 dark:text-gray-400">角色分布</div>
                  <div class="flex flex-wrap gap-1.5">
                    <span
                      v-for="(cnt, role) in (entityPanelEntity as any).role_breakdown"
                      :key="role"
                      class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-white dark:bg-gray-700 text-xs"
                    >
                      <span class="text-gray-600 dark:text-gray-400">{{ role }}</span>
                      <span class="font-mono text-gray-900 dark:text-white">{{ cnt }}</span>
                    </span>
                  </div>
                </div>
                <div v-if="(entityPanelEntity as any).type_breakdown" class="space-y-1">
                  <div class="text-xs text-gray-500 dark:text-gray-400">类型分布</div>
                  <div class="flex flex-wrap gap-1.5">
                    <span
                      v-for="(cnt, tp) in (entityPanelEntity as any).type_breakdown"
                      :key="tp"
                      class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-white dark:bg-gray-700 text-xs"
                    >
                      <span class="text-gray-600 dark:text-gray-400">{{ tp }}</span>
                      <span class="font-mono text-gray-900 dark:text-white">{{ cnt }}</span>
                    </span>
                  </div>
                </div>
              </div>

              <!-- 产品特性 / 产品问题 -->
              <div
                v-if="(entityPanelEntity as any).top_features?.length || (entityPanelEntity as any).top_issues?.length"
                class="space-y-2"
              >
                <div
                  v-if="(entityPanelEntity as any).top_features?.length"
                  class="p-3 rounded-lg bg-emerald-50 dark:bg-emerald-900/15"
                >
                  <div class="text-xs text-gray-500 dark:text-gray-400 mb-2">
                    产品特性 Top {{ Math.min((entityPanelEntity as any).top_features.length, 5) }}
                  </div>
                  <div class="space-y-1.5">
                    <div
                      v-for="(feat, fIdx) in (entityPanelEntity as any).top_features.slice(0, 5)"
                      :key="`feat-${fIdx}`"
                      class="flex items-baseline justify-between gap-2"
                    >
                      <span
                        class="text-xs text-gray-800 dark:text-gray-200 truncate flex-1"
                        :title="feat.text"
                      >{{ feat.text }}</span>
                      <span class="text-[10px] font-mono text-emerald-700 dark:text-emerald-400 shrink-0">×{{ feat.mentions }}</span>
                    </div>
                  </div>
                </div>
                <div
                  v-if="(entityPanelEntity as any).top_issues?.length"
                  class="p-3 rounded-lg bg-rose-50 dark:bg-rose-900/15"
                >
                  <div class="text-xs text-gray-500 dark:text-gray-400 mb-2">
                    产品问题 Top {{ Math.min((entityPanelEntity as any).top_issues.length, 5) }}
                  </div>
                  <div class="space-y-1.5">
                    <div
                      v-for="(issue, iIdx) in (entityPanelEntity as any).top_issues.slice(0, 5)"
                      :key="`issue-${iIdx}`"
                      class="flex items-baseline justify-between gap-2"
                    >
                      <span
                        class="text-xs text-gray-800 dark:text-gray-200 truncate flex-1"
                        :title="issue.text"
                      >{{ issue.text }}</span>
                      <span class="text-[10px] font-mono text-rose-700 dark:text-rose-400 shrink-0">×{{ issue.mentions }}</span>
                    </div>
                  </div>
                </div>
              </div>

              <div class="flex items-center justify-end">
                <UButton
                  size="xs"
                  color="neutral"
                  variant="outline"
                  :disabled="!(entityPanelEntity as any).post_ids_sample?.length"
                  :label="(entityPanelEntity as any).post_ids_sample?.length ? `查看样本贴（${(entityPanelEntity as any).post_ids_sample.length}）` : '暂无样本贴'"
                  @click="openEntitySamplePosts"
                />
              </div>
            </div>
            <div v-else class="py-12 text-center text-sm text-gray-400">
              暂无实体证据信息
            </div>
          </template>
        </USlideover>

        <!-- 聚焦层维度证据侧边栏（SWOT/Gap：先证据，后样本） -->
        <USlideover v-model:open="focusPanelOpen">
          <template #title>
            <div class="flex items-center gap-2 min-w-0">
              <span class="text-gray-900 dark:text-white font-medium truncate">
                {{ focusPanelItem?.dimension || '维度详情' }}
              </span>
              <UBadge v-if="focusPanelType" color="neutral" variant="subtle" size="xs">
                {{ focusPanelType === 'swot' ? 'SWOT' : 'Gap' }}
              </UBadge>
            </div>
          </template>
          <template #description>
            <span class="sr-only">
              查看聚焦层维度证据与样本贴入口
            </span>
          </template>
          <template #body>
            <div v-if="focusPanelItem" class="space-y-4">
              <div class="grid grid-cols-2 gap-3">
                <div class="p-3 rounded-lg bg-gray-50 dark:bg-gray-800">
                  <div class="text-xs text-gray-500 dark:text-gray-400">我方</div>
                  <div class="text-lg font-mono font-semibold text-gray-900 dark:text-white mt-1">
                    {{ Number(focusPanelItem.target_sentiment || 0).toFixed(2) }}
                  </div>
                  <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">提及 {{ Number(focusPanelItem.target_mentions || 0) }}</div>
                </div>
                <div class="p-3 rounded-lg bg-gray-50 dark:bg-gray-800">
                  <div class="text-xs text-gray-500 dark:text-gray-400">竞品集合</div>
                  <div class="text-lg font-mono font-semibold text-gray-900 dark:text-white mt-1">
                    {{ Number(focusPanelItem.competitor_sentiment || 0).toFixed(2) }}
                  </div>
                  <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">提及 {{ Number(focusPanelItem.competitor_mentions || 0) }}</div>
                </div>
              </div>

              <!-- 有机 / 推广分层情感 -->
              <div
                v-if="focusPanelItem.target_organic_sentiment != null || focusPanelItem.competitor_organic_sentiment != null
                  || focusPanelItem.target_promo_sentiment != null || focusPanelItem.competitor_promo_sentiment != null"
                class="grid grid-cols-2 gap-3"
              >
                <div class="p-3 rounded-lg bg-emerald-50 dark:bg-emerald-900/15 border border-emerald-100 dark:border-emerald-800/40">
                  <div class="text-xs text-gray-500 dark:text-gray-400">我方有机情感</div>
                  <div
                    class="text-base font-mono font-semibold mt-1"
                    :class="Number(focusPanelItem.target_organic_sentiment || 0) >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'"
                  >
                    {{ focusPanelItem.target_organic_sentiment != null
                      ? (Number(focusPanelItem.target_organic_sentiment) >= 0 ? '+' : '') + Number(focusPanelItem.target_organic_sentiment).toFixed(2)
                      : '-' }}
                  </div>
                  <div v-if="focusPanelItem.target_promo_sentiment != null" class="text-[10px] text-gray-400 mt-0.5 font-mono">
                    推广 {{ Number(focusPanelItem.target_promo_sentiment) >= 0 ? '+' : '' }}{{ Number(focusPanelItem.target_promo_sentiment).toFixed(2) }}
                  </div>
                </div>
                <div class="p-3 rounded-lg bg-emerald-50 dark:bg-emerald-900/15 border border-emerald-100 dark:border-emerald-800/40">
                  <div class="text-xs text-gray-500 dark:text-gray-400">竞品有机情感</div>
                  <div
                    class="text-base font-mono font-semibold mt-1"
                    :class="Number(focusPanelItem.competitor_organic_sentiment || 0) >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'"
                  >
                    {{ focusPanelItem.competitor_organic_sentiment != null
                      ? (Number(focusPanelItem.competitor_organic_sentiment) >= 0 ? '+' : '') + Number(focusPanelItem.competitor_organic_sentiment).toFixed(2)
                      : '-' }}
                  </div>
                  <div v-if="focusPanelItem.competitor_promo_sentiment != null" class="text-[10px] text-gray-400 mt-0.5 font-mono">
                    推广 {{ Number(focusPanelItem.competitor_promo_sentiment) >= 0 ? '+' : '' }}{{ Number(focusPanelItem.competitor_promo_sentiment).toFixed(2) }}
                  </div>
                </div>
              </div>

              <!-- 推广/有机分布条 -->
              <div
                v-if="focusPanelItem.target_spam_distribution || focusPanelItem.competitor_spam_distribution"
                class="p-3 rounded-lg bg-gray-50 dark:bg-gray-800 space-y-2"
              >
                <div class="text-xs text-gray-500 dark:text-gray-400">推广/有机分布</div>
                <div v-if="focusPanelItem.target_spam_distribution" class="flex items-start gap-2">
                  <span class="text-xs text-gray-500 dark:text-gray-400 w-6 shrink-0 pt-0.5">我方</span>
                  <SpamRatioBar :spam-distribution="focusPanelItem.target_spam_distribution" />
                </div>
                <div v-if="focusPanelItem.competitor_spam_distribution" class="flex items-start gap-2">
                  <span class="text-xs text-gray-500 dark:text-gray-400 w-6 shrink-0 pt-0.5">竞品</span>
                  <SpamRatioBar :spam-distribution="focusPanelItem.competitor_spam_distribution" />
                </div>
              </div>

              <div v-if="focusPanelItem.original_terms?.length" class="p-3 rounded-lg bg-gray-50 dark:bg-gray-800">
                <div class="text-xs text-gray-500 dark:text-gray-400 mb-2">
                  维度证据原话（{{ focusPanelItem.original_terms.length }}）
                </div>
                <div class="space-y-2 max-h-72 overflow-y-auto">
                  <div
                    v-for="(term, idx) in focusPanelItem.original_terms.slice(0, 20)"
                    :key="`fd-${idx}`"
                    class="p-2 rounded bg-white dark:bg-gray-700 text-sm"
                  >
                    <div class="text-gray-800 dark:text-gray-200">{{ term.text }}</div>
                    <div class="text-xs text-gray-400 mt-1">出现 {{ term.count }} 次</div>
                  </div>
                </div>
              </div>

              <div class="flex items-center justify-end">
                <UButton
                  size="xs"
                  color="neutral"
                  variant="outline"
                  :disabled="!focusPanelItem.post_ids_sample?.length"
                  :label="focusPanelItem.post_ids_sample?.length ? `查看样本贴（${focusPanelItem.post_ids_sample.length}）` : '暂无样本贴'"
                  @click="openFocusSamplePosts"
                />
              </div>
            </div>
            <div v-else class="py-12 text-center text-sm text-gray-400">
              暂无维度证据信息
            </div>
          </template>
        </USlideover>
        </template>
      </div>
    </ClientOnly>
  </div>
</template>
