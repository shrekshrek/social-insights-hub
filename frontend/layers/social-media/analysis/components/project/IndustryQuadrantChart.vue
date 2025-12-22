<script setup lang="ts">
import { computed } from 'vue'
import type { IndustryQuadrantPoint } from '../../../types/project-snapshot'

const props = defineProps<{
  data: IndustryQuadrantPoint[]
}>()

const emit = defineEmits<{
  (e: 'select', item: IndustryQuadrantPoint): void
}>()

// ECharts 配置
const chartOptions = computed(() => {
  const points = props.data || []
  if (!points.length) return null

  // 找出最大热度用于归一化点大小
  const maxHeat = Math.max(...points.map(p => p.heat || 0), 1)

  // 角色颜色
  const roleColors: Record<string, string> = {
    Target: '#10b981',
    Competitor: '#f59e0b',
    Context: '#94a3b8',
  }

  // 构建 series 数据（按 role 分组）
  const seriesData: Record<string, Array<[number, number, number, string, IndustryQuadrantPoint]>> = {
    Target: [],
    Competitor: [],
    Context: [],
  }

  for (const p of points) {
    const role = p.role || 'Context'
    const heat = p.heat || 0
    const sentiment = p.sentiment || 0
    const size = Math.max(8, Math.min(30, (heat / maxHeat) * 30 + 8))
    seriesData[role]?.push([heat, sentiment, size, p.name, p])
  }

  const series = Object.entries(seriesData)
    .filter(([, arr]) => arr.length > 0)
    .map(([role, arr]) => ({
      name: role === 'Target' ? '主体' : role === 'Competitor' ? '竞品' : '行业实体',
      type: 'scatter',
      symbolSize: (val: number[]) => val[2],
      itemStyle: {
        color: roleColors[role],
        opacity: 0.75,
      },
      emphasis: {
        itemStyle: {
          opacity: 1,
          shadowBlur: 10,
          shadowColor: roleColors[role],
        },
      },
      data: arr,
    }))

  return {
    tooltip: {
      trigger: 'item',
      formatter: (params: { data: [number, number, number, string, IndustryQuadrantPoint] }) => {
        const [heat, sentiment, , name, point] = params.data
        const roleLabel = point.role === 'Target' ? '主体' : point.role === 'Competitor' ? '竞品' : '行业实体'
        return `
          <div style="font-weight:600;margin-bottom:4px">${name}</div>
          <div style="font-size:12px;color:#888">${roleLabel}</div>
          <div style="margin-top:6px">
            <div>热度：<b>${heat.toFixed(0)}</b></div>
            <div>情感：<b style="color:${sentiment >= 0 ? '#10b981' : '#ef4444'}">${sentiment.toFixed(2)}</b></div>
            <div>提及：<b>${point.mentions || 0}</b></div>
          </div>
        `
      },
    },
    legend: {
      bottom: 0,
      textStyle: { fontSize: 11 },
    },
    grid: {
      left: 50,
      right: 20,
      top: 20,
      bottom: 45,
    },
    xAxis: {
      type: 'value',
      name: '热度',
      nameLocation: 'middle',
      nameGap: 28,
      nameTextStyle: { fontSize: 11, color: '#6b7280' },
      axisLine: { lineStyle: { color: '#e5e7eb' } },
      splitLine: { lineStyle: { color: '#f3f4f6', type: 'dashed' } },
      axisLabel: {
        fontSize: 10,
        formatter: (v: number) => {
          if (v >= 1000000) return `${(v / 1000000).toFixed(0)}M`
          if (v >= 1000) return `${(v / 1000).toFixed(0)}K`
          return v.toString()
        },
      },
    },
    yAxis: {
      type: 'value',
      name: '情感',
      nameLocation: 'middle',
      nameGap: 35,
      nameTextStyle: { fontSize: 11, color: '#6b7280' },
      min: -1,
      max: 1,
      axisLine: { lineStyle: { color: '#e5e7eb' } },
      splitLine: { lineStyle: { color: '#f3f4f6', type: 'dashed' } },
      axisLabel: { fontSize: 10 },
    },
    series,
  }
})

// 点击事件
const handleChartClick = (params: { data?: [number, number, number, string, IndustryQuadrantPoint] }) => {
  if (params.data && params.data[4]) {
    emit('select', params.data[4])
  }
}
</script>

<template>
  <div class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-sm font-semibold text-gray-900 dark:text-white">行业象限</h3>
      <span class="text-xs text-gray-500 dark:text-gray-400">热度 × 情感</span>
    </div>

    <ClientOnly>
      <template #fallback>
        <div class="h-72 flex items-center justify-center bg-gray-50 dark:bg-gray-800/50 rounded">
          <UIcon name="i-heroicons-arrow-path" class="w-5 h-5 animate-spin text-gray-400" />
        </div>
      </template>

      <VChart
        v-if="chartOptions"
        :option="chartOptions"
        autoresize
        class="h-72"
        @click="handleChartClick"
      />
      <div v-else class="h-72 flex items-center justify-center text-sm text-gray-400">
        暂无行业象限数据
      </div>
    </ClientOnly>
  </div>
</template>

