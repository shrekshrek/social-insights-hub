<script setup lang="ts">
/**
 * 时间分布图表组件
 *
 * 展示内容发布时间分布的折线图，支持总量/推广-有机分组两种视图
 */
import { ref, watch, onMounted, nextTick } from 'vue'
import type { EChartsOption } from 'echarts'
import type { SpamCountBreakdown } from '../../types'
import TabSwitch from '../shared/TabSwitch.vue'

interface TimeDistributionItem {
  date: string
  count: number
  post_ids?: number[]
  spam_breakdown?: SpamCountBreakdown
}

const props = defineProps<{
  data: TimeDistributionItem[]
  skippedCount?: number
}>()

const emit = defineEmits<{
  (e: 'click-date', date: string, postIds: number[]): void
}>()

const { chartRef, initChart, setOption, getInstance } = useCharts()

// 视图切换
const viewMode = ref('total')
const viewModeOptions = [
  { value: 'total', label: '总量' },
  { value: 'spam_split', label: '分组' },
]

/** 是否存在 spam 分组数据 */
const hasSpamData = computed(() =>
  (props.data || []).some(item => item.spam_breakdown != null),
)

/** 总量视图 ECharts option */
const getTotalOption = (dist: TimeDistributionItem[]): EChartsOption => ({
  animation: false,
  tooltip: {
    trigger: 'item',
    confine: true,
    borderWidth: 1,
    padding: [8, 12],
    textStyle: { color: '#374151', fontSize: 12 },
    formatter: (params: unknown) => {
      const p = params as { name: string; value: number; dataIndex: number }
      if (!p) return ''
      const fullDate = dist[p.dataIndex]?.date || p.name
      const bd = dist[p.dataIndex]?.spam_breakdown
      let spamLine = ''
      if (bd) {
        spamLine = `<div style="margin-top:4px;font-size:11px;color:#9ca3af;">推广 <span style="color:#f59e0b;">${bd.high}</span> / 有机 <span style="color:#22c55e;">${bd.low}</span></div>`
      }
      return `<div style="font-weight:500;margin-bottom:4px;">${fullDate}</div>
              <div>发布数量: <span style="color:#3b82f6;font-weight:600;">${p.value}</span> 条</div>${spamLine}`
    },
  },
  grid: { left: '10px', right: '10px', bottom: '0px', top: '10px', containLabel: true },
  xAxis: {
    type: 'category',
    boundaryGap: false,
    data: dist.map(i => i.date.slice(5)),
    axisLabel: { rotate: 45, fontSize: 10 },
    axisLine: { lineStyle: { color: '#e5e7eb' } },
  },
  yAxis: {
    type: 'value',
    splitLine: { lineStyle: { color: '#f3f4f6', type: 'dashed' } },
    axisLabel: { fontSize: 10 },
  },
  series: [{
    name: '发布数量',
    type: 'line',
    smooth: true,
    symbol: 'circle',
    symbolSize: 8,
    showSymbol: true,
    emphasis: {
      scale: true,
      itemStyle: { shadowBlur: 10, shadowColor: 'rgba(59, 130, 246, 0.5)' },
    },
    data: dist.map(i => i.count),
    lineStyle: { color: '#3b82f6', width: 2 },
    itemStyle: { color: '#3b82f6', borderColor: '#fff', borderWidth: 2 },
    areaStyle: {
      color: {
        type: 'linear',
        x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [
          { offset: 0, color: 'rgba(59, 130, 246, 0.3)' },
          { offset: 1, color: 'rgba(59, 130, 246, 0.05)' },
        ],
      },
    },
  }],
})

/** 分组视图 ECharts option（堆叠面积图） */
const getSpamSplitOption = (dist: TimeDistributionItem[]): EChartsOption => ({
  animation: false,
  tooltip: {
    trigger: 'axis',
    confine: true,
    borderWidth: 1,
    padding: [8, 12],
    textStyle: { color: '#374151', fontSize: 12 },
  },
  legend: {
    data: ['推广', '有机'],
    bottom: 0,
    textStyle: { fontSize: 10 },
    itemWidth: 12,
    itemHeight: 8,
  },
  grid: { left: '10px', right: '10px', bottom: '30px', top: '10px', containLabel: true },
  xAxis: {
    type: 'category',
    boundaryGap: false,
    data: dist.map(i => i.date.slice(5)),
    axisLabel: { rotate: 45, fontSize: 10 },
    axisLine: { lineStyle: { color: '#e5e7eb' } },
  },
  yAxis: {
    type: 'value',
    splitLine: { lineStyle: { color: '#f3f4f6', type: 'dashed' } },
    axisLabel: { fontSize: 10 },
  },
  series: [
    {
      name: '推广',
      type: 'line',
      stack: 'spam',
      smooth: true,
      showSymbol: false,
      data: dist.map(i => i.spam_breakdown?.high ?? 0),
      lineStyle: { color: '#f59e0b', width: 1.5 },
      itemStyle: { color: '#f59e0b' },
      areaStyle: {
        color: {
          type: 'linear',
          x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(245, 158, 11, 0.4)' },
            { offset: 1, color: 'rgba(245, 158, 11, 0.05)' },
          ],
        },
      },
    },
    {
      name: '有机',
      type: 'line',
      stack: 'spam',
      smooth: true,
      showSymbol: false,
      data: dist.map(i => i.spam_breakdown?.low ?? 0),
      lineStyle: { color: '#22c55e', width: 1.5 },
      itemStyle: { color: '#22c55e' },
      areaStyle: {
        color: {
          type: 'linear',
          x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(34, 197, 94, 0.4)' },
            { offset: 1, color: 'rgba(34, 197, 94, 0.05)' },
          ],
        },
      },
    },
  ],
})

const getOption = (): EChartsOption => {
  const dist = props.data || []
  if (dist.length === 0) return {}
  if (viewMode.value === 'spam_split' && hasSpamData.value) {
    return getSpamSplitOption(dist)
  }
  return getTotalOption(dist)
}

const handleClick = (params: { dataIndex: number }) => {
  const dist = props.data || []
  const item = dist[params.dataIndex]
  if (!item) return
  const postIds = item.post_ids || []
  if (postIds.length > 0) {
    emit('click-date', item.date, postIds)
  }
}

const updateChart = async () => {
  await nextTick()
  if (chartRef.value && props.data?.length) {
    let instance = getInstance()
    if (!instance) {
      instance = initChart()
      if (instance) {
        instance.off('click')
        instance.on('click', handleClick)
      }
    }
    const option = getOption()
    if (option && Object.keys(option).length > 0) {
      setOption(option, { notMerge: true })
    }
  }
}

watch(() => props.data, updateChart, { deep: true })
watch(viewMode, updateChart)

onMounted(() => {
  updateChart()
})

const totalDays = computed(() => props.data?.length || 0)
const totalCount = computed(() => props.data?.reduce((sum, i) => sum + i.count, 0) || 0)
</script>

<template>
  <div class="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300">内容发布时间分布</h3>
      <TabSwitch v-if="hasSpamData" v-model="viewMode" :options="viewModeOptions" />
    </div>
    <div ref="chartRef" class="w-full h-48" />
    <div class="mt-3 flex items-center justify-between text-xs text-gray-500">
      <span>共 {{ totalDays }} 天</span>
      <div class="flex items-center gap-3">
        <span v-if="skippedCount" class="text-amber-500" :title="`${skippedCount} 条内容无发布时间`">
          ({{ skippedCount }} 条未统计)
        </span>
        <span>总计 {{ totalCount }} 条内容</span>
      </div>
    </div>
  </div>
</template>
