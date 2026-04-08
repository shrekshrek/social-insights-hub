<script setup lang="ts">
import { ref, computed } from 'vue'
import type { EntityAttrItem, SpamDistribution, TaskAnalysisResultData, ContextGraph, CompetitorRadar } from '../../types'
import PostListModal from '../shared/PostListModal.vue'
import ClickableCount from '../shared/ClickableCount.vue'
import IpaChart from './IpaChart.vue'
import ContextGraphChart from './ContextGraphChart.vue'
import CompetitorRadarChart from './CompetitorRadarChart.vue'
import TimeDistributionChart from './TimeDistributionChart.vue'
import OriginalTermsPopover from '../shared/OriginalTermsPopover.vue'
import SpamRatioBar from '../shared/SpamRatioBar.vue'
import TabSwitch from '../shared/TabSwitch.vue'

const props = defineProps<{
  data: TaskAnalysisResultData
}>()

// 原文列表弹窗状态
const postListModalOpen = ref(false)
const postListModalTitle = ref('')
const postListModalPostIds = ref<number[]>([])

/** 打开原文列表弹窗 */
const openPostListModal = (title: string, postIds: number[]) => {
  if (!postIds || postIds.length === 0) return
  postListModalTitle.value = title
  postListModalPostIds.value = postIds
  postListModalOpen.value = true
}

/** 获取 taskId */
const taskId = computed(() => props.data.meta.task_id || 0)

// ==================== 热门实体属性：原始观点追溯（层1+2，方案B） ====================
const MAX_ORIGINAL_TERMS_IN_POPOVER = 15

type EntityAttrKind = 'features' | 'issues' | 'expectations'

// 直接使用后端下发的详细项数组（不兼容老报告）
const getEntityAttrItems = (entity: { top_features?: EntityAttrItem[]; top_issues?: EntityAttrItem[]; top_expectations?: EntityAttrItem[] }, kind: EntityAttrKind): EntityAttrItem[] => {
  if (kind === 'features') return (entity.top_features || []).slice(0, 5)
  if (kind === 'issues') return (entity.top_issues || []).slice(0, 5)
  return (entity.top_expectations || []).slice(0, 5)
}

// 列表展开状态
const topEntitiesExpanded = ref(false)
const kolVoicesExpanded = ref(false)

// KOL 声音筛选
const kolFilterMode = ref('all')
const kolFilterOptions = [
  { value: 'all', label: '全部' },
  { value: 'promo', label: '推广' },
  { value: 'organic', label: '有机' },
]

/** 是否有任何 KOL 声音携带 spam 数据 */
const hasKolSpamData = computed(() =>
  props.data.insights.kol_voices.some(v => v.spam_group != null),
)

/** 按筛选模式过滤的 KOL 声音 */
const filteredKolVoices = computed(() => {
  const voices = props.data.insights.kol_voices
  if (kolFilterMode.value === 'organic') return voices.filter(v => v.spam_group === 'low')
  if (kolFilterMode.value === 'promo') return voices.filter(v => v.spam_group === 'high')
  return voices
})

// IPA 筛选
const ipaFilterMode = ref('all')

/** IPA 点中是否有 spam 数据 */
const hasIpaSpamData = computed(() => {
  const ipa = props.data.charts.ipa_analysis
  if (!ipa) return false
  const allPoints = [
    ...ipa.quadrants.strength,
    ...ipa.quadrants.improvement,
    ...ipa.quadrants.maintain,
    ...ipa.quadrants.opportunity,
  ]
  return allPoints.some(p => p.spam_distribution != null)
})

/** 按筛选模式过滤的 IPA 数据 */
const filteredIpaAnalysis = computed(() => {
  const ipa = props.data.charts.ipa_analysis
  if (!ipa || ipaFilterMode.value === 'all') return ipa

  const filterFn = (point: { spam_distribution?: SpamDistribution | null }) => {
    const sd = point.spam_distribution
    if (!sd || !sd.high_spam || !sd.low_spam) return false
    if (ipaFilterMode.value === 'promo') return sd.high_spam.total > 0
    if (ipaFilterMode.value === 'organic') return sd.low_spam.total > 0
    return true
  }

  return {
    ...ipa,
    quadrants: {
      strength: ipa.quadrants.strength.filter(filterFn),
      improvement: ipa.quadrants.improvement.filter(filterFn),
      maintain: ipa.quadrants.maintain.filter(filterFn),
      opportunity: ipa.quadrants.opportunity.filter(filterFn),
    },
  }
})

// ==================== 4D spam 维度排序 ====================

/** 通用 4D spam 维度排序 */
const sortBySpamDimension = <T extends { spam_distribution?: SpamDistribution | null }>(
  items: T[],
  mode: string,
): T[] => {
  if (mode === 'default') return items
  const getValue = (item: T): number => {
    const sd = item.spam_distribution
    if (!sd) return -1
    switch (mode) {
      case 'promo_post': return sd.high_spam.post
      case 'promo_comment': return sd.high_spam.comment
      case 'organic_post': return sd.low_spam.post
      case 'organic_comment': return sd.low_spam.comment
      default: return -1
    }
  }
  return [...items].sort((a, b) => getValue(b) - getValue(a))
}

const spamSortOptions = [
  { value: 'default', label: '综合评分' },
  { value: 'promo_post', label: '推广·原文' },
  { value: 'promo_comment', label: '推广·评论' },
  { value: 'organic_post', label: '有机·原文' },
  { value: 'organic_comment', label: '有机·评论' },
]

