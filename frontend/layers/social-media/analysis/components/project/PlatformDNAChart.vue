<script setup lang="ts">
import { computed, watch, onMounted, nextTick, ref } from 'vue'
import type { EChartsOption } from 'echarts'

interface PlatformDNAItem {
  name: string
  role?: string
  total_mentions: number
  platform_shares: Record<string, number>
}

const props = defineProps<{
  data: PlatformDNAItem[]
  maxItems?: number
}>()

const { chartRef, initChart, setOption, getInstance, clear } = useCharts()

type ViewMode = 'stack' | 'heatmap'
const viewMode = ref<ViewMode>('stack')

const maxItems = computed(() => props.maxItems ?? 10)
const rawItems = computed(() => props.data || [])
const sortedItems = computed(() => {
  const list = rawItems.value.slice()
  list.sort((a, b) => (b.total_mentions || 0) - (a.total_mentions || 0))
  return list
})
const items = computed(() => sortedItems.value.slice(0, maxItems.value))

// 收集所有平台
const allPlatforms = computed(() => {
  const platformSet = new Set<string>()
  for (const item of items.value) {
    for (const p of Object.keys(item.platform_shares || {})) {
      platformSet.add(p)
    }
  }
  return Array.from(platformSet).sort()
})

// 平台颜色（使用固定调色板）
const platformColors: Record<string, string> = {
  weibo: '#ff6b6b',
  bilibili: '#fb7299',
  douyin: '#161823',
  kuaishou: '#ff5500',
  xiaohongshu: '#fe2c55',
  xhs: '#fe2c55',
  zhihu: '#0084ff',
  tieba: '#4e6ef2',
  default: '#94a3b8',
}

const getPlatformColor = (platform: string) => {
  const key = platform.toLowerCase().replace(/[^a-z]/g, '')
  return platformColors[key] || platformColors.default
}

const formatNumber = (n: number) => {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return n.toFixed(0)
}

// ECharts 配置
const getStackOption = (): EChartsOption => {
  if (!items.value.length || !allPlatforms.value.length) return {}

  const series = allPlatforms.value.map(platform => ({
    name: platform,
    type: 'bar' as const,
    stack: 'total',
    barWidth: 24,
    itemStyle: {
      color: getPlatformColor(platform),
    },
    emphasis: {
      focus: 'series' as const,
    },
    data: items.value.map(item => {
      const share = (item.platform_shares || {})[platform] || 0
      return parseFloat((share * 100).toFixed(1))
    }),
  }))

  const totalLabelSeries = {
    name: 'total',
    type: 'scatter' as const,
    symbolSize: 0,
    tooltip: { show: false },
    label: {
      show: true,
      position: 'top' as const,
      color: '#4b5563',
      fontSize: 10,
      formatter: (params: { data: { total: number } }) => formatNumber(params.data.total || 0),
    },
    data: items.value.map(item => ({
      value: [item.name, 102],
      total: item.total_mentions || 0,
    })),
  }

  return {
    animation: false,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      formatter: (params: any) => {
        const seriesParams = Array.isArray(params) ? params : params ? [params] : []
        if (!seriesParams.length) return ''
        const idx = seriesParams[0]?.dataIndex ?? 0
        const entityName = items.value[idx]?.name || ''
        const total = items.value[idx]?.total_mentions || 0
        let content = `<div style="font-weight:600;margin-bottom:6px">${entityName}</div>`
        for (const p of seriesParams) {
          if (parseFloat(p.value) > 0) {
            content += `<div>${p.marker} ${p.seriesName}: <b>${p.value}%</b></div>`
          }
        }
        content += `<div style="margin-top:6px">总量：<b>${formatNumber(total)}</b></div>`
        return content
      },
    },
    legend: {
      type: 'scroll',
      bottom: 0,
      data: allPlatforms.value,
      textStyle: { fontSize: 10 },
      itemWidth: 12,
      itemHeight: 8,
    },
    grid: {
      left: 10,
      right: 10,
      top: 10,
      bottom: 45,
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: items.value.map(i => i.name),
      axisLabel: {
        fontSize: 10,
        rotate: 30,
        interval: 0,
        formatter: (v: string) => (v.length > 8 ? v.slice(0, 8) + '…' : v),
      },
      axisLine: { lineStyle: {} },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      max: 110,
      axisLabel: {
        fontSize: 10,
        formatter: (v: number) => (v > 100 ? '' : `${v}%`),
      },
      axisLine: { show: false },
      splitLine: { lineStyle: { type: 'dashed' } },
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    series: [...series, totalLabelSeries] as any,
  }
}

