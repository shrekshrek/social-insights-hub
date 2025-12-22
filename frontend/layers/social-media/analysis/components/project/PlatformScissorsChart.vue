<script setup lang="ts">
import { computed, watch, onMounted, nextTick } from 'vue'
import type { EChartsOption } from 'echarts'

interface PlatformScissorsItem {
  platform: string
  subject_mentions: number
  industry_mentions: number
  subject_share: number
  industry_share: number
  delta: number
}

interface PlatformScissorsData {
  subject_total_mentions: number
  industry_total_mentions: number
  by_platform: PlatformScissorsItem[]
}

const props = defineProps<{
  data?: PlatformScissorsData | null
  subject?: string
}>()

const { chartRef, initChart, setOption, getInstance } = useCharts()

const items = computed(() => props.data?.by_platform || [])

// ECharts 差异柱状图配置
const getOption = (): EChartsOption => {
  if (!items.value.length) return {}

  const platforms = items.value.map(i => i.platform)
  const subjectData = items.value.map(i => parseFloat((i.subject_share * 100).toFixed(1)))
  const industryData = items.value.map(i => parseFloat((i.industry_share * 100).toFixed(1)))

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
        const delta = item.delta * 100
        const deltaSign = delta >= 0 ? '+' : ''
        const deltaColor = delta >= 0 ? '#10b981' : '#ef4444'
        return `
          <div style="font-weight:600;margin-bottom:6px">${item.platform}</div>
          <div style="font-size:12px">
            <div>${props.subject || '目标'}份额：<b>${(item.subject_share * 100).toFixed(1)}%</b></div>
            <div>行业平均：<b>${(item.industry_share * 100).toFixed(1)}%</b></div>
            <div style="color:${deltaColor}">差异：<b>${deltaSign}${delta.toFixed(1)}%</b></div>
          </div>
        `
      },
    },
    legend: {
      bottom: 0,
      textStyle: { fontSize: 11 },
    },
    grid: {
      left: 10,
      right: 10,
      top: 30,
      bottom: 45,
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: platforms,
      axisLabel: {
        fontSize: 10,
        rotate: 0,
        interval: 0,
      },
      axisLine: { lineStyle: { color: '#e5e7eb' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        fontSize: 10,
        formatter: '{value}%',
      },
      axisLine: { show: false },
      splitLine: { lineStyle: { color: '#f3f4f6', type: 'dashed' } },
    },
    series: [
      {
        name: props.subject || '目标',
        type: 'bar',
        barWidth: 20,
        itemStyle: { color: '#10b981' },
        data: subjectData,
      },
      {
        name: '行业平均',
        type: 'bar',
        barWidth: 20,
        itemStyle: { color: '#94a3b8' },
        data: industryData,
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
    }
    setOption(getOption())
  }
}

watch(() => props.data, updateChart, { deep: true })

onMounted(() => {
  updateChart()
})

// 格式化
const formatDelta = (n: number) => {
  const v = n * 100
  return `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`
}
</script>

<template>
  <div class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
    <div class="flex items-center justify-between mb-3">
      <div>
        <h3 class="text-sm font-semibold text-gray-900 dark:text-white">平台剪刀差</h3>
        <p class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
          {{ subject || '目标' }} 平台份额 vs 行业平均
        </p>
      </div>
    </div>

    <div v-if="items.length" ref="chartRef" class="h-56" />
    <div v-else class="h-56 flex items-center justify-center text-sm text-gray-400">
      暂无平台剪刀差数据
    </div>

    <!-- 差异明细表 -->
    <div v-if="items.length" class="mt-3 pt-3 border-t border-gray-100 dark:border-gray-800">
      <div class="text-xs text-gray-500 dark:text-gray-400 mb-2">差异明细（按绝对值排序）</div>
      <div class="grid grid-cols-2 sm:grid-cols-3 gap-2">
        <div
          v-for="item in items.slice(0, 6)"
          :key="item.platform"
          class="flex items-center justify-between p-2 rounded bg-gray-50 dark:bg-gray-800/50"
        >
          <span class="text-xs text-gray-700 dark:text-gray-300">{{ item.platform }}</span>
          <span
            class="text-xs font-mono"
            :class="item.delta >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'"
          >
            {{ formatDelta(item.delta) }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>