// 实体排序
const entitySortMode = ref('default')

/** 是否有任何实体携带 spam 数据 */
const hasEntitySpamData = computed(() =>
  props.data.insights.top_entities.some(e => e.spam_distribution != null),
)

/** 按排序模式重排的实体列表 */
const sortedTopEntities = computed(() =>
  sortBySpamDimension(props.data.insights.top_entities, entitySortMode.value),
)

// 话题排序
const topicSortMode = ref('default')

/** 是否有任何话题携带 spam 数据 */
const hasTopicSpamData = computed(() =>
  props.data.insights.top_topics.some(t => t.spam_distribution != null),
)

/** 排序后的负面话题（热门问题） */
const sortedNegativeTopics = computed(() =>
  sortBySpamDimension(
    props.data.insights.top_topics.filter(t => t.sentiment < 0),
    topicSortMode.value,
  ).slice(0, 10),
)

/** 排序后的正面话题（热门特性） */
const sortedPositiveTopics = computed(() =>
  sortBySpamDimension(
    props.data.insights.top_topics.filter(t => t.sentiment > 0),
    topicSortMode.value,
  ).slice(0, 10),
)

// 话题展开状态
const topicsExpanded = ref(false)

// 关联网络和竞品雷达筛选
const contextGraphFilterMode = ref('all')
const competitorRadarFilterMode = ref('all')
const dimensionFilterOptions = [
  { value: 'all', label: '全部' },
  { value: 'promo', label: '推广' },
  { value: 'organic', label: '有机' },
]

/** 是否有关联网络 spam 数据（检查 organic 和 promo 是否与 all 不同） */
const hasContextGraphSpamData = computed(() => {
  const cg = props.data.charts.context_graph
  if (!cg) return false
  // 如果 organic 和 promo 都与 all 相同（引用相等），说明没有 spam 数据
  return cg.organic !== cg.all || cg.promo !== cg.all
})

/** 是否有竞品雷达 spam 数据（检查 organic 和 promo 是否与 all 不同） */
const hasCompetitorRadarSpamData = computed(() => {
  const cr = props.data.charts.competitor_radar
  if (!cr) return false
  return cr.organic !== cr.all || cr.promo !== cr.all
})

/** 过滤后的关联网络数据 */
const filteredContextGraph = computed((): ContextGraph | undefined => {
  const cg = props.data.charts.context_graph
  if (!cg) return undefined
  const mode = contextGraphFilterMode.value as 'all' | 'organic' | 'promo'
  return cg[mode]
})

/** 过滤后的竞品雷达数据 */
const filteredCompetitorRadar = computed((): CompetitorRadar | undefined => {
  const cr = props.data.charts.competitor_radar
  if (!cr) return undefined
  const mode = competitorRadarFilterMode.value as 'all' | 'organic' | 'promo'
  return cr[mode]
})

/** 获取四象限中某个象限的原文IDs */
const getQuadrantPostIds = (quadrant: string): number[] => {
  const items = props.data.charts.quadrant || []
  return items
    .filter(item => item.quadrant === quadrant)
    .map(item => item.post_id)
}

/** 获取四象限中某个象限的 spam 分组统计 */
const getQuadrantSpamBreakdown = (quadrant: string): { promo: number; organic: number } | null => {
  const items = (props.data.charts.quadrant || []).filter(item => item.quadrant === quadrant)
  const promo = items.filter(item => item.spam_group === 'high').length
  const organic = items.filter(item => item.spam_group === 'low').length
  if (promo === 0 && organic === 0) return null
  return { promo, organic }
}

/** 四象限 spam 分布（预计算，含有机/推广比例） */
const quadrantSpamBreakdowns = computed(() => {
  const keys = ['Q1_danger', 'Q2_brand', 'Q3_complaint', 'Q4_niche', 'neutral'] as const
  const result = {} as Record<string, { promo: number; organic: number; promoRatio: number } | null>
  for (const key of keys) {
    const bd = getQuadrantSpamBreakdown(key)
    if (bd) {
      const total = bd.promo + bd.organic
      result[key] = { ...bd, promoRatio: total > 0 ? bd.promo / total : 0 }
    } else {
      result[key] = null
    }
  }
  return result
})

/** 处理时间分布图表点击事件 */
const handleTimeChartClick = (date: string, postIds: number[]) => {
  openPostListModal(`${date} 发布的内容`, postIds)
}

/** 格式化百分比 */
const formatPercent = (value: number) => {
  return `${(value * 100).toFixed(1)}%`
}

/** 获取 NSR 颜色 */
const getNsrColor = (nsr: number) => {
  if (nsr >= 1) return 'success'
  if (nsr >= 0) return 'info'
  if (nsr >= -1) return 'warning'
  return 'error'
}

/** 获取 SERP 颜色 */
const getSerpColor = (serp: number) => {
  if (serp >= 70) return 'success'
  if (serp >= 50) return 'info'
  if (serp >= 30) return 'warning'
  return 'error'
}

/** 获取情感标签（派生情感值范围 [-1, 1]） */
const getSentimentLabel = (sentiment: number) => {
  if (sentiment >= 0.6) return '正面'
  if (sentiment >= 0.2) return '偏正面'
  if (sentiment >= -0.2) return '中性'
  if (sentiment >= -0.6) return '偏负面'
  return '负面'
}