const getHeatmapOption = (): EChartsOption => {
  if (!items.value.length || !allPlatforms.value.length) return {}

  const data: Array<[number, number, number]> = []
  items.value.forEach((item, yIdx) => {
    allPlatforms.value.forEach((platform, xIdx) => {
      const share = (item.platform_shares || {})[platform] || 0
      data.push([xIdx, yIdx, parseFloat((share * 100).toFixed(1))])
    })
  })

  return {
    animation: false,
    legend: { show: false },
    tooltip: {
      position: 'top',
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      formatter: (params: any) => {
        const raw = params?.data
        if (!Array.isArray(raw)) return ''
        const [xIdx, yIdx, value] = raw as [number, number, number]
        const platform = allPlatforms.value[xIdx] || ''
        const brand = items.value[yIdx]?.name || ''
        const total = items.value[yIdx]?.total_mentions || 0
        return `
          <div style="font-weight:600;margin-bottom:4px">${brand}</div>
          <div>${platform}: <b>${value}%</b></div>
          <div style="margin-top:4px">总量：<b>${formatNumber(total)}</b></div>
        `
      },
    },
    grid: {
      left: 60,
      right: 10,
      top: 10,
      bottom: 50,
    },
    xAxis: {
      type: 'category',
      data: allPlatforms.value,
      axisLabel: {
        fontSize: 10,
        rotate: 30,
        interval: 0,
      },
      axisLine: { lineStyle: {} },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'category',
      data: items.value.map(i => i.name),
      inverse: true,
      axisLabel: { fontSize: 10 },
      axisLine: { lineStyle: {} },
      axisTick: { show: false },
    },
    visualMap: {
      min: 0,
      max: 100,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      textStyle: { fontSize: 10 },
    },
    series: [
      {
        type: 'heatmap',
        data,
        label: { show: false },
        itemStyle: { borderColor: '#f3f4f6', borderWidth: 1 },
        emphasis: { itemStyle: { borderColor: '#111827', borderWidth: 1 } },
      },
    ],
  }
}

const getOption = (): EChartsOption => {
  return viewMode.value === 'heatmap' ? getHeatmapOption() : getStackOption()
}

const updateChart = async () => {
  await nextTick()
  if (chartRef.value && items.value.length && allPlatforms.value.length) {
    let instance = getInstance()
    if (!instance) {
      instance = initChart()
    }
    clear()
    setOption(getOption(), { notMerge: true })
  }
}

watch(() => props.data, updateChart, { deep: true })
watch(viewMode, updateChart)

onMounted(() => {
  updateChart()
})
</script>

<template>
  <div class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 h-full flex flex-col">
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-sm font-semibold text-gray-900 dark:text-white">平台阵地 DNA</h3>
      <div class="flex items-center gap-2">
        <div class="flex items-center gap-1 text-[11px] text-gray-500 dark:text-gray-400">
          <button
            class="px-2 py-0.5 rounded border border-gray-200 dark:border-gray-800"
            :class="viewMode === 'stack' ? 'bg-gray-50 dark:bg-gray-800/60 text-gray-800 dark:text-gray-200' : 'bg-transparent'"
            @click="viewMode = 'stack'"
          >
            堆叠
          </button>
          <button
            class="px-2 py-0.5 rounded border border-gray-200 dark:border-gray-800"
            :class="viewMode === 'heatmap' ? 'bg-gray-50 dark:bg-gray-800/60 text-gray-800 dark:text-gray-200' : 'bg-transparent'"
            @click="viewMode = 'heatmap'"
          >
            矩阵
          </button>
        </div>
        <span class="text-xs text-gray-500 dark:text-gray-400">Top {{ items.length }} 品牌 · 按总量</span>
      </div>
    </div>
    <div class="flex items-center justify-between text-[11px] text-gray-500 dark:text-gray-400 mb-2">
      <span>堆叠：平台占比结构；矩阵：行=品牌、列=平台、颜色越深占比越高</span>
      <span v-if="viewMode === 'stack'">柱顶数字为总量</span>
    </div>

    <div v-if="items.length && allPlatforms.length" ref="chartRef" class="flex-1 min-h-[360px]" />
    <div v-else class="flex-1 min-h-[360px] flex items-center justify-center text-sm text-gray-400">
      暂无平台分布数据
    </div>
  </div>
</template>
