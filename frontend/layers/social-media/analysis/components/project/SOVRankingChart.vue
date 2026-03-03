<script setup lang="ts">
import { computed, ref } from 'vue'
import TabSwitch from '../shared/TabSwitch.vue'

interface SOVRankingItem {
  name: string
  parent?: string
  role?: string
  heat: number
  organic_heat?: number
  promo_heat?: number
  mentions: number
  share: number
  spam_distribution?: {
    high_spam: { total: number; post: number; comment: number }
    low_spam: { total: number; post: number; comment: number }
  }
  sentiment?: number
  organic_sentiment?: number
  promo_sentiment?: number
  sentiment_distribution?: Record<string, number>
  platform_distribution?: Record<string, number>
}

interface GroupShareItemForSOV {
  name: string
  heat: number
  organic_heat?: number
  promo_heat?: number
  mentions: number
  share?: number
  role?: string
  sentiment?: number
  organic_sentiment?: number
  promo_sentiment?: number
  spam_distribution?: {
    high_spam: { total: number; post: number; comment: number }
    low_spam: { total: number; post: number; comment: number }
  }
  platform_distribution?: Record<string, number>
}

const props = defineProps<{
  data: SOVRankingItem[]
  groupData?: GroupShareItemForSOV[]
  maxItems?: number
  selected?: string | null
  /** 全量实体的有机热度总和（后端提供时用于计算全局口径的有机 SOV 份额） */
  globalOrganicHeat?: number
  /** 全量实体的推广热度总和（后端提供时用于计算全局口径的推广 SOV 份额） */
  globalPromoHeat?: number
}>()

const emit = defineEmits<{
  (e: 'select', item: SOVRankingItem): void
}>()

// ==================== 聚合模式 ====================

type AggregateMode = 'entity' | 'brand'
const aggregateMode = ref<AggregateMode>('entity')

const aggregateModeOptions = [
  { value: 'entity', label: '个体' },
  { value: 'brand', label: '品牌' },
]

const hasGroupData = computed(() => (props.groupData || []).length > 0)

/** 当前生效的数据源：个体使用 data，品牌使用 groupData（适配为 SOVRankingItem 兼容形状） */
const effectiveData = computed<SOVRankingItem[]>(() => {
  if (aggregateMode.value === 'brand' && hasGroupData.value) {
    return (props.groupData || []).map(g => ({
      name: g.name,
      role: g.role,
      heat: g.heat,
      organic_heat: g.organic_heat,
      promo_heat: g.promo_heat,
      mentions: g.mentions,
      share: g.share ?? 0,
      sentiment: g.sentiment,
      organic_sentiment: g.organic_sentiment,
      promo_sentiment: g.promo_sentiment,
      spam_distribution: g.spam_distribution,
      platform_distribution: g.platform_distribution,
    }))
  }
  return props.data || []
})

// ==================== 声量视角 ====================

type SpamView = 'all' | 'promo' | 'organic'
const spamView = ref<SpamView>('all')

const spamViewOptions = [
  { value: 'all', label: '全量' },
  { value: 'promo', label: '推广' },
  { value: 'organic', label: '有机' },
]

// ==================== 排序模式 ====================

type SortMode = 'share' | 'mentions'
const maxItems = computed(() => props.maxItems ?? 15)
const sortMode = ref<SortMode>('share')

const sortModeOptions = [
  { value: 'share', label: '份额' },
  { value: 'mentions', label: '提及' },
]

// ==================== 能力检测 ====================

const hasSpamData = computed(() =>
  effectiveData.value.some(i => i.spam_distribution != null),
)


// ==================== 有机/推广指标辅助 ====================

const getOrganicMentions = (item: SOVRankingItem): number =>
  item.spam_distribution?.low_spam.total ?? 0

const getPromoMentions = (item: SOVRankingItem): number =>
  item.spam_distribution?.high_spam.total ?? 0

const getOrganicRatio = (item: SOVRankingItem): number => {
  const sd = item.spam_distribution
  if (!sd) return -1
  const total = sd.high_spam.total + sd.low_spam.total
  return total > 0 ? sd.low_spam.total / total : -1
}

