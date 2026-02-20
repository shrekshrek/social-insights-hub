<script setup lang="ts">
import { computed, ref } from 'vue'
import SpamRatioBar from '../shared/SpamRatioBar.vue'
import TabSwitch from '../shared/TabSwitch.vue'

interface SpamBreakdown {
  high_spam: { total: number; post: number; comment: number }
  low_spam: { total: number; post: number; comment: number }
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
  target_spam_distribution?: SpamBreakdown
  competitor_spam_distribution?: SpamBreakdown
}

interface SWOTData {
  strengths: SWOTItem[]
  weaknesses: SWOTItem[]
  opportunities: SWOTItem[]
  threats: SWOTItem[]
}

const props = defineProps<{
  data?: SWOTData | null
  subject?: string
}>()

const emit = defineEmits<{
  (e: 'select', item: SWOTItem, type: 'S' | 'W' | 'O' | 'T'): void
}>()

// ==================== 视图模式 ====================

type SWOTViewMode = 'all' | 'organic' | 'promo'
const swotViewMode = ref<SWOTViewMode>('all')

const swotViewOptions = [
  { value: 'all', label: '全量' },
  { value: 'promo', label: '推广' },
  { value: 'organic', label: '有机' },
]

// ==================== 能力检测 ====================

const allItems = computed(() => {
  const d = props.data
  if (!d) return []
  return [...(d.strengths || []), ...(d.weaknesses || []), ...(d.opportunities || []), ...(d.threats || [])]
})

const hasSpamData = computed(() =>
  allItems.value.some(i => i.target_spam_distribution != null || i.competitor_spam_distribution != null),
)

const hasOrganicSentiment = computed(() =>
  allItems.value.some(i => i.target_organic_sentiment != null || i.competitor_organic_sentiment != null),
)

// ==================== 视图数值计算 ====================

interface ItemDisplayValues {
  targetVal: number
  competitorVal: number
  /** targetVal - competitorVal（在当前视图下的优势差） */
  delta: number
  /** true 时当前值为占比 (0-1)，非情感值 */
  isRatioMode: boolean
}

const getOrganicRatio = (sd?: SpamBreakdown): number | null => {
  if (!sd) return null
  const total = sd.high_spam.total + sd.low_spam.total
  return total > 0 ? sd.low_spam.total / total : null
}

const getItemDisplayValues = (item: SWOTItem): ItemDisplayValues => {
  if (swotViewMode.value === 'all') {
    return {
      targetVal: item.target_sentiment,
      competitorVal: item.competitor_sentiment,
      delta: item.delta,
      isRatioMode: false,
    }
  }

  if (swotViewMode.value === 'organic') {
    if (item.target_organic_sentiment != null || item.competitor_organic_sentiment != null) {
      const targetVal = item.target_organic_sentiment ?? item.target_sentiment
      const competitorVal = item.competitor_organic_sentiment ?? item.competitor_sentiment
      return { targetVal, competitorVal, delta: targetVal - competitorVal, isRatioMode: false }
    }
    // 退回：有机占比
    const tr = getOrganicRatio(item.target_spam_distribution) ?? 0.5
    const cr = getOrganicRatio(item.competitor_spam_distribution) ?? 0.5
    return { targetVal: tr, competitorVal: cr, delta: tr - cr, isRatioMode: true }
  }

  // promo
  if (item.target_promo_sentiment != null || item.competitor_promo_sentiment != null) {
    const targetVal = item.target_promo_sentiment ?? item.target_sentiment
    const competitorVal = item.competitor_promo_sentiment ?? item.competitor_sentiment
    return { targetVal, competitorVal, delta: targetVal - competitorVal, isRatioMode: false }
  }
  // 退回：推广占比 = 1 - 有机占比
  const tr = getOrganicRatio(item.target_spam_distribution)
  const cr = getOrganicRatio(item.competitor_spam_distribution)
  const tPromo = tr != null ? 1 - tr : 0.5
  const cPromo = cr != null ? 1 - cr : 0.5
  return { targetVal: tPromo, competitorVal: cPromo, delta: tPromo - cPromo, isRatioMode: true }
}

// ==================== 排序 ====================
// 全量：保持后端顺序（已按 delta 排序）
// 有机/推广：按 targetVal - competitorVal 降序（我方有机优势越大排越前）

const sortedItems = (items: SWOTItem[]) => {
  if (swotViewMode.value === 'all') return items
  return [...items].sort((a, b) => getItemDisplayValues(b).delta - getItemDisplayValues(a).delta)
}

// ==================== 格式化 ====================