/** 获取情感颜色（派生情感值范围 [-1, 1]） */
const getSentimentColor = (sentiment: number) => {
  if (sentiment >= 0.2) return 'success'
  if (sentiment >= -0.2) return 'neutral'
  return 'error'
}

/** 获取风险等级颜色 */
const getRiskColor = (risk: string) => {
  if (risk === 'high') return 'error'
  if (risk === 'medium') return 'warning'
  return 'success'
}

/** 获取风险等级标签 */
const getRiskLabel = (risk: string) => {
  if (risk === 'high') return '高风险'
  if (risk === 'medium') return '中风险'
  return '低风险'
}

/** 获取反差方向标签 */
const getConflictDirectionLabel = (direction: string) => {
  if (direction === 'post_positive') return '原文更正面'
  if (direction === 'comment_positive') return '评论更正面'
  return '情感一致'
}

/** 获取 spam 分组标签 */
const getSpamGroupLabel = (group: string | undefined | null) => {
  if (group === 'high') return '推广'
  if (group === 'low') return '有机'
  return null
}

/** 获取 spam 分组颜色 */
const getSpamGroupColor = (group: string | undefined | null) => {
  if (group === 'high') return 'warning'
  if (group === 'low') return 'success'
  return 'neutral'
}

const hasContextGraph = computed(() => !!props.data.charts.context_graph?.all?.nodes?.length)
const hasCompetitorRadar = computed(() => !!(props.data.charts.competitor_radar?.all && props.data.charts.competitor_radar.all.mode !== 'none'))

/** 是否有任何 spam 数据（用于原文列表弹窗显示分组 tab） */
const hasAnySpamData = computed(() =>
  hasEntitySpamData.value || hasTopicSpamData.value || hasIpaSpamData.value || hasKolSpamData.value,
)

</script>

