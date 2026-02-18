<script setup lang="ts">
import { computed, watch, onMounted, nextTick } from 'vue'
import type { EChartsOption } from 'echarts'
import SpamRatioBar from '../shared/SpamRatioBar.vue'

interface GapItem {
  dimension: string
  target_sentiment: number
  competitor_sentiment: number
  target_mentions: number
  competitor_mentions: number
  delta: number
  target_spam_distribution?: {
    high_spam: { total: number; post: number; comment: number }
    low_spam: { total: number; post: number; comment: number }
  }
  competitor_spam_distribution?: {
    high_spam: { total: number; post: number; comment: number }
    low_spam: { total: number; post: number; comment: number }
  }
}

interface GapData {
  dimensions: GapItem[]
}

const props = defineProps<{
  data?: GapData | null
  subject?: string
}>()

const emit = defineEmits<{
  (e: 'select', item: GapItem): void
}>()

const { chartRef, initChart, setOption, getInstance, on } = useCharts()

const items = computed(() => props.data?.dimensions || [])

// 格式化
const formatSentiment = (v: number) => {
  const sign = v >= 0 ? '+' : ''
  return `${sign}${v.toFixed(2)}`
}

// ECharts 龙卷风图配置
const getOption = (): EChartsOption => {
  if (!items.value.length) return {}

  const dimensions = items.value.map(i => i.dimension)
  const targetData = items.value.map(i => i.target_sentiment)
  const competitorData = items.value.map(i => -i.competitor_sentiment) // 取反以形成双向

  return {
    animation: false,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      formatter: (params: any) => {
        const idx = params[0]?.dataIndex ?? 0
        const item = items.value[idx]
        if (!item) return ''
        let targetSpamInfo = ''
        if (item.target_spam_distribution) {
          const sd = item.target_spam_distribution
          const total = sd.high_spam.total + sd.low_spam.total
          const organicRatio = total > 0 ? ((sd.low_spam.total / total) * 100).toFixed(0) : '-'
          targetSpamInfo = `
            <div style="margin-top:4px;font-size:11px">
              我方有机占比: <b>${organicRatio}%</b><br>
              <span style="color:#f59e0b;">推广${sd.high_spam.total}(原${sd.high_spam.post}/评${sd.high_spam.comment})</span> /
              <span style="color:#22c55e;">有机${sd.low_spam.total}(原${sd.low_spam.post}/评${sd.low_spam.comment})</span>
            </div>
          `
        }
        let compSpamInfo = ''
        if (item.competitor_spam_distribution) {
          const sd = item.competitor_spam_distribution
          const total = sd.high_spam.total + sd.low_spam.total
          const organicRatio = total > 0 ? ((sd.low_spam.total / total) * 100).toFixed(0) : '-'
          compSpamInfo = `
            <div style="margin-top:4px;font-size:11px">
              竞品有机占比: <b>${organicRatio}%</b><br>
              <span style="color:#f59e0b;">推广${sd.high_spam.total}(原${sd.high_spam.post}/评${sd.high_spam.comment})</span> /
              <span style="color:#22c55e;">有机${sd.low_spam.total}(原${sd.low_spam.post}/评${sd.low_spam.comment})</span>
            </div>
          `
        }
        return `
          <div style="font-weight:600;margin-bottom:6px">${item.dimension}</div>
          <div style="font-size:12px">
            <div>${props.subject || '目标'}：<b style="color:${item.target_sentiment >= 0 ? '#10b981' : '#ef4444'}">${formatSentiment(item.target_sentiment)}</b> (${item.target_mentions}条)</div>
            ${targetSpamInfo}
            <div style="margin-top:6px">竞品：<b style="color:${item.competitor_sentiment >= 0 ? '#10b981' : '#ef4444'}">${formatSentiment(item.competitor_sentiment)}</b> (${item.competitor_mentions}条)</div>
            ${compSpamInfo}
            <div style="margin-top:6px;color:#f59e0b">⚠️ 竞品强项，我方缺失</div>
          </div>
        `
      },
    },
    grid: {
      left: 10,
      right: 10,
      top: 20,
      bottom: 30,
      containLabel: true,
    },
    xAxis: {
      type: 'value',
      min: -1,
      max: 1,
      axisLabel: {
        fontSize: 10,
        formatter: (v: number) => {
          if (v < 0) return `竞${(-v).toFixed(1)}`
          if (v > 0) return `我${v.toFixed(1)}`
          return '0'
        },
      },
      axisLine: { lineStyle: { color: '#e5e7eb' } },
      splitLine: { lineStyle: { color: '#f3f4f6', type: 'dashed' } },
    },
    yAxis: {
      type: 'category',
      data: dimensions,
      axisLabel: {
        fontSize: 10,
        width: 80,
        overflow: 'truncate',
      },
      axisLine: { lineStyle: { color: '#e5e7eb' } },
      axisTick: { show: false },
    },
    series: [
      {
        name: props.subject || '目标',
        type: 'bar',
        stack: 'total',
        barWidth: 16,
        itemStyle: {
          color: '#10b981',
          opacity: 0.8,
        },
        data: targetData,
      },
      {
        name: '竞品',
        type: 'bar',
        stack: 'total',
        barWidth: 16,
        itemStyle: {
          color: '#f59e0b',
          opacity: 0.8,
        },
        data: competitorData,
      },
    ],
  }
}

const updateChart = async () => {
  await nextTick()
  if (chartRef.value && items.value.length) {
    let instance = getInstance()
    if (!instance) {
      instance = initChart()
      on('click', (params: unknown) => {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const p = params as any
        const idx = p?.dataIndex
        if (typeof idx !== 'number') return
        const item = items.value[idx]
        if (!item) return
        emit('select', item)
      })
    }
    setOption(getOption())
  }
}

watch(() => props.data, updateChart, { deep: true })

onMounted(() => {
  updateChart()
})
</script>

<template>
  <div class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
    <div class="flex items-center justify-between mb-3">
      <div>
        <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Gap 分析</h3>
        <p class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
          竞品优势 vs {{ subject || '目标' }}缺失点
        </p>
      </div>
    </div>

    <div v-if="items.length" ref="chartRef" class="h-48" />

    <!-- 缺口列表 -->
    <div v-if="items.length" class="mt-3 space-y-2">
      <div
      v-for="item in items.slice(0, 5)"
      :key="item.dimension"
      class="flex items-center gap-3 p-2.5 rounded-lg bg-amber-50/50 dark:bg-amber-900/10 border border-amber-100 dark:border-amber-900/30 cursor-pointer transition-colors hover:bg-amber-50 dark:hover:bg-amber-900/20"
      @click="emit('select', item)"
    >
      <UIcon name="i-heroicons-exclamation-triangle" class="w-4 h-4 text-amber-500 shrink-0" />
      <div class="flex-1 min-w-0">
          <div class="text-sm text-gray-900 dark:text-white truncate">{{ item.dimension }}</div>
          <div class="text-[10px] text-gray-500 dark:text-gray-400 mt-0.5">
            竞品 <span class="font-mono text-emerald-600 dark:text-emerald-400">{{ formatSentiment(item.competitor_sentiment) }}</span> ({{ item.competitor_mentions }}条)
            · {{ subject || '目标' }} <span class="font-mono" :class="item.target_sentiment >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'">{{ formatSentiment(item.target_sentiment) }}</span> ({{ item.target_mentions }}条)
          </div>
          <!-- Spam 分布展示 -->
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
    </div>
    <div v-else class="py-8 text-center text-sm text-gray-400 dark:text-gray-500">
      暂无 Gap 分析数据
    </div>
  </div>
</template>
