<script setup lang="ts">
import { computed, ref, watch, onMounted, nextTick } from 'vue'
import type { EChartsOption } from 'echarts'
import SpamRatioBar from '../shared/SpamRatioBar.vue'
import TabSwitch from '../shared/TabSwitch.vue'

interface SpamBreakdown {
  high_spam: { total: number; post: number; comment: number }
  low_spam: { total: number; post: number; comment: number }
}

interface GapItem {
  dimension: string
  target_sentiment: number
  competitor_sentiment: number
  target_mentions: number
  competitor_mentions: number
  delta: number
  /** 有机/推广分层情感（后端提供时使用精确值；否则退回有机占比视图） */
  target_organic_sentiment?: number
  target_promo_sentiment?: number
  competitor_organic_sentiment?: number
  competitor_promo_sentiment?: number
  target_spam_distribution?: SpamBreakdown
  competitor_spam_distribution?: SpamBreakdown
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

// ==================== 视图模式 ====================

type GapViewMode = 'all' | 'organic' | 'promo'
const gapViewMode = ref<GapViewMode>('all')

const gapViewOptions = [
  { value: 'all', label: '全量' },
  { value: 'promo', label: '推广' },
  { value: 'organic', label: '有机' },
]

// ==================== 数据与能力检测 ====================

const items = computed(() => props.data?.dimensions || [])

/** 是否有任何 spam 分布数据（决定是否显示 TabSwitch） */
const hasSpamData = computed(() =>
  items.value.some(i => i.target_spam_distribution != null || i.competitor_spam_distribution != null),
)


// ==================== 视图数值计算 ====================

const getOrganicRatio = (sd?: SpamBreakdown): number | null => {
  if (!sd) return null
  const total = sd.high_spam.total + sd.low_spam.total
  return total > 0 ? sd.low_spam.total / total : null
}

interface ItemDisplayValues {
  targetVal: number
  competitorVal: number
  /** true 时当前值为占比 (0-1)，非情感值 */
  isRatioMode: boolean
}

const getItemDisplayValues = (item: GapItem): ItemDisplayValues => {
  if (gapViewMode.value === 'all') {
    return { targetVal: item.target_sentiment, competitorVal: item.competitor_sentiment, isRatioMode: false }
  }

  if (gapViewMode.value === 'organic') {
    // 优先使用精确分层情感值
    if (item.target_organic_sentiment != null || item.competitor_organic_sentiment != null) {
      return {
        targetVal: item.target_organic_sentiment ?? item.target_sentiment,
        competitorVal: item.competitor_organic_sentiment ?? item.competitor_sentiment,
        isRatioMode: false,
      }
    }
    // 退回：使用有机占比 (0-1)
    return {
      targetVal: getOrganicRatio(item.target_spam_distribution) ?? 0.5,
      competitorVal: getOrganicRatio(item.competitor_spam_distribution) ?? 0.5,
      isRatioMode: true,
    }
  }

  // promo 模式
  if (item.target_promo_sentiment != null || item.competitor_promo_sentiment != null) {
    return {
      targetVal: item.target_promo_sentiment ?? item.target_sentiment,
      competitorVal: item.competitor_promo_sentiment ?? item.competitor_sentiment,
      isRatioMode: false,
    }
  }
  // 退回：使用推广占比 = 1 - 有机占比
  const tr = getOrganicRatio(item.target_spam_distribution)
  const cr = getOrganicRatio(item.competitor_spam_distribution)
  return {
    targetVal: tr != null ? 1 - tr : 0.5,
    competitorVal: cr != null ? 1 - cr : 0.5,
    isRatioMode: true,
  }
}

/**
 * 排序逻辑：
 *   全量 → 保持原始顺序（后端按 delta 排序，竞品优势最大在前）
 *   有机/推广 → 按竞品在该维度的相对优势（competitorVal - targetVal）降序
 *             即：竞品有机声音最强而我方最弱的维度排最前
 */
const displayItems = computed(() => {
  if (gapViewMode.value === 'all') return items.value
  return [...items.value].sort((a, b) => {
    const av = getItemDisplayValues(a)
    const bv = getItemDisplayValues(b)
    return (bv.competitorVal - bv.targetVal) - (av.competitorVal - av.targetVal)
  })
})

// ==================== 格式化辅助 ====================

const formatSentiment = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}`
const formatRatio = (v: number) => `${(v * 100).toFixed(0)}%`
const fmtVal = (v: number, isRatio: boolean) => (isRatio ? formatRatio(v) : formatSentiment(v))

/** 列表中每行的展示指标文本 */
const getListMetric = (item: GapItem) => {
  const { targetVal, competitorVal, isRatioMode } = getItemDisplayValues(item)
  const subjectLabel = props.subject || '目标'

  if (gapViewMode.value === 'all') {
    const targetDisplay = item.target_mentions > 0 ? formatSentiment(item.target_sentiment) : '—'
    return `竞品 ${formatSentiment(item.competitor_sentiment)} (${item.competitor_mentions}条) · ${subjectLabel} ${targetDisplay} (${item.target_mentions}条)`
  }
  const dimension = gapViewMode.value === 'organic' ? '有机' : '推广'
  const unit = isRatioMode ? '占比' : '情感'
  return `竞品${dimension}${unit} ${fmtVal(competitorVal, isRatioMode)} · ${subjectLabel}${dimension}${unit} ${fmtVal(targetVal, isRatioMode)}`
}

// ==================== ECharts 配置 ====================

const getOption = (): EChartsOption => {
  if (!displayItems.value.length) return {}

  const dimensions = displayItems.value.map(i => i.dimension)
  const first = displayItems.value[0]
  if (!first) return {}
  const firstVals = getItemDisplayValues(first)
  const isRatioMode = firstVals.isRatioMode

  const targetData = displayItems.value.map(i => getItemDisplayValues(i).targetVal)
  // 竞品取负值，使其向左延伸形成龙卷风图
  const competitorData = displayItems.value.map(i => -getItemDisplayValues(i).competitorVal)

  const axisFormatter = isRatioMode
    ? (v: number) => {
        const abs = Math.abs(v)
        if (v < 0) return `竞${(abs * 100).toFixed(0)}%`
        if (v > 0) return `我${(abs * 100).toFixed(0)}%`
        return '0'
      }
    : (v: number) => {
        if (v < 0) return `竞${(-v).toFixed(1)}`
        if (v > 0) return `我${v.toFixed(1)}`
        return '0'
      }

  const viewSuffix = gapViewMode.value === 'organic' ? '·有机' : gapViewMode.value === 'promo' ? '·推广' : ''
  const subjectLabel = props.subject || '目标'

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const tooltipFormatter = (params: any) => {
    const idx = params[0]?.dataIndex ?? 0
    const item = displayItems.value[idx]
    if (!item) return ''

    const { targetVal, competitorVal, isRatioMode: ratioMode } = getItemDisplayValues(item)
    const targetDisplay = fmtVal(targetVal, ratioMode)
    const compDisplay = fmtVal(competitorVal, ratioMode)
    const targetColor = ratioMode ? '#10b981' : targetVal >= 0 ? '#10b981' : '#ef4444'
    const compColor = ratioMode ? '#f59e0b' : competitorVal >= 0 ? '#10b981' : '#ef4444'

    const ratioNote = ratioMode
      ? `<div style="margin-top:4px;font-size:10px;color:#9ca3af">（当前为有机占比，暂无分层情感值）</div>`
      : ''

    const buildSpamInfo = (sd: SpamBreakdown | undefined, label: string) => {
      if (!sd) return ''
      const total = sd.high_spam.total + sd.low_spam.total
      const r = total > 0 ? ((sd.low_spam.total / total) * 100).toFixed(0) : '-'
      return `<div style="margin-top:3px;font-size:11px">${label}有机: <b>${r}%</b> · <span style="color:#f59e0b;">推广${sd.high_spam.total}(原${sd.high_spam.post}/评${sd.high_spam.comment})</span> / <span style="color:#22c55e;">有机${sd.low_spam.total}(原${sd.low_spam.post}/评${sd.low_spam.comment})</span></div>`
    }

    return `
      <div style="font-weight:600;margin-bottom:6px">${item.dimension}</div>
      <div style="font-size:12px">
        <div>${subjectLabel}${viewSuffix}：<b style="color:${targetColor}">${targetDisplay}</b> (${item.target_mentions}条)</div>
        ${buildSpamInfo(item.target_spam_distribution, '我方')}
        <div style="margin-top:6px">竞品${viewSuffix}：<b style="color:${compColor}">${compDisplay}</b> (${item.competitor_mentions}条)</div>
        ${buildSpamInfo(item.competitor_spam_distribution, '竞品')}
        ${ratioNote}
      </div>
    `
  }

  return {
    animation: false,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: tooltipFormatter,
    },
    grid: { left: 10, right: 10, top: 20, bottom: 30, containLabel: true },
    xAxis: {
      type: 'value',
      min: -1,
      max: 1,
      axisLabel: { fontSize: 10, formatter: axisFormatter },
      axisLine: { lineStyle: { color: '#e5e7eb' } },
      splitLine: { lineStyle: { color: '#f3f4f6', type: 'dashed' } },
    },
    yAxis: {
      type: 'category',
      data: dimensions,
      axisLabel: { fontSize: 10, width: 80, overflow: 'truncate' },
      axisLine: { lineStyle: { color: '#e5e7eb' } },
      axisTick: { show: false },
    },
    series: [
      {
        name: `${subjectLabel}${viewSuffix}`,
        type: 'bar',
        stack: 'total',
        barWidth: 16,
        itemStyle: { color: '#10b981', opacity: 0.85 },
        data: targetData,
      },
      {
        name: `竞品${viewSuffix}`,
        type: 'bar',
        stack: 'total',
        barWidth: 16,
        itemStyle: { color: '#f59e0b', opacity: 0.85 },
        data: competitorData,
      },
    ],
  }
}

// ==================== 图表生命周期 ====================

const updateChart = async () => {
  await nextTick()
  if (chartRef.value && displayItems.value.length) {
    let instance = getInstance()
    if (!instance) {
      instance = initChart()
      on('click', (params: unknown) => {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const p = params as any
        const idx = p?.dataIndex
        if (typeof idx !== 'number') return
        const item = displayItems.value[idx]
        if (!item) return
        emit('select', item)
      })
    }
    setOption(getOption())
  }
}

watch(() => props.data, updateChart, { deep: true })
watch(gapViewMode, updateChart)

onMounted(updateChart)
</script>

<template>
  <div class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
    <!-- 标题行 -->
    <div class="flex items-center justify-between mb-3">
      <div class="flex items-center gap-3">
        <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Gap 分析</h3>
        <TabSwitch
          v-if="hasSpamData"
          v-model="gapViewMode"
          :options="gapViewOptions"
        />
      </div>
      <p class="text-xs text-gray-500 dark:text-gray-400">
        <template v-if="gapViewMode === 'all'">竞品优势 vs {{ subject || '目标' }}缺失点</template>
        <template v-else-if="gapViewMode === 'organic'">有机声音维度对比</template>
        <template v-else>推广内容维度对比</template>
      </p>
    </div>

    <!-- 图表 -->
    <div v-if="displayItems.length" ref="chartRef" class="h-48" />

    <!-- 列表 -->
    <div v-if="displayItems.length" class="mt-3 space-y-2">
      <div
        v-for="item in displayItems.slice(0, 5)"
        :key="item.dimension"
        class="flex items-center gap-3 p-2.5 rounded-lg cursor-pointer transition-colors border"
        :class="gapViewMode === 'all'
          ? 'bg-amber-50/50 dark:bg-amber-900/10 border-amber-100 dark:border-amber-900/30 hover:bg-amber-50 dark:hover:bg-amber-900/20'
          : 'bg-gray-50 dark:bg-gray-800/50 border-gray-100 dark:border-gray-800 hover:bg-gray-100 dark:hover:bg-gray-800'"
        @click="emit('select', item)"
      >
        <UIcon
          :name="gapViewMode === 'all' ? 'i-heroicons-exclamation-triangle' : 'i-heroicons-chart-bar-square'"
          class="w-4 h-4 shrink-0"
          :class="gapViewMode === 'all' ? 'text-amber-500' : 'text-blue-500 dark:text-blue-400'"
        />
        <div class="flex-1 min-w-0">
          <div class="text-sm text-gray-900 dark:text-white truncate">{{ item.dimension }}</div>
          <div class="text-[10px] text-gray-500 dark:text-gray-400 mt-0.5">
            {{ getListMetric(item) }}
          </div>
          <!-- Spam 分布条（所有模式均显示） -->
          <div v-if="item.target_spam_distribution || item.competitor_spam_distribution" class="mt-1.5 space-y-0.5">
            <div v-if="item.target_spam_distribution" class="flex items-center gap-1.5 text-[10px]">
              <span class="text-gray-500 dark:text-gray-400 w-4 shrink-0">我</span>
              <SpamRatioBar :spam-distribution="item.target_spam_distribution" />
            </div>
            <div v-if="item.competitor_spam_distribution" class="flex items-center gap-1.5 text-[10px]">
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
