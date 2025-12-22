<script setup lang="ts">
import { computed } from 'vue'

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

const props = defineProps<{
  data?: SWOTData | null
  subject?: string
}>()

const emit = defineEmits<{
  (e: 'select', item: SWOTItem, type: 'S' | 'W' | 'O' | 'T'): void
}>()

const hasData = computed(() => {
  if (!props.data) return false
  const d = props.data
  return (d.strengths?.length || 0) + (d.weaknesses?.length || 0) +
         (d.opportunities?.length || 0) + (d.threats?.length || 0) > 0
})

// 四象限配置
const quadrants = computed(() => [
  {
    key: 'S' as const,
    label: 'Strengths',
    labelCn: '优势',
    desc: '目标独有的高频好评',
    icon: 'i-heroicons-arrow-trending-up',
    items: props.data?.strengths || [],
    bgClass: 'bg-emerald-50 dark:bg-emerald-900/10',
    borderClass: 'border-emerald-200 dark:border-emerald-800/50',
    iconClass: 'text-emerald-600 dark:text-emerald-400',
    badgeClass: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
  },
  {
    key: 'W' as const,
    label: 'Weaknesses',
    labelCn: '劣势',
    desc: '目标特有的高频差评',
    icon: 'i-heroicons-arrow-trending-down',
    items: props.data?.weaknesses || [],
    bgClass: 'bg-red-50 dark:bg-red-900/10',
    borderClass: 'border-red-200 dark:border-red-800/50',
    iconClass: 'text-red-600 dark:text-red-400',
    badgeClass: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  },
  {
    key: 'O' as const,
    label: 'Opportunities',
    labelCn: '机会',
    desc: '基于竞品的劣势',
    icon: 'i-heroicons-light-bulb',
    items: props.data?.opportunities || [],
    bgClass: 'bg-blue-50 dark:bg-blue-900/10',
    borderClass: 'border-blue-200 dark:border-blue-800/50',
    iconClass: 'text-blue-600 dark:text-blue-400',
    badgeClass: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  },
  {
    key: 'T' as const,
    label: 'Threats',
    labelCn: '威胁',
    desc: '基于竞品的优势',
    icon: 'i-heroicons-exclamation-triangle',
    items: props.data?.threats || [],
    bgClass: 'bg-amber-50 dark:bg-amber-900/10',
    borderClass: 'border-amber-200 dark:border-amber-800/50',
    iconClass: 'text-amber-600 dark:text-amber-400',
    badgeClass: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  },
])

// 格式化情感值
const formatSentiment = (v: number) => {
  const sign = v >= 0 ? '+' : ''
  return `${sign}${v.toFixed(2)}`
}
</script>

<template>
  <div class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
    <div class="flex items-center justify-between mb-4">
      <div>
        <h3 class="text-sm font-semibold text-gray-900 dark:text-white">SWOT 矩阵</h3>
        <p v-if="subject" class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
          分析主体：{{ subject }}
        </p>
      </div>
    </div>

    <div v-if="hasData" class="grid grid-cols-1 md:grid-cols-2 gap-3">
      <div
        v-for="q in quadrants"
        :key="q.key"
        class="rounded-lg border p-3"
        :class="[q.bgClass, q.borderClass]"
      >
        <!-- 象限头部 -->
        <div class="flex items-center gap-2 mb-2">
          <UIcon :name="q.icon" class="w-4 h-4" :class="q.iconClass" />
          <span class="font-semibold text-sm text-gray-900 dark:text-white">{{ q.label }}</span>
          <span class="text-xs text-gray-500 dark:text-gray-400">({{ q.labelCn }})</span>
          <span class="ml-auto text-[10px] px-1.5 py-0.5 rounded" :class="q.badgeClass">
            {{ q.items.length }}
          </span>
        </div>
        <p class="text-[10px] text-gray-500 dark:text-gray-400 mb-2">{{ q.desc }}</p>

        <!-- 维度列表 -->
        <div v-if="q.items.length" class="space-y-1.5 max-h-40 overflow-y-auto">
          <div
            v-for="item in q.items.slice(0, 5)"
            :key="item.dimension"
            class="flex items-center gap-2 py-1.5 px-2 rounded bg-white/60 dark:bg-gray-900/40 cursor-pointer transition-colors hover:bg-white dark:hover:bg-gray-900/60"
            @click="emit('select', item, q.key)"
          >
            <span class="text-xs text-gray-800 dark:text-gray-200 truncate flex-1">
              {{ item.dimension }}
            </span>
            <div class="flex items-center gap-2 text-[10px] font-mono shrink-0">
              <span
                :class="item.target_sentiment >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'"
              >
                我{{ formatSentiment(item.target_sentiment) }}
              </span>
              <span class="text-gray-400">vs</span>
              <span
                :class="item.competitor_sentiment >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'"
              >
                竞{{ formatSentiment(item.competitor_sentiment) }}
              </span>
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

