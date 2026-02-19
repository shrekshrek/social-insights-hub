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

const props = defineProps<{
  data: SOVRankingItem[]
  maxItems?: number
  selected?: string | null
}>()

const emit = defineEmits<{
  (e: 'select', item: SOVRankingItem): void
}>()

// ==================== 声量视角 ====================

type SpamView = 'all' | 'promo' | 'organic'
const spamView = ref<SpamView>('all')

const spamViewOptions = [
  { value: 'all', label: '全量' },
  { value: 'promo', label: '推广' },
  { value: 'organic', label: '有机' },
]

// ==================== 排序模式（全量视角下生效）====================

type SortMode = 'share' | 'mentions' | 'efficiency'
const maxItems = computed(() => props.maxItems ?? 15)
const sortMode = ref<SortMode>('share')

const sortModeOptions = [
  { value: 'share', label: '份额' },
  { value: 'mentions', label: '提及' },
  { value: 'efficiency', label: '效能' },
]

// ==================== 能力检测 ====================

const hasSpamData = computed(() =>
  (props.data || []).some(i => i.spam_distribution != null),
)

const hasSentimentData = computed(() =>
  (props.data || []).some(i => i.sentiment != null),
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
  const list = (props.data || []).slice()

  if (spamView.value === 'organic') {
    return list.sort((a, b) => (b.organic_heat ?? getOrganicMentions(b)) - (a.organic_heat ?? getOrganicMentions(a)))
  }
  if (spamView.value === 'promo') {
    return list.sort((a, b) => (b.promo_heat ?? getPromoMentions(b)) - (a.promo_heat ?? getPromoMentions(a)))
  }

  // 全量视角：应用排序模式
  if (sortMode.value === 'mentions') {
    return list.sort((a, b) => (b.mentions || 0) - (a.mentions || 0))
  }
  if (sortMode.value === 'efficiency') {
    const byEff = (x: SOVRankingItem) =>
      x.mentions > 0 ? (x.heat || 0) / x.mentions : -Infinity
    return list.sort((a, b) => byEff(b) - byEff(a))
  }
  return list.sort((a, b) => (b.share || 0) - (a.share || 0))
})

const items = computed(() => sortedItems.value.slice(0, maxItems.value))

// ==================== SOV 份额（按视角）====================

const totalOrganicMentions = computed(() =>
  (props.data || []).reduce((s, i) => s + getOrganicMentions(i), 0),
)

const totalPromoMentions = computed(() =>
  (props.data || []).reduce((s, i) => s + getPromoMentions(i), 0),
)

const totalOrganicHeat = computed(() =>
  (props.data || []).reduce((s, i) => s + (i.organic_heat ?? getOrganicMentions(i)), 0),
)

const totalPromoHeat = computed(() =>
  (props.data || []).reduce((s, i) => s + (i.promo_heat ?? getPromoMentions(i)), 0),
)

const getDisplayShare = (item: SOVRankingItem): number => {
  if (spamView.value === 'organic') {
    const metric = item.organic_heat ?? getOrganicMentions(item)
    return totalOrganicHeat.value > 0 ? metric / totalOrganicHeat.value : 0
  }
  if (spamView.value === 'promo') {
    const metric = item.promo_heat ?? getPromoMentions(item)
    return totalPromoHeat.value > 0 ? metric / totalPromoHeat.value : 0
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
        <!-- 排序模式：仅全量视角下显示 -->
        <TabSwitch v-if="spamView === 'all'" v-model="sortMode" :options="sortModeOptions" />
      </div>
      <div class="flex items-center gap-2">
        <TabSwitch v-if="hasSpamData" v-model="spamView" :options="spamViewOptions" />
        <span class="text-xs text-gray-500 dark:text-gray-400">Top {{ items.length }}</span>
      </div>
    </div>

    <!-- 视角说明 -->
    <div
      v-if="spamView !== 'all'"
      class="mb-2 px-2.5 py-1.5 rounded bg-blue-50 dark:bg-blue-900/20 text-[11px] text-blue-700 dark:text-blue-400"
    >
      <template v-if="spamView === 'organic'">
        <b>有机视角</b>：按有机声量排序，份额为有机 SOV 份额（低推广内容的 share of voice）
      </template>
      <template v-else>
        <b>推广视角</b>：按推广声量排序，份额为推广 SOV 份额（高推广内容的 share of voice）
      </template>
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
                <!-- 全量视角 -->
                <template v-if="spamView === 'all'">
                  <span title="热度值">
                    热 <span class="font-mono text-gray-700 dark:text-gray-300">{{ formatNumber(item.heat) }}</span>
                  </span>
                  <span title="提及帖数">
                    帖 <span class="font-mono text-gray-700 dark:text-gray-300">{{ formatNumber(item.mentions) }}</span>
                  </span>
                  <span title="效能倍数 (热度 / 提及)">
                    效 <span class="font-mono text-gray-700 dark:text-gray-300">{{ item.mentions > 0 ? (item.heat / item.mentions).toFixed(1) : '-' }}</span>x
                  </span>
                  <span v-if="item.spam_distribution" title="有机占比" class="hidden md:inline">
                    机 <span class="font-mono text-gray-700 dark:text-gray-300">{{ (getOrganicRatio(item) * 100).toFixed(0) }}</span>%
                  </span>
                  <!-- 情感（全量，后端填充后自动显示） -->
                  <span
                    v-if="hasSentimentData && item.sentiment != null"
                    class="hidden lg:inline font-mono"
                    :class="item.sentiment >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'"
                    title="整体情感"
                  >
                    {{ fmtSentiment(item.sentiment) }}
                  </span>
                </template>

                <!-- 有机/推广视角 -->
                <template v-else>
                  <span :title="spamView === 'organic' ? '有机提及' : '推广提及'">
                    {{ spamView === 'organic' ? '机' : '广' }}
                    <span class="font-mono text-gray-700 dark:text-gray-300">{{ formatNumber(getEffectiveMentions(item)) }}</span>
                  </span>
                  <!-- 情感（有机/推广，后端填充后自动显示） -->
                  <span
                    v-if="getDisplaySentiment(item) != null"
                    class="font-mono"
                    :class="(getDisplaySentiment(item) ?? 0) >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'"
                    :title="spamView === 'organic' ? '有机情感' : '推广情感'"
                  >
                    {{ fmtSentiment(getDisplaySentiment(item) ?? 0) }}
                  </span>
                </template>
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
