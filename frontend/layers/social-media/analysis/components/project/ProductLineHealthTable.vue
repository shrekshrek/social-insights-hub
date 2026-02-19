<script setup lang="ts">
import { computed } from 'vue'
import SpamRatioBar from '../shared/SpamRatioBar.vue'

interface SpamDistribution {
  high_spam: { total: number; post: number; comment: number }
  low_spam: { total: number; post: number; comment: number }
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
  post_ids_sample?: Array<{ task_id: number; post_id: number }>
}

interface ProductLineHealthData {
  subject: string
  total_heat: number
  members: ProductLineHealthItem[]
}

const props = defineProps<{
  data?: ProductLineHealthData | null
}>()

const emit = defineEmits<{
  (e: 'select', item: ProductLineHealthItem): void
}>()

const members = computed(() => props.data?.members || [])
const subject = computed(() => props.data?.subject || '')
const totalHeat = computed(() => props.data?.total_heat || 0)

// 格式化
const formatNumber = (n: number) => {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return n.toFixed(0)
}

const formatPercent = (n: number) => `${(n * 100).toFixed(1)}%`

// 情感颜色
const getSentimentColor = (s: number) => {
  if (s >= 0.2) return 'text-emerald-600 dark:text-emerald-400'
  if (s <= -0.2) return 'text-red-600 dark:text-red-400'
  return 'text-gray-600 dark:text-gray-400'
}

const getSentimentBg = (s: number) => {
  if (s >= 0.2) return 'bg-emerald-100 dark:bg-emerald-900/30'
  if (s <= -0.2) return 'bg-red-100 dark:bg-red-900/30'
  return 'bg-gray-100 dark:bg-gray-800'
}

// 最大贡献度用于进度条
const maxContribution = computed(() => {
  const contributions = members.value.map(m => m.contribution || 0)
  return Math.max(...contributions, 0.01)
})
</script>

<template>
  <div class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
    <div class="flex items-center justify-between mb-3">
      <div>
        <h3 class="text-sm font-semibold text-gray-900 dark:text-white">产品线健康度</h3>
        <p v-if="subject" class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
          {{ subject }} 旗下子实体分析
        </p>
      </div>
      <div v-if="totalHeat" class="text-xs text-gray-500 dark:text-gray-400">
        总热度：<span class="font-mono">{{ formatNumber(totalHeat) }}</span>
      </div>
    </div>

    <div v-if="members.length" class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="text-left text-xs text-gray-500 dark:text-gray-400 border-b border-gray-100 dark:border-gray-800">
            <th class="py-2 pr-3 font-medium">产品线</th>
            <th class="py-2 pr-3 font-medium text-right">热度</th>
            <th class="py-2 pr-3 font-medium text-right">贡献度</th>
            <th class="py-2 pr-3 font-medium text-center">情感</th>
            <th class="py-2 font-medium">Top 痛点</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-50 dark:divide-gray-800/50">
          <tr
            v-for="(item, idx) in members"
            :key="item.name"
            class="transition-colors hover:bg-gray-50 dark:hover:bg-gray-800/30 cursor-pointer"
            @click="emit('select', item)"
          >
            <td class="py-2.5 pr-3">
              <div class="flex items-center gap-2 mb-1">
                <span
                  class="w-5 h-5 flex items-center justify-center rounded text-[10px] font-medium shrink-0"
                  :class="idx < 3 ? 'bg-primary-100 text-primary-700 dark:bg-primary-900/30 dark:text-primary-400' : 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'"
                >
                  {{ idx + 1 }}
                </span>
                <span class="text-gray-900 dark:text-white">{{ item.name }}</span>
              </div>
              <div v-if="item.spam_distribution" class="ml-7">
                <SpamRatioBar :spam-distribution="item.spam_distribution" />
              </div>
            </td>
            <td class="py-2.5 pr-3 text-right font-mono text-gray-700 dark:text-gray-300">
              {{ formatNumber(item.heat) }}
            </td>
            <td class="py-2.5 pr-3">
              <div class="flex items-center gap-2">
                <div class="w-16 h-1.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
                  <div
                    class="h-full bg-primary-500 rounded-full"
                    :style="{ width: `${(item.contribution / maxContribution) * 100}%` }"
                  />
                </div>
                <span class="text-xs font-mono text-gray-600 dark:text-gray-400 w-12 text-right">
                  {{ formatPercent(item.contribution) }}
                </span>
              </div>
            </td>
            <td class="py-2.5 pr-3 text-center">
              <div class="flex flex-col items-center gap-0.5">
                <span
                  class="inline-block px-2 py-0.5 rounded text-xs font-mono"
                  :class="[getSentimentColor(item.sentiment), getSentimentBg(item.sentiment)]"
                >
                  {{ item.sentiment >= 0 ? '+' : '' }}{{ item.sentiment.toFixed(2) }}
                </span>
                <span
                  v-if="item.organic_sentiment != null"
                  class="text-[10px] font-mono"
                  :class="getSentimentColor(item.organic_sentiment)"
                  :title="`有机情感: ${item.organic_sentiment >= 0 ? '+' : ''}${item.organic_sentiment.toFixed(2)}${Math.abs(item.organic_sentiment - item.sentiment) >= 0.1 ? '（与总体差距 ≥0.1，推广内容可能存在失真）' : ''}`"
                >
                  机{{ item.organic_sentiment >= 0 ? '+' : '' }}{{ item.organic_sentiment.toFixed(2) }}
                  <span v-if="Math.abs(item.organic_sentiment - item.sentiment) >= 0.1" class="text-amber-500">⚠</span>
                </span>
              </div>
            </td>
            <td class="py-2.5">
              <span
                v-if="item.top_pain"
                class="text-xs text-red-600 dark:text-red-400 truncate max-w-32 inline-block"
                :title="item.top_pain"
              >
                {{ item.top_pain }}
              </span>
              <span v-else class="text-xs text-gray-400">-</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-else class="py-8 text-center text-sm text-gray-400 dark:text-gray-500">
      暂无产品线健康度数据（需设置分析主体且有子实体）
    </div>
  </div>
</template>
