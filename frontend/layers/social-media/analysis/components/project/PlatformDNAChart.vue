<script setup lang="ts">
import { computed } from 'vue'

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

const maxItems = computed(() => props.maxItems ?? 10)
const items = computed(() => (props.data || []).slice(0, maxItems.value))

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

// ECharts 配置
const chartOptions = computed(() => {
  if (!items.value.length || !allPlatforms.value.length) return null

  const series = allPlatforms.value.map(platform => ({
    name: platform,
    type: 'bar',
    stack: 'total',
    barWidth: 24,
    itemStyle: {
      color: getPlatformColor(platform),
    },
    emphasis: {
      focus: 'series',
    },
    data: items.value.map(item => {
      const share = (item.platform_shares || {})[platform] || 0
      return (share * 100).toFixed(1)
    }),
  }))

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: Array<{ seriesName: string; value: string; marker: string; dataIndex?: number }>) => {
        const entityName = items.value[params[0]?.dataIndex ?? 0]?.name || ''
        let content = `<div style="font-weight:600;margin-bottom:6px">${entityName}</div>`
        for (const p of params) {
          if (parseFloat(p.value) > 0) {
            content += `<div>${p.marker} ${p.seriesName}: <b>${p.value}%</b></div>`
          }
        }
        return content
      },
    },
    legend: {
      type: 'scroll',
      bottom: 0,
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
      axisLine: { lineStyle: { color: '#e5e7eb' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      max: 100,
      axisLabel: {
        fontSize: 10,
        formatter: '{value}%',
      },
      axisLine: { show: false },
      splitLine: { lineStyle: { color: '#f3f4f6', type: 'dashed' } },
    },
    series,
  }
})
</script>

<template>
  <div class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-sm font-semibold text-gray-900 dark:text-white">平台阵地 DNA</h3>
      <span class="text-xs text-gray-500 dark:text-gray-400">Top {{ items.length }} 品牌</span>
    </div>

    <ClientOnly>
      <template #fallback>
        <div class="h-64 flex items-center justify-center bg-gray-50 dark:bg-gray-800/50 rounded">
          <UIcon name="i-heroicons-arrow-path" class="w-5 h-5 animate-spin text-gray-400" />
        </div>
      </template>

      <VChart
        v-if="chartOptions"
        :option="chartOptions"
        autoresize
        class="h-64"
      />
      <div v-else class="h-64 flex items-center justify-center text-sm text-gray-400">
        暂无平台分布数据
      </div>
    </ClientOnly>
  </div>
</template>