const getEffectiveMentions = (item: SOVRankingItem): number => {
  if (spamView.value === 'organic') return getOrganicMentions(item)
  if (spamView.value === 'promo') return getPromoMentions(item)
  return item.mentions
}

// ==================== 排序 ====================

const sortedItems = computed(() => {
  const list = effectiveData.value.slice()

  if (sortMode.value === 'mentions') {
    if (spamView.value === 'organic') return list.sort((a, b) => getOrganicMentions(b) - getOrganicMentions(a))
    if (spamView.value === 'promo') return list.sort((a, b) => getPromoMentions(b) - getPromoMentions(a))
    return list.sort((a, b) => (b.mentions || 0) - (a.mentions || 0))
  }

  // 份额：按热度降序（各视角使用对应热度字段）
  if (spamView.value === 'organic') return list.sort((a, b) => (b.organic_heat ?? getOrganicMentions(b)) - (a.organic_heat ?? getOrganicMentions(a)))
  if (spamView.value === 'promo') return list.sort((a, b) => (b.promo_heat ?? getPromoMentions(b)) - (a.promo_heat ?? getPromoMentions(a)))
  return list.sort((a, b) => (b.share || 0) - (a.share || 0))
})

const items = computed(() => sortedItems.value.slice(0, maxItems.value))

// ==================== SOV 份额（按视角）====================

const totalOrganicHeat = computed(() =>
  effectiveData.value.reduce((s, i) => s + (i.organic_heat ?? getOrganicMentions(i)), 0),
)

const totalPromoHeat = computed(() =>
  effectiveData.value.reduce((s, i) => s + (i.promo_heat ?? getPromoMentions(i)), 0),
)

const getDisplayShare = (item: SOVRankingItem): number => {
  if (spamView.value === 'organic') {
    const metric = item.organic_heat ?? getOrganicMentions(item)
    const denom = props.globalOrganicHeat ?? totalOrganicHeat.value
    return denom > 0 ? metric / denom : 0
  }
  if (spamView.value === 'promo') {
    const metric = item.promo_heat ?? getPromoMentions(item)
    const denom = props.globalPromoHeat ?? totalPromoHeat.value
    return denom > 0 ? metric / denom : 0
  }
  return item.share || 0
}

// ==================== 情感（按视角）====================

const getDisplaySentiment = (item: SOVRankingItem): number | null => {
  if (spamView.value === 'organic') return item.organic_sentiment ?? item.sentiment ?? null
  if (spamView.value === 'promo') return item.promo_sentiment ?? item.sentiment ?? null
  return item.sentiment ?? null
}

