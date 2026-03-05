<script setup lang="ts">
import { computed, watch, onMounted, nextTick, ref } from 'vue'
import type { EChartsOption } from 'echarts'
import TabSwitch from '../shared/TabSwitch.vue'

interface PlatformDNAItem {
  name: string
  role?: string
  total_mentions: number
  total_organic_mentions?: number
  total_promo_mentions?: number
  platform_shares: Record<string, number>
  organic_platform_shares?: Record<string, number>
  promo_platform_shares?: Record<string, number>
}

const props = defineProps<{
  data: PlatformDNAItem[]
  groupData?: PlatformDNAItem[]
  maxItems?: number
}>()

const { chartRef, initChart, setOption, getInstance, clear } = useCharts()

type ViewMode = 'stack' | 'heatmap'
const viewMode = ref<ViewMode>('stack')

const viewModeOptions = [
  { value: 'stack', label: '堆叠' },
  { value: 'heatmap', label: '矩阵' },
]

type SpamDimension = 'all' | 'organic' | 'promo'
const spamDimension = ref<SpamDimension>('all')

const spamDimensionOptions = [
  { value: 'all', label: '全量' },
  { value: 'promo', label: '推广' },
  { value: 'organic', label: '有机' },
]

// ==================== 聚合模式 ====================

type AggregateMode = 'entity' | 'brand'
const aggregateMode = ref<AggregateMode>('entity')

const aggregateModeOptions = [
  { value: 'entity', label: '个体' },
  { value: 'brand', label: '品牌' },
]

const hasGroupData = computed(() => (props.groupData || []).length > 0)

const hasSpamData = computed(() =>
  rawItems.value.some(
    i => (i.total_organic_mentions ?? 0) > 0 || (i.total_promo_mentions ?? 0) > 0,
  ),
)

const getEffectiveShares = (item: PlatformDNAItem): Record<string, number> => {
  if (spamDimension.value === 'organic') return item.organic_platform_shares || {}
  if (spamDimension.value === 'promo') return item.promo_platform_shares || {}
  return item.platform_shares || {}
}

const getEffectiveTotalMentions = (item: PlatformDNAItem): number => {
  if (spamDimension.value === 'organic') return item.total_organic_mentions ?? item.total_mentions
  if (spamDimension.value === 'promo') return item.total_promo_mentions ?? item.total_mentions
  return item.total_mentions
}

const maxItems = computed(() => props.maxItems ?? 10)
const rawItems = computed(() => {
  if (aggregateMode.value === 'brand' && hasGroupData.value) {
    return props.groupData || []
  }
  return props.data || []
})
const sortedItems = computed(() => {
  const list = rawItems.value.slice()
  list.sort((a, b) => getEffectiveTotalMentions(b) - getEffectiveTotalMentions(a))
  return list
})
const items = computed(() => sortedItems.value.slice(0, maxItems.value))

// 收集所有平台（从当前视角的 shares 中读取，保证有数据的平台才显示）
const allPlatforms = computed(() => {
  const platformSet = new Set<string>()
  for (const item of items.value) {
    for (const p of Object.keys(getEffectiveShares(item))) {
      platformSet.add(p)
    }
  }
  return Array.from(platformSet).sort()
})

// 官方 7 个平台颜色（对齐 backend/src/social_media/monitors/init_data.py）
const platformColors: Record<string, string> = {
  // 微博 - 红色
  weibo: '#e6162d',
  wb: '#e6162d',
  // B站 - 粉色
  bilibili: '#fb7299',
  bili: '#fb7299',
  // 抖音 - 青色（logo 标志色，避免黑色在深色模式不可见）
  douyin: '#00bcd4',
  dy: '#00bcd4',
  // 快手 - 橙色
  kuaishou: '#ff6a00',
  ks: '#ff6a00',
  // 小红书 - 红色
  xiaohongshu: '#ff2442',
  xhs: '#ff2442',
  // 知乎 - 蓝色
  zhihu: '#0084ff',
  // 贴吧 - 紫色
  tieba: '#7c3aed',
  // 默认 - 灰色
  default: '#94a3b8',
}

// 备用颜色（当平台超出预定义列表时使用）
const fallbackColors = [
  '#6366f1', // 靛蓝
  '#14b8a6', // 青色
  '#f59e0b', // 琥珀
  '#84cc16', // 黄绿
  '#ec4899', // 粉红
  '#8b5cf6', // 紫色
]

// 动态分配颜色的缓存
const dynamicColorMap = new Map<string, string>()
let fallbackColorIndex = 0

const getPlatformColor = (platform: string) => {
  const key = platform.toLowerCase().replace(/[^a-z]/g, '')

  // 1. 优先使用预定义颜色
  if (platformColors[key]) {
    return platformColors[key]
  }

  // 2. 检查动态缓存
  if (dynamicColorMap.has(key)) {
    return dynamicColorMap.get(key)!
  }

  // 3. 分配备用颜色
  const color = fallbackColors[fallbackColorIndex % fallbackColors.length] ?? '#94a3b8'
  fallbackColorIndex++
  dynamicColorMap.set(key, color)
  return color
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
      const share = getEffectiveShares(item)[platform] || 0
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
      total: getEffectiveTotalMentions(item),
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
        const entityItem = items.value[idx]
        const total = entityItem ? getEffectiveTotalMentions(entityItem) : 0
        let content = `<div style="font-weight:600;margin-bottom:6px">${entityName}</div>`
        for (const p of seriesParams) {
          if (parseFloat(p.value) > 0) {
            content += `<div>${p.marker} ${p.seriesName}: <b>${p.value}%</b></div>`
          }
        }
        const totalLabel = spamDimension.value === 'organic' ? '有机量' : spamDimension.value === 'promo' ? '推广量' : '总量'
        content += `<div style="margin-top:6px">${totalLabel}：<b>${formatNumber(total)}</b></div>`
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
      const share = getEffectiveShares(item)[platform] || 0
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
        const brandItem = items.value[yIdx]
        const total = brandItem ? getEffectiveTotalMentions(brandItem) : 0
        const totalLabel = spamDimension.value === 'organic' ? '有机量' : spamDimension.value === 'promo' ? '推广量' : '总量'
        return `
          <div style="font-weight:600;margin-bottom:4px">${brand}</div>
          <div>${platform}: <b>${value}%</b></div>
          <div style="margin-top:4px">${totalLabel}：<b>${formatNumber(total)}</b></div>
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
watch(spamDimension, updateChart)
watch(aggregateMode, updateChart)

onMounted(() => {
  updateChart()
})
</script>

<template>
  <div class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 h-full flex flex-col">
    <div class="flex items-center justify-between mb-3">
      <div class="flex items-center gap-3">
        <h3 class="text-sm font-semibold text-gray-900 dark:text-white">平台阵地 DNA</h3>
        <TabSwitch v-if="hasGroupData" v-model="aggregateMode" :options="aggregateModeOptions" />
        <TabSwitch
          v-if="hasSpamData"
          v-model="spamDimension"
          :options="spamDimensionOptions"
        />
      </div>
      <div class="flex items-center gap-2">
        <TabSwitch v-model="viewMode" :options="viewModeOptions" />
        <span class="text-xs text-gray-500 dark:text-gray-400">Top {{ items.length }}</span>
      </div>
    </div>

    <div v-if="items.length && allPlatforms.length" ref="chartRef" class="flex-1 min-h-[360px]" />
    <div v-else class="flex-1 min-h-[360px] flex items-center justify-center text-sm text-gray-400">
      暂无平台分布数据
    </div>
  </div>
</template>