const fmtSentiment = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}`
const fmtRatio = (v: number) => `${(v * 100).toFixed(0)}%`
const fmtVal = (v: number, isRatio: boolean) => (isRatio ? fmtRatio(v) : fmtSentiment(v))
const fmtDelta = (v: number, isRatio: boolean) =>
  isRatio ? `${v >= 0 ? '+' : ''}${(v * 100).toFixed(0)}%pt` : `${v >= 0 ? '+' : ''}${v.toFixed(2)}`

/**
 * 情感值用情感色（正 emerald，负 red）；
 * 占比值一律用中性灰，避免"高占比 = 正面情感"的误读。
 */
const getValColorClass = (val: number, isRatioMode: boolean) =>
  isRatioMode
    ? 'text-gray-700 dark:text-gray-300'
    : val >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'

// ==================== 数据汇总 ====================

const hasData = computed(() => {
  if (!props.data) return false
  const d = props.data
  return (
    (d.strengths?.length || 0) +
    (d.weaknesses?.length || 0) +
    (d.opportunities?.length || 0) +
    (d.threats?.length || 0) > 0
  )
})

// ==================== 四象限配置 ====================

const quadrantDesc = (key: string) => {
  const mode = swotViewMode.value
  const descs: Record<string, Record<string, string>> = {
    S: { all: '目标独有的高频好评', organic: '目标有机口碑优势维度', promo: '目标推广声量优势维度' },
    W: { all: '目标特有的高频差评', organic: '目标有机口碑劣势维度', promo: '目标推广声量劣势维度' },
    O: { all: '基于竞品的劣势', organic: '竞品有机口碑弱点（机会窗口）', promo: '竞品推广弱点（机会窗口）' },
    T: { all: '基于竞品的优势', organic: '竞品有机口碑强项（威胁维度）', promo: '竞品推广强项（威胁维度）' },
  }
  return descs[key]?.[mode] ?? ''
}

const quadrants = computed(() => [
  {
    key: 'S' as const,
    label: 'Strengths',
    labelCn: '优势',
    icon: 'i-heroicons-arrow-trending-up',
    items: sortedItems(props.data?.strengths || []),
    bgClass: 'bg-emerald-50 dark:bg-emerald-900/10',
    borderClass: 'border-emerald-200 dark:border-emerald-800/50',
    iconClass: 'text-emerald-600 dark:text-emerald-400',
    badgeClass: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
  },
  {
    key: 'W' as const,
    label: 'Weaknesses',
    labelCn: '劣势',
    icon: 'i-heroicons-arrow-trending-down',
    items: sortedItems(props.data?.weaknesses || []),
    bgClass: 'bg-red-50 dark:bg-red-900/10',
    borderClass: 'border-red-200 dark:border-red-800/50',
    iconClass: 'text-red-600 dark:text-red-400',
    badgeClass: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  },
  {
    key: 'O' as const,
    label: 'Opportunities',
    labelCn: '机会',
    icon: 'i-heroicons-light-bulb',
    items: sortedItems(props.data?.opportunities || []),
    bgClass: 'bg-blue-50 dark:bg-blue-900/10',
    borderClass: 'border-blue-200 dark:border-blue-800/50',
    iconClass: 'text-blue-600 dark:text-blue-400',
    badgeClass: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  },
  {
    key: 'T' as const,
    label: 'Threats',
    labelCn: '威胁',
    icon: 'i-heroicons-exclamation-triangle',
    items: sortedItems(props.data?.threats || []),
    bgClass: 'bg-amber-50 dark:bg-amber-900/10',
    borderClass: 'border-amber-200 dark:border-amber-800/50',
    iconClass: 'text-amber-600 dark:text-amber-400',
    badgeClass: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  },
])

// 视图标签（用于情感列的行头）
const viewLabel = computed(() => {
  if (swotViewMode.value === 'organic') return '有机'
  if (swotViewMode.value === 'promo') return '推广'
  return ''
})
</script>

<template>
  <div class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
    <!-- 标题行 -->
    <div class="flex items-center justify-between mb-4">
      <div class="flex items-center gap-3">
        <div>
          <h3 class="text-sm font-semibold text-gray-900 dark:text-white">SWOT 矩阵</h3>
          <p v-if="subject" class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            分析主体：{{ subject }}
          </p>
        </div>
        <TabSwitch
          v-if="hasSpamData"
          v-model="swotViewMode"
          :options="swotViewOptions"
        />
      </div>
      <div class="text-[11px] text-gray-500 dark:text-gray-400">
        竞 = 竞品集合均值
      </div>
    </div>

    <!-- 占比模式说明（无分层情感时显示） -->
    <div
      v-if="swotViewMode !== 'all' && !hasOrganicSentiment && hasSpamData"
      class="mb-3 px-2.5 py-1.5 rounded bg-blue-50 dark:bg-blue-900/20 text-[11px] text-blue-700 dark:text-blue-400 leading-relaxed"
    >
      <template v-if="swotViewMode === 'organic'">
        当前显示<b>有机占比</b>（暂无分层情感值）。数值表示该维度有机内容比例，不代表情感高低。
      </template>
      <template v-else>
        当前显示<b>推广占比</b>（暂无分层情感值）。数值表示该维度推广内容比例，不代表情感高低。
      </template>
    </div>

    <div v-if="hasData" class="grid grid-cols-1 md:grid-cols-2 gap-3">
      <div
        v-for="q in quadrants"
        :key="q.key"
        class="rounded-lg border p-3"
        :class="[q.bgClass, q.borderClass]"
      >
        <!-- 象限头部 -->
        <div class="flex items-center gap-2 mb-1">
          <UIcon :name="q.icon" class="w-4 h-4" :class="q.iconClass" />
          <span class="font-semibold text-sm text-gray-900 dark:text-white">{{ q.label }}</span>
          <span class="text-xs text-gray-500 dark:text-gray-400">({{ q.labelCn }})</span>
          <span class="ml-auto text-[10px] px-1.5 py-0.5 rounded" :class="q.badgeClass">
            {{ q.items.length }}
          </span>
        </div>
        <p class="text-[10px] text-gray-500 dark:text-gray-400 mb-2">{{ quadrantDesc(q.key) }}</p>

        <!-- 维度列表 -->
        <div v-if="q.items.length" class="space-y-1.5 max-h-44 overflow-y-auto">
          <div
            v-for="item in q.items.slice(0, 5)"
            :key="item.dimension"
            class="py-1.5 px-2 rounded bg-white/60 dark:bg-gray-900/40 cursor-pointer transition-colors hover:bg-white dark:hover:bg-gray-900/60"
            @click="emit('select', item, q.key)"
          >
            <!-- 维度名 + 情感对比 -->
            <div class="flex items-center gap-2">
              <span class="text-xs text-gray-800 dark:text-gray-200 truncate flex-1">
                {{ item.dimension }}
              </span>
              <div class="flex items-center gap-1.5 text-[10px] font-mono shrink-0">
                <!-- 当前视图下的情感/占比 -->
                <template v-if="swotViewMode !== 'all'">
                  <span :class="getValColorClass(getItemDisplayValues(item).targetVal, getItemDisplayValues(item).isRatioMode)">
                    我{{ viewLabel }}{{ fmtVal(getItemDisplayValues(item).targetVal, getItemDisplayValues(item).isRatioMode) }}
                  </span>
                  <span class="text-gray-400">vs</span>
                  <span :class="getValColorClass(getItemDisplayValues(item).competitorVal, getItemDisplayValues(item).isRatioMode)">
                    竞{{ viewLabel }}{{ fmtVal(getItemDisplayValues(item).competitorVal, getItemDisplayValues(item).isRatioMode) }}
                  </span>
                </template>
                <!-- 全量视图（原有显示） -->
                <template v-else>
                  <span
                    :class="item.target_mentions > 0
                      ? (item.target_sentiment >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400')
                      : 'text-gray-400 dark:text-gray-500'"
                  >
                    我{{ item.target_mentions > 0 ? fmtSentiment(item.target_sentiment) : '—' }}
                  </span>
                  <span class="text-gray-400">vs</span>
                  <span
                    :class="item.competitor_mentions > 0
                      ? (item.competitor_sentiment >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400')
                      : 'text-gray-400 dark:text-gray-500'"
                  >
                    竞{{ item.competitor_mentions > 0 ? fmtSentiment(item.competitor_sentiment) : '—' }}
                  </span>
                </template>
              </div>

              <!-- delta + 提及数（仅宽屏） -->
              <div class="hidden sm:flex items-center gap-1.5 text-[10px] font-mono shrink-0 text-gray-500 dark:text-gray-400">
                <template v-if="swotViewMode === 'all'">
                  <span>我{{ item.target_mentions }}</span>
                  <span>竞{{ item.competitor_mentions }}</span>
                  <span :class="item.delta >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'">
                    Δ{{ fmtSentiment(item.delta) }}
                  </span>
                </template>
                <template v-else>
                  <span
                    :class="getItemDisplayValues(item).isRatioMode
                      ? 'text-gray-500 dark:text-gray-400'
                      : (getItemDisplayValues(item).delta >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400')"
                  >
                    Δ{{ fmtDelta(getItemDisplayValues(item).delta, getItemDisplayValues(item).isRatioMode) }}
                  </span>
                </template>
              </div>
            </div>

            <!-- 全量模式下补充显示有机/推广分布条（始终可见） -->
            <div v-if="item.target_spam_distribution || item.competitor_spam_distribution" class="mt-1.5 space-y-0.5 text-[10px]">
              <div v-if="item.target_spam_distribution" class="flex items-center gap-1.5">
                <span class="text-gray-500 dark:text-gray-400 w-4 shrink-0">我</span>
                <SpamRatioBar :spam-distribution="item.target_spam_distribution" />
              </div>
              <div v-if="item.competitor_spam_distribution" class="flex items-center gap-1.5">
                <span class="text-gray-500 dark:text-gray-400 w-4 shrink-0">竞</span>
                <SpamRatioBar :spam-distribution="item.competitor_spam_distribution" />
              </div>
            </div>
          </div>
        </div>
        <div v-else class="py-4 text-center text-xs text-gray-400">
          暂无数据
        </div>
      </div>
    </div>

    <div v-else class="py-12 text-center text-sm text-gray-400 dark:text-gray-500">
      暂无 SWOT 分析数据（需设置分析主体且有足够样本量）
    </div>
  </div>
</template>