const fmtSentiment = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}`

// ==================== 通用辅助 ====================

const isSelected = (item: SOVRankingItem) => {
  const selected = (props.selected || '').toString()
  return selected && selected === item.name
}

const roleColors: Record<string, string> = {
  Target: '#10b981',
  Competitor: '#f59e0b',
  Context: '#6b7280',
}

const getRoleColor = (role?: string) => roleColors[role || 'Context'] || roleColors.Context

const maxShare = computed(() => {
  const shares = items.value.map(i => getDisplayShare(i))
  return Math.max(...shares, 0.000001)
})

const getBarWidth = (item: SOVRankingItem) =>
  `${Math.round((getDisplayShare(item) / maxShare.value) * 100)}%`

const formatNumber = (n: number) => {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return n.toString()
}
</script>

<template>
  <div class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
    <!-- 标题栏 -->
    <div class="flex items-center justify-between mb-3">
      <div class="flex items-center gap-3">
        <h3 class="text-sm font-semibold text-gray-900 dark:text-white">SOV 排行榜</h3>
        <TabSwitch v-if="hasGroupData" v-model="aggregateMode" :options="aggregateModeOptions" />
        <TabSwitch v-if="hasSpamData" v-model="spamView" :options="spamViewOptions" />
      </div>
      <div class="flex items-center gap-2">
        <TabSwitch v-model="sortMode" :options="sortModeOptions" />
        <span class="text-xs text-gray-500 dark:text-gray-400">Top {{ items.length }}</span>
      </div>
    </div>

    <!-- 列表 -->
    <div class="space-y-0.5">
      <div
        v-for="(item, idx) in items"
        :key="item.name"
        class="group"
      >
        <div
          class="py-1.5 px-2 rounded-md transition-colors cursor-pointer"
          :class="isSelected(item) ? 'bg-primary-50/70 dark:bg-primary-900/20 ring-1 ring-primary-200/60 dark:ring-primary-800/40' : 'hover:bg-gray-50 dark:hover:bg-gray-800/50'"
          @click="emit('select', item)"
        >
          <div class="flex items-center gap-2">
            <!-- 排名 -->
            <span
              class="w-5 h-5 flex items-center justify-center rounded text-xs font-medium shrink-0"
              :class="idx < 3 ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400' : 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'"
            >
              {{ idx + 1 }}
            </span>

            <div class="min-w-0 flex-1 flex items-center gap-2">
              <!-- 名称 + 角色标签 -->
              <div class="flex items-center gap-1.5 min-w-0 flex-1">
                <span class="text-sm text-gray-900 dark:text-white truncate">{{ item.name }}</span>
                <span
                  v-if="item.role && item.role !== 'Context'"
                  class="shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium"
                  :style="{ backgroundColor: `${getRoleColor(item.role)}20`, color: getRoleColor(item.role) }"
                >
                  {{ item.role === 'Target' ? '主体' : '竞品' }}
                </span>
              </div>

              <!-- 行内指标 -->
              <div class="shrink-0 flex items-center gap-2 sm:gap-3 text-[10px] sm:text-[11px] text-gray-500 dark:text-gray-400 whitespace-nowrap">
                <!-- 热度 / 提及（按视角显示对应数字） -->
                <span :title="spamView === 'organic' ? '有机热度' : spamView === 'promo' ? '推广热度' : '热度'">
                  热 <span class="font-mono text-gray-700 dark:text-gray-300">{{ formatNumber(spamView === 'organic' ? (item.organic_heat ?? getOrganicMentions(item)) : spamView === 'promo' ? (item.promo_heat ?? getPromoMentions(item)) : item.heat) }}</span>
                </span>
                <span :title="spamView === 'organic' ? '有机提及' : spamView === 'promo' ? '推广提及' : '提及帖数'">
                  帖 <span class="font-mono text-gray-700 dark:text-gray-300">{{ formatNumber(getEffectiveMentions(item)) }}</span>
                </span>
                <!-- 有机占比（仅全量视角显示） -->
                <span v-if="spamView === 'all' && item.spam_distribution" title="有机占比" class="hidden md:inline">
                  机 <span class="font-mono text-gray-700 dark:text-gray-300">{{ (getOrganicRatio(item) * 100).toFixed(0) }}</span>%
                </span>
                <!-- 情感 -->
                <span
                  v-if="getDisplaySentiment(item) != null"
                  class="hidden lg:inline font-mono"
                  :class="(getDisplaySentiment(item) ?? 0) >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'"
                  :title="spamView === 'organic' ? '有机情感' : spamView === 'promo' ? '推广情感' : '整体情感'"
                >
                  {{ fmtSentiment(getDisplaySentiment(item) ?? 0) }}
                </span>
              </div>
            </div>

            <!-- SOV 份额进度条 -->
            <div class="hidden sm:block w-16 md:w-20 h-1.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden shrink-0">
              <div
                class="h-full rounded-full transition-all"
                :style="{ width: getBarWidth(item), backgroundColor: getRoleColor(item.role) }"
              />
            </div>

            <!-- 份额数字 -->
            <span
              class="text-xs font-mono text-gray-600 dark:text-gray-400 w-12 text-right shrink-0"
              :title="spamView !== 'all' ? `${spamView === 'organic' ? '有机' : '推广'} SOV（全量: ${((item.share || 0) * 100).toFixed(1)}%）` : undefined"
            >
              {{ (getDisplayShare(item) * 100).toFixed(1) }}%
            </span>
          </div>
        </div>
      </div>
    </div>

    <div v-if="!items.length" class="py-8 text-center text-sm text-gray-400 dark:text-gray-500">
      暂无 SOV 排行数据
    </div>
  </div>
</template>