<template>
  <div class="space-y-6">
    <!-- 分析概览：元数据 + 数据量统计 + 数据新鲜度 -->
    <section class="p-4 bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-gray-800 dark:to-gray-800 rounded-lg border border-blue-100 dark:border-gray-700">
      <div class="flex flex-wrap items-center justify-between gap-4">
        <!-- 左侧：分析时间和关键词 -->
        <div class="flex items-center gap-4">
          <div v-if="data.meta.analyzed_at" class="flex items-center gap-2 text-sm">
            <UIcon name="i-heroicons-clock" class="w-4 h-4 text-blue-500" />
            <span class="text-gray-500 dark:text-gray-400">分析时间:</span>
            <span class="text-gray-700 dark:text-gray-300">{{ new Date(data.meta.analyzed_at).toLocaleString('zh-CN') }}</span>
          </div>
          <div v-if="data.meta.keywords?.length" class="flex items-center gap-2 text-sm">
            <UIcon name="i-heroicons-tag" class="w-4 h-4 text-blue-500" />
            <span class="text-gray-500 dark:text-gray-400">关键词:</span>
            <div class="flex gap-1">
              <UBadge v-for="kw in data.meta.keywords.slice(0, 5)" :key="kw" color="primary" variant="subtle" size="xs">
                {{ kw }}
              </UBadge>
            </div>
          </div>
        </div>
        <!-- 右侧：数据量统计 + 数据新鲜度 -->
        <div class="flex items-center gap-6 text-sm">
          <!-- 数据量 -->
          <div class="flex items-center gap-4">
            <div class="flex items-center gap-1">
              <span class="text-gray-500 dark:text-gray-400">总量</span>
              <span class="font-mono font-medium text-gray-900 dark:text-white">{{ data.meta.data_volume.total }}</span>
            </div>
            <div class="flex items-center gap-1">
              <span class="text-gray-500 dark:text-gray-400">初筛</span>
              <span class="font-mono font-medium text-blue-600 dark:text-blue-400">{{ data.meta.data_volume.screened }}</span>
            </div>
            <div class="flex items-center gap-1">
              <span class="text-gray-500 dark:text-gray-400">深度</span>
              <span class="font-mono font-medium text-green-600 dark:text-green-400">{{ data.meta.data_volume.deep_analyzed }}</span>
            </div>
            <div class="flex items-center gap-1">
              <span class="text-gray-500 dark:text-gray-400">评论</span>
              <span class="font-mono font-medium text-purple-600 dark:text-purple-400">{{ data.meta.data_volume.comment_analyzed }}</span>
            </div>
          </div>
          <!-- 分隔线 -->
          <div class="h-4 w-px bg-gray-300 dark:bg-gray-600" />
          <!-- 数据新鲜度 -->
          <div class="flex items-center gap-3">
            <UTooltip text="数据新鲜度">
              <UIcon name="i-heroicons-calendar-days" class="w-4 h-4 text-blue-500" />
            </UTooltip>
            <div class="flex items-center gap-1">
              <span class="text-gray-500 dark:text-gray-400">7天</span>
              <span class="font-mono font-medium text-gray-900 dark:text-white">{{ formatPercent(data.freshness.last_7_days) }}</span>
            </div>
            <div class="flex items-center gap-1">
              <span class="text-gray-500 dark:text-gray-400">30天</span>
              <span class="font-mono font-medium text-gray-900 dark:text-white">{{ formatPercent(data.freshness.last_30_days) }}</span>
            </div>
            <div class="flex items-center gap-1">
              <span class="text-gray-500 dark:text-gray-400">均龄</span>
              <span class="font-mono font-medium text-gray-900 dark:text-white">{{ data.freshness.avg_age_days.toFixed(0) }}天</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 核心指标卡片 -->
    <section>
      <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">核心指标</h3>
      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        <!-- NSR 净情感率 -->
        <div class="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
          <div class="flex items-center justify-between mb-2">
            <span class="text-sm text-gray-500 dark:text-gray-400">NSR 净情感率</span>
            <UBadge :color="getNsrColor(data.metrics.nsr)" variant="subtle" size="xs">
              {{ data.metrics.nsr >= 0 ? '+' : '' }}{{ data.metrics.nsr.toFixed(2) }}
            </UBadge>
          </div>
          <p class="text-2xl font-bold text-gray-900 dark:text-white">
            {{ getSentimentLabel(data.metrics.nsr / 2) }}
          </p>
          <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">范围: -2 ~ +2</p>
          <div v-if="data.metrics.nsr_by_spam" class="mt-1 flex items-center gap-2 text-xs">
            <span class="text-green-600 dark:text-green-400">有机 {{ data.metrics.nsr_by_spam.low.toFixed(2) }}</span>
            <span class="text-orange-600 dark:text-orange-400">推广 {{ data.metrics.nsr_by_spam.high.toFixed(2) }}</span>
          </div>
        </div>

        <!-- CII 互动指数 -->
        <div class="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
          <div class="flex items-center justify-between mb-2">
            <span class="text-sm text-gray-500 dark:text-gray-400">平均 CII</span>
          </div>
          <p class="text-2xl font-bold text-gray-900 dark:text-white">
            {{ data.metrics.avg_cii.toFixed(1) }}
          </p>
          <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">内容互动指数</p>
        </div>

        <!-- SERP 健康度 -->
        <div class="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
          <div class="flex items-center justify-between mb-2">
            <span class="text-sm text-gray-500 dark:text-gray-400">SERP 健康度</span>
            <UBadge :color="getSerpColor(data.metrics.serp_health)" variant="subtle" size="xs">
              {{ data.metrics.serp_health.toFixed(0) }}
            </UBadge>
          </div>
          <UProgress
            :model-value="data.metrics.serp_health"
            :max="100"
            size="sm"
            :color="getSerpColor(data.metrics.serp_health)"
            class="mt-2"
          />
          <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">搜索结果质量</p>
        </div>

        <!-- 营销浓度 -->
        <div class="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
          <div class="flex items-center justify-between mb-2">
            <span class="text-sm text-gray-500 dark:text-gray-400">营销浓度</span>
          </div>
          <p class="text-2xl font-bold text-gray-900 dark:text-white">
            {{ formatPercent(data.metrics.marketing_analysis.promotion_ratio) }}
          </p>
          <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
            自然内容: {{ formatPercent(data.metrics.marketing_analysis.organic_ratio) }}
          </p>
        </div>

        <!-- 舆论反差度 -->
        <div class="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
          <div class="flex items-center justify-between mb-2">
            <span class="text-sm text-gray-500 dark:text-gray-400">舆论反差度</span>
            <UBadge :color="getRiskColor(data.metrics.sentiment_conflict.risk_level)" variant="subtle" size="xs">
              {{ getRiskLabel(data.metrics.sentiment_conflict.risk_level) }}
            </UBadge>
          </div>
          <p class="text-2xl font-bold text-gray-900 dark:text-white">
            {{ data.metrics.sentiment_conflict.avg_conflict.toFixed(2) }}
          </p>
          <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
            {{ getConflictDirectionLabel(data.metrics.sentiment_conflict.conflict_direction) }}
            <span v-if="data.metrics.sentiment_conflict.high_conflict_count > 0" class="text-orange-500">
              ({{ data.metrics.sentiment_conflict.high_conflict_count }}条高反差)
            </span>
          </p>
        </div>
      </div>
    </section>

    <!-- 四象限统计 -->
    <section>
      <div class="flex items-center gap-2 mb-3">
        <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300">舆情四象限分布</h3>
        <UTooltip text="按情感(正/负)和CII互动指数(高/低)划分，以均值为分界">
          <UIcon name="i-heroicons-question-mark-circle" class="w-4 h-4 text-gray-400" />
        </UTooltip>
      </div>
      <div class="grid grid-cols-2 md:grid-cols-5 gap-3">
        <button
          class="text-center p-3 bg-red-50 dark:bg-red-900/20 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors cursor-pointer"
          :disabled="data.charts.quadrant_summary.Q1_danger === 0"
          @click="openPostListModal('爆雷区原文', getQuadrantPostIds('Q1_danger'))"
        >
          <p class="text-xl font-bold text-red-600 dark:text-red-400">{{ data.charts.quadrant_summary.Q1_danger }}</p>
          <p class="text-xs text-gray-600 dark:text-gray-400">爆雷区</p>
          <p class="text-xs text-gray-400 dark:text-gray-500">高互动/负面</p>
          <div v-if="quadrantSpamBreakdowns['Q1_danger']" class="mt-1.5 w-full px-0.5">
            <div class="flex h-1 rounded-full overflow-hidden">
              <div class="bg-orange-400" :style="{ width: (quadrantSpamBreakdowns['Q1_danger'].promoRatio * 100).toFixed(0) + '%' }" />
              <div class="bg-green-400 flex-1" />
            </div>
            <div class="flex justify-between text-[10px] mt-0.5">
              <span class="text-orange-500">推 {{ quadrantSpamBreakdowns['Q1_danger'].promo }}</span>
              <span class="text-green-500">机 {{ quadrantSpamBreakdowns['Q1_danger'].organic }}</span>
            </div>
          </div>
        </button>
        <button
          class="text-center p-3 bg-green-50 dark:bg-green-900/20 rounded-lg hover:bg-green-100 dark:hover:bg-green-900/30 transition-colors cursor-pointer"
          :disabled="data.charts.quadrant_summary.Q2_brand === 0"
          @click="openPostListModal('品牌区原文', getQuadrantPostIds('Q2_brand'))"
        >
          <p class="text-xl font-bold text-green-600 dark:text-green-400">{{ data.charts.quadrant_summary.Q2_brand }}</p>
          <p class="text-xs text-gray-600 dark:text-gray-400">品牌区</p>
          <p class="text-xs text-gray-400 dark:text-gray-500">高互动/正面</p>
          <div v-if="quadrantSpamBreakdowns['Q2_brand']" class="mt-1.5 w-full px-0.5">
            <div class="flex h-1 rounded-full overflow-hidden">
              <div class="bg-orange-400" :style="{ width: (quadrantSpamBreakdowns['Q2_brand'].promoRatio * 100).toFixed(0) + '%' }" />
              <div class="bg-green-400 flex-1" />
            </div>
            <div class="flex justify-between text-[10px] mt-0.5">
              <span class="text-orange-500">推 {{ quadrantSpamBreakdowns['Q2_brand'].promo }}</span>
              <span class="text-green-500">机 {{ quadrantSpamBreakdowns['Q2_brand'].organic }}</span>
            </div>
          </div>
        </button>
        <button
          class="text-center p-3 bg-orange-50 dark:bg-orange-900/20 rounded-lg hover:bg-orange-100 dark:hover:bg-orange-900/30 transition-colors cursor-pointer"
          :disabled="data.charts.quadrant_summary.Q3_complaint === 0"
          @click="openPostListModal('吐槽区原文', getQuadrantPostIds('Q3_complaint'))"
        >
          <p class="text-xl font-bold text-orange-600 dark:text-orange-400">{{ data.charts.quadrant_summary.Q3_complaint }}</p>
          <p class="text-xs text-gray-600 dark:text-gray-400">吐槽区</p>
          <p class="text-xs text-gray-400 dark:text-gray-500">低互动/负面</p>
          <div v-if="quadrantSpamBreakdowns['Q3_complaint']" class="mt-1.5 w-full px-0.5">
            <div class="flex h-1 rounded-full overflow-hidden">
              <div class="bg-orange-400" :style="{ width: (quadrantSpamBreakdowns['Q3_complaint'].promoRatio * 100).toFixed(0) + '%' }" />
              <div class="bg-green-400 flex-1" />
            </div>
            <div class="flex justify-between text-[10px] mt-0.5">
              <span class="text-orange-500">推 {{ quadrantSpamBreakdowns['Q3_complaint'].promo }}</span>
              <span class="text-green-500">机 {{ quadrantSpamBreakdowns['Q3_complaint'].organic }}</span>
            </div>
          </div>
        </button>
        <button
          class="text-center p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg hover:bg-blue-100 dark:hover:bg-blue-900/30 transition-colors cursor-pointer"
          :disabled="data.charts.quadrant_summary.Q4_niche === 0"
          @click="openPostListModal('自嗨区原文', getQuadrantPostIds('Q4_niche'))"
        >
          <p class="text-xl font-bold text-blue-600 dark:text-blue-400">{{ data.charts.quadrant_summary.Q4_niche }}</p>
          <p class="text-xs text-gray-600 dark:text-gray-400">自嗨区</p>
          <p class="text-xs text-gray-400 dark:text-gray-500">低互动/正面</p>
          <div v-if="quadrantSpamBreakdowns['Q4_niche']" class="mt-1.5 w-full px-0.5">
            <div class="flex h-1 rounded-full overflow-hidden">
              <div class="bg-orange-400" :style="{ width: (quadrantSpamBreakdowns['Q4_niche'].promoRatio * 100).toFixed(0) + '%' }" />
              <div class="bg-green-400 flex-1" />
            </div>
            <div class="flex justify-between text-[10px] mt-0.5">
              <span class="text-orange-500">推 {{ quadrantSpamBreakdowns['Q4_niche'].promo }}</span>
              <span class="text-green-500">机 {{ quadrantSpamBreakdowns['Q4_niche'].organic }}</span>
            </div>
          </div>
        </button>
        <button
          class="text-center p-3 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors cursor-pointer"
          :disabled="data.charts.quadrant_summary.neutral === 0"
          @click="openPostListModal('中性区原文', getQuadrantPostIds('neutral'))"
        >
          <p class="text-xl font-bold text-gray-600 dark:text-gray-300">{{ data.charts.quadrant_summary.neutral }}</p>
          <p class="text-xs text-gray-600 dark:text-gray-400">中性区</p>
          <p class="text-xs text-gray-400 dark:text-gray-500">情感中立</p>
          <div v-if="quadrantSpamBreakdowns['neutral']" class="mt-1.5 w-full px-0.5">
            <div class="flex h-1 rounded-full overflow-hidden">
              <div class="bg-orange-400" :style="{ width: (quadrantSpamBreakdowns['neutral'].promoRatio * 100).toFixed(0) + '%' }" />
              <div class="bg-green-400 flex-1" />
            </div>
            <div class="flex justify-between text-[10px] mt-0.5">
              <span class="text-orange-500">推 {{ quadrantSpamBreakdowns['neutral'].promo }}</span>
              <span class="text-green-500">机 {{ quadrantSpamBreakdowns['neutral'].organic }}</span>
            </div>
          </div>
        </button>
      </div>
    </section>

    <!-- 时间分布折线图 -->
    <section v-if="data.charts.time_distribution?.length">
      <ClientOnly>
        <TimeDistributionChart
          :data="data.charts.time_distribution"
          :skipped-count="data.charts.time_distribution_skipped"
          @click-date="handleTimeChartClick"
        />
      </ClientOnly>
    </section>

    <!-- 产品力诊断 (IPA) -->
    <section v-if="data.charts.ipa_analysis?.quadrants">
      <ClientOnly>
        <IpaChart :data="filteredIpaAnalysis" @click-point="openPostListModal">
          <TabSwitch v-if="hasIpaSpamData" v-model="ipaFilterMode" :options="dimensionFilterOptions" />
        </IpaChart>
      </ClientOnly>
    </section>

    <!-- 热门观点：问题 vs 特性 -->
    <section v-if="data.insights.top_topics?.length">
      <div class="flex items-center justify-between mb-3">
        <div class="flex items-center gap-3">
          <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300">热门话题</h3>
          <TabSwitch v-if="hasTopicSpamData" v-model="topicSortMode" :options="spamSortOptions" />
        </div>
        <button
          v-if="sortedNegativeTopics.length > 5 || sortedPositiveTopics.length > 5"
          class="text-xs text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300"
          @click="topicsExpanded = !topicsExpanded"
        >
          {{ topicsExpanded ? '收起' : '查看更多' }}
        </button>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <!-- 热门问题（负面观点） -->
        <div class="p-4 bg-red-50 dark:bg-red-900/10 rounded-lg border border-red-100 dark:border-red-900/30">
          <div class="flex items-center gap-2 mb-3">
            <UIcon name="i-heroicons-exclamation-triangle" class="w-5 h-5 text-red-500" />
            <span class="font-medium text-gray-900 dark:text-white">热门问题</span>
            <span class="text-xs text-gray-400">(负面观点)</span>
          </div>
          <div v-if="sortedNegativeTopics.length" class="space-y-3">
            <div
              v-for="issue in sortedNegativeTopics.slice(0, topicsExpanded ? 10 : 5)"
              :key="issue.name"
              class="text-sm"
            >
              <div class="flex items-center justify-between mb-1">
                <OriginalTermsPopover
                  :text="issue.name"
                  :original-terms="issue.original_terms"
                  :max-items="MAX_ORIGINAL_TERMS_IN_POPOVER"
                />
                <div class="flex items-center gap-2 text-xs">
                  <span class="text-gray-500 dark:text-gray-400">
                    热度 <span class="font-mono text-gray-700 dark:text-gray-300">{{ issue.heat.toFixed(1) }}</span>
                  </span>
                  <ClickableCount
                    :count="issue.mentions"
                    :post-ids="issue.post_ids"
                    :label="issue.name"
                    @click="openPostListModal"
                  />
                </div>
              </div>
              <ul v-if="issue.opinions?.length" class="text-xs text-gray-600 dark:text-gray-400 mb-1 list-disc list-inside space-y-0.5">
                <li v-for="(op, idx) in issue.opinions.slice(0, 3)" :key="idx">{{ op.text }} ({{ op.count }})</li>
              </ul>
              <div v-if="issue.spam_distribution" class="flex items-center gap-2 text-xs text-gray-400">
                <SpamRatioBar :spam-distribution="issue.spam_distribution" />
              </div>
            </div>
          </div>
          <p v-else class="text-sm text-gray-400">暂无数据</p>
        </div>

        <!-- 热门特性（正面观点） -->
        <div class="p-4 bg-green-50 dark:bg-green-900/10 rounded-lg border border-green-100 dark:border-green-900/30">
          <div class="flex items-center gap-2 mb-3">
            <UIcon name="i-heroicons-star" class="w-5 h-5 text-green-500" />
            <span class="font-medium text-gray-900 dark:text-white">热门特性</span>
            <span class="text-xs text-gray-400">(正面观点)</span>
          </div>
          <div v-if="sortedPositiveTopics.length" class="space-y-3">
            <div
              v-for="feature in sortedPositiveTopics.slice(0, topicsExpanded ? 10 : 5)"
              :key="feature.name"
              class="text-sm"
            >
              <div class="flex items-center justify-between mb-1">
                <OriginalTermsPopover
                  :text="feature.name"
                  :original-terms="feature.original_terms"
                  :max-items="MAX_ORIGINAL_TERMS_IN_POPOVER"
                />
                <div class="flex items-center gap-2 text-xs">
                  <span class="text-gray-500 dark:text-gray-400">
                    热度 <span class="font-mono text-gray-700 dark:text-gray-300">{{ feature.heat.toFixed(1) }}</span>
                  </span>
                  <ClickableCount
                    :count="feature.mentions"
                    :post-ids="feature.post_ids"
                    :label="feature.name"
                    @click="openPostListModal"
                  />
                </div>
              </div>
              <ul v-if="feature.opinions?.length" class="text-xs text-gray-600 dark:text-gray-400 mb-1 list-disc list-inside space-y-0.5">
                <li v-for="(op, idx) in feature.opinions.slice(0, 3)" :key="idx">{{ op.text }} ({{ op.count }})</li>
              </ul>
              <div v-if="feature.spam_distribution" class="flex items-center gap-2 text-xs text-gray-400">
                <SpamRatioBar :spam-distribution="feature.spam_distribution" />
              </div>
            </div>
          </div>
          <p v-else class="text-sm text-gray-400">暂无数据</p>
        </div>
      </div>
    </section>

    <!-- 关联网络与竞品分析 (并排展示) -->
    <div v-if="hasContextGraph || hasCompetitorRadar" class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <!-- 关联网络 (Context Graph) -->
      <section v-if="hasContextGraph" :class="{'lg:col-span-2': !hasCompetitorRadar}">
        <ClientOnly>
          <ContextGraphChart :data="filteredContextGraph" @click-node="openPostListModal">
            <TabSwitch v-if="hasContextGraphSpamData" v-model="contextGraphFilterMode" :options="dimensionFilterOptions" />
          </ContextGraphChart>
        </ClientOnly>
      </section>

      <!-- 竞品分析 -->
      <section v-if="hasCompetitorRadar" :class="{'lg:col-span-2': !hasContextGraph}">
        <ClientOnly>
          <CompetitorRadarChart :data="filteredCompetitorRadar">
            <TabSwitch v-if="hasCompetitorRadarSpamData" v-model="competitorRadarFilterMode" :options="dimensionFilterOptions" />
          </CompetitorRadarChart>
        </ClientOnly>
      </section>
    </div>

    <!-- 热门实体 -->
    <section v-if="data.insights.top_entities.length > 0">
      <div class="flex items-center justify-between mb-3">
        <div class="flex items-center gap-3">
          <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300">热门实体</h3>
          <TabSwitch v-if="hasEntitySpamData" v-model="entitySortMode" :options="spamSortOptions" />
        </div>
        <button
          v-if="data.insights.top_entities.length > 5"
          class="text-xs text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300"
          @click="topEntitiesExpanded = !topEntitiesExpanded"
        >
          {{ topEntitiesExpanded ? '收起' : `查看全部 ${Math.min(data.insights.top_entities.length, 10)} 项` }}
        </button>
      </div>
      <div class="space-y-2">
        <div
          v-for="entity in sortedTopEntities.slice(0, topEntitiesExpanded ? 10 : 5)"
          :key="entity.name"
          class="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg"
        >
          <!-- 实体基本信息行 -->
          <div class="flex items-center justify-between flex-wrap gap-2">
            <div class="flex items-center gap-2">
              <span class="font-medium text-gray-900 dark:text-white">{{ entity.name }}</span>
              <UBadge color="neutral" variant="subtle" size="xs">{{ entity.type }}</UBadge>
              <UBadge
                :color="entity.role === 'target' ? 'primary' : entity.role === 'competitor' ? 'warning' : 'neutral'"
                variant="subtle"
                size="xs"
              >
                {{ entity.role === 'target' ? '本品' : entity.role === 'competitor' ? '竞品' : '其他' }}
              </UBadge>
            </div>
            <div class="flex items-center gap-2 text-xs">
              <span class="text-gray-500 dark:text-gray-400">
                热度 <span class="font-mono text-gray-700 dark:text-gray-300">{{ entity.heat.toFixed(1) }}</span>
              </span>
              <ClickableCount
                :count="entity.mentions"
                :post-ids="entity.post_ids"
                :label="entity.name"
                @click="openPostListModal"
              />
              <UBadge :color="getSentimentColor(entity.sentiment)" variant="subtle" size="xs">
                {{ getSentimentLabel(entity.sentiment) }}
              </UBadge>
              <!-- 推广 vs 有机情感对比：两组均有数据且差值 > 0.3 时展示 -->
              <template v-if="entity.spam_distribution && entity.spam_distribution.high_spam.total > 0 && entity.spam_distribution.low_spam.total > 0 && Math.abs((entity.promo_sentiment ?? 0) - (entity.organic_sentiment ?? 0)) > 0.3">
                <span class="text-gray-300 dark:text-gray-600">·</span>
                <span class="text-orange-500 dark:text-orange-400">推 {{ entity.promo_sentiment?.toFixed(2) }}</span>
                <span class="text-green-600 dark:text-green-400">机 {{ entity.organic_sentiment?.toFixed(2) }}</span>
              </template>
            </div>
          </div>
          <!-- 情感分布 + Spam 分布 -->
          <div class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
            <template v-if="entity.sentiment_distribution">
              <span class="text-gray-500 dark:text-gray-400">情感分布:</span>
              <span class="text-green-600 dark:text-green-400">正面 {{ entity.sentiment_distribution.positive }}</span>
              <span class="text-gray-500 dark:text-gray-400">中性 {{ entity.sentiment_distribution.neutral }}</span>
              <span class="text-red-600 dark:text-red-400">负面 {{ entity.sentiment_distribution.negative }}</span>
            </template>
            <template v-if="entity.spam_distribution">
              <span class="text-gray-400 dark:text-gray-500">|</span>
              <SpamRatioBar :spam-distribution="entity.spam_distribution" />
            </template>
          </div>
          <!-- 归一化信息（别名、关联实体） -->
          <div v-if="entity.normalized_info" class="mt-2 space-y-1 text-xs">
            <div v-if="entity.normalized_info.aliases?.length" class="flex flex-wrap items-baseline gap-x-2">
              <span class="text-gray-400 dark:text-gray-500 shrink-0">别名:</span>
              <span v-for="alias in entity.normalized_info.aliases.slice(0, 3)" :key="alias" class="text-gray-500 dark:text-gray-400">{{ alias }}</span>
            </div>
            <div v-if="entity.normalized_info.related?.length" class="flex flex-wrap items-baseline gap-x-2">
              <span class="text-gray-400 dark:text-gray-500 shrink-0">关联:</span>
              <span v-for="rel in entity.normalized_info.related.slice(0, 3)" :key="rel" class="text-indigo-500 dark:text-indigo-400">{{ rel }}</span>
            </div>
            <div v-if="entity.normalized_info.merged_from?.length" class="flex flex-wrap items-baseline gap-x-2">
              <UTooltip :text="`已合并 ${entity.normalized_info.merged_from.length} 个相似实体`">
                <span class="text-gray-400 dark:text-gray-500 italic">
                  (合并自: {{ entity.normalized_info.merged_from.slice(0, 2).join('、') }}{{ entity.normalized_info.merged_from.length > 2 ? '...' : '' }})
                </span>
              </UTooltip>
            </div>
          </div>
          <!-- 特性、问题和期望 -->
          <div v-if="entity.top_features?.length || entity.top_issues?.length || entity.top_expectations?.length" class="mt-2 space-y-1 text-xs">
            <div v-if="entity.top_features?.length" class="flex flex-wrap items-baseline gap-x-3">
              <span class="font-medium text-green-600 dark:text-green-400 shrink-0">特性：</span>
              <span
                v-for="item in getEntityAttrItems(entity, 'features')"
                :key="item.text"
                class="text-gray-700 dark:text-gray-300"
              >
                <OriginalTermsPopover
                  :text="item.text"
                  :original-terms="item.original_terms"
                  :max-items="MAX_ORIGINAL_TERMS_IN_POPOVER"
                />
              </span>
            </div>
            <div v-if="entity.top_issues?.length" class="flex flex-wrap items-baseline gap-x-3">
              <span class="font-medium text-red-600 dark:text-red-400 shrink-0">问题：</span>
              <span
                v-for="item in getEntityAttrItems(entity, 'issues')"
                :key="item.text"
                class="text-gray-700 dark:text-gray-300"
              >
                <OriginalTermsPopover
                  :text="item.text"
                  :original-terms="item.original_terms"
                  :max-items="MAX_ORIGINAL_TERMS_IN_POPOVER"
                />
              </span>
            </div>
            <div v-if="entity.top_expectations?.length" class="flex flex-wrap items-baseline gap-x-3">
              <span class="font-medium text-blue-600 dark:text-blue-400 shrink-0">期望：</span>
              <span
                v-for="item in getEntityAttrItems(entity, 'expectations')"
                :key="item.text"
                class="text-gray-700 dark:text-gray-300"
              >
                <OriginalTermsPopover
                  :text="item.text"
                  :original-terms="item.original_terms"
                  :max-items="MAX_ORIGINAL_TERMS_IN_POPOVER"
                />
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 高影响力内容 -->
    <section v-if="data.insights.kol_voices.length > 0">
      <div class="flex items-center justify-between mb-3">
        <div class="flex items-center gap-3">
          <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300">高影响力内容 TOP {{ Math.min(filteredKolVoices.length, 10) }}</h3>
          <TabSwitch v-if="hasKolSpamData" v-model="kolFilterMode" :options="kolFilterOptions" />
        </div>
        <button
          v-if="filteredKolVoices.length > 5"
          class="text-xs text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300"
          @click="kolVoicesExpanded = !kolVoicesExpanded"
        >
          {{ kolVoicesExpanded ? '收起' : `查看全部 ${Math.min(filteredKolVoices.length, 10)} 项` }}
        </button>
      </div>
      <div class="space-y-2">
        <div
          v-for="item in filteredKolVoices.slice(0, kolVoicesExpanded ? 10 : 5)"
          :key="item.post_id"
          class="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg"
        >
          <div class="flex items-center justify-between mb-2">
            <div class="flex items-center gap-2">
              <UIcon name="i-heroicons-fire" class="w-5 h-5 text-orange-500" />
              <span class="font-medium text-gray-900 dark:text-white">{{ item.author }}</span>
            </div>
            <div class="flex items-center gap-2">
              <UBadge :color="getSentimentColor(item.sentiment / 2)" variant="subtle" size="xs">
                {{ getSentimentLabel(item.sentiment / 2) }}
              </UBadge>
              <UBadge v-if="getSpamGroupLabel(item.spam_group)" :color="getSpamGroupColor(item.spam_group)" variant="subtle" size="xs">
                {{ getSpamGroupLabel(item.spam_group) }}
              </UBadge>
              <span class="text-xs text-gray-500 dark:text-gray-400">CII: {{ item.cii.toFixed(1) }}</span>
              <button
                class="inline-flex items-center gap-0.5 text-xs text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300"
                @click="openPostListModal(`${item.author} 的原文`, [item.post_id])"
              >
                <UIcon name="i-heroicons-arrow-top-right-on-square" class="w-3 h-3" />
                原文
              </button>
            </div>
          </div>
          <p class="text-sm text-gray-600 dark:text-gray-400">{{ item.summary }}</p>
        </div>
      </div>
    </section>

    <!-- 原文列表弹窗 -->
    <PostListModal
      v-model:open="postListModalOpen"
      :task-id="taskId"
      :post-ids="postListModalPostIds"
      :title="postListModalTitle"
      :has-spam-data="hasAnySpamData"
    />
  </div>
</template>
