<script setup lang="ts">
import { onMounted, watch, nextTick } from 'vue'
import type { EChartsOption } from 'echarts'

type QuadrantLabel = 'Q1_danger' | 'Q2_brand' | 'Q3_complaint' | 'Q4_niche' | 'neutral'

export interface ProjectQuadrantPoint {
  task_id: number
  post_id: number
  x: number
  y: number
  quadrant: QuadrantLabel
  label?: string
  platform?: string
  keyword?: string
}

const props = defineProps<{
  points?: ProjectQuadrantPoint[]
  avgCii?: number
}>()

const { chartRef, initChart, setOption, getInstance } = useCharts()

const quadrantStyle: Record<QuadrantLabel, { name: string; color: string }> = {
  Q1_danger: { name: '爆雷区', color: '#ef4444' },
  Q2_brand: { name: '品牌区', color: '#10b981' },
  Q3_complaint: { name: '吐槽区', color: '#f97316' },
  Q4_niche: { name: '自嗨区', color: '#3b82f6' },
  neutral: { name: '中性', color: '#9ca3af' },
}

const buildOption = (): EChartsOption => {
  const pts = (props.points || []).filter(p => typeof p.x === 'number' && typeof p.y === 'number')
  const avgCii = typeof props.avgCii === 'number' ? props.avgCii : undefined

  const byQuadrant: Record<QuadrantLabel, ProjectQuadrantPoint[]> = {
    Q1_danger: [],
    Q2_brand: [],
    Q3_complaint: [],
    Q4_niche: [],
    neutral: [],
  }
  pts.forEach(p => {
    const q = (p.quadrant || 'neutral') as QuadrantLabel
    if (byQuadrant[q]) byQuadrant[q].push(p)
  })

  return {
    animation: false,
    tooltip: {
      trigger: 'item',
      confine: true,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      formatter: (params: any) => {
        const d = params?.data as any
        if (!d) return ''
        const p: ProjectQuadrantPoint = d.__raw || d
        const q = quadrantStyle[p.quadrant]?.name || p.quadrant
        const label = p.label ? `<div class="text-xs text-gray-500 mt-1">${p.label}</div>` : ''
        return `
          <div class="font-medium mb-1">${q}</div>
          <div class="text-xs text-gray-500">
            情感: ${Number(p.x).toFixed(2)}<br/>
            CII: ${Number(p.y).toFixed(2)}<br/>
            平台: ${p.platform || '-'}<br/>
            关键词: ${p.keyword || '-'}<br/>
            task/post: ${p.task_id}/${p.post_id}
          </div>
          ${label}
        `
      },
    },
    grid: { left: 40, right: 16, top: 16, bottom: 40 },
    xAxis: {
      type: 'value',
      name: '情感',
      min: -2,
      max: 2,
      axisLabel: { formatter: (v: number) => v.toFixed(1) },
    },
    yAxis: {
      type: 'value',
      name: 'CII',
      axisLabel: { formatter: (v: number) => v.toFixed(0) },
    },
    legend: {
      bottom: 0,
      data: (Object.keys(quadrantStyle) as QuadrantLabel[]).map(k => quadrantStyle[k].name),
    },
    series: (Object.keys(byQuadrant) as QuadrantLabel[]).map((q): any => ({
      name: quadrantStyle[q].name,
      type: 'scatter',
      symbolSize: 6,
      itemStyle: { color: quadrantStyle[q].color, opacity: 0.75 },
      data: byQuadrant[q].map(p => ({ value: [p.x, p.y], __raw: p })),
      markLine: avgCii
        ? {
          silent: true,
          lineStyle: { color: '#6b7280', type: 'dashed', opacity: 0.6 },
          data: [{ yAxis: avgCii }],
        }
        : undefined,
    })),
  }
}

const update = async () => {
  await nextTick()
  if (!chartRef.value) return
  let inst = getInstance()
  if (!inst) inst = initChart()
  setOption(buildOption())
}

watch(() => props.points, update, { deep: true })
watch(() => props.avgCii, update)

onMounted(() => update())
</script>

<template>
  <div class="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
    <div class="flex items-center justify-between mb-2">
      <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300">项目级四象限（全局阈值重算）</h3>
      <div class="text-xs text-gray-500 dark:text-gray-400">
        avg CII: {{ typeof avgCii === 'number' ? avgCii.toFixed(2) : '-' }}
      </div>
    </div>
    <div ref="chartRef" class="w-full h-80" />
  </div>
</template>


