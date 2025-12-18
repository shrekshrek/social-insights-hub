<script setup lang="ts">
import { onMounted, watch, nextTick } from 'vue'
import type { EChartsOption } from 'echarts'

export interface ProjectEntityGraphNode {
  id: string
  name: string
  role?: string
  type?: string
  mentions: number
  heat: number
  score: number
  platform_distribution?: Record<string, number>
  keyword_distribution?: Record<string, number>
}

export interface ProjectEntityGraphEdge {
  source: string
  target: string
  co_occurrence: number
  jaccard: number
  value: number
  platform_distribution?: Record<string, number>
  keyword_distribution?: Record<string, number>
}

export interface ProjectEntityGraphData {
  nodes: ProjectEntityGraphNode[]
  edges: ProjectEntityGraphEdge[]
  params?: {
    top_n?: number
    min_co_occurrence?: number
  }
}

const props = defineProps<{
  data?: ProjectEntityGraphData
}>()

const { chartRef, initChart, setOption, getInstance } = useCharts()

const roleColorMap: Record<string, string> = {
  target: '#3b82f6',
  competitor: '#f97316',
  other: '#9ca3af',
  unknown: '#9ca3af',
}

const buildOption = (): EChartsOption => {
  const nodes = props.data?.nodes || []
  const edges = props.data?.edges || []
  const idToName = new Map(nodes.map(n => [n.id, n.name]))
  const MAX_EDGES = 120
  const edgesToShow = edges.slice(0, MAX_EDGES)

  const maxMentions = Math.max(...nodes.map(n => n.mentions || 0), 1)

  const chartNodes = nodes.map(n => ({
    ...n,
    name: n.name,
    symbolSize: 14 + (26 * (n.mentions / maxMentions)),
    itemStyle: { color: roleColorMap[(n.role || 'other').toLowerCase()] || '#9ca3af' },
    label: { show: true, position: 'right', fontSize: 10 },
  }))

  const chartEdges = edgesToShow.map(e => ({
    ...e,
    lineStyle: {
      width: Math.min(6, 1 + e.co_occurrence),
      opacity: 0.55,
    },
  }))

  return {
    animation: false,
    tooltip: {
      trigger: 'item',
      confine: true,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      formatter: (params: any) => {
        if (params.dataType === 'edge') {
          const e = params.data as ProjectEntityGraphEdge
          const sourceName = idToName.get(e.source) || e.source
          const targetName = idToName.get(e.target) || e.target
          const pDist = e.platform_distribution ? Object.entries(e.platform_distribution).sort((a, b) => (b[1] || 0) - (a[1] || 0)).slice(0, 3).map(([k, v]) => `${k}:${v}`).join('，') : '-'
          const kDist = e.keyword_distribution ? Object.entries(e.keyword_distribution).sort((a, b) => (b[1] || 0) - (a[1] || 0)).slice(0, 3).map(([k, v]) => `${k}:${v}`).join('，') : '-'
          return `
            <div class="font-medium mb-1">${sourceName} ↔ ${targetName}</div>
            <div class="text-xs text-gray-500">
              共现: ${e.co_occurrence}<br/>
              Jaccard: ${Number(e.jaccard).toFixed(3)}<br/>
              平台: ${pDist}<br/>
              关键词: ${kDist}
            </div>
          `
        }
        const n = params.data as ProjectEntityGraphNode
        const pDist = n.platform_distribution ? Object.entries(n.platform_distribution).sort((a, b) => (b[1] || 0) - (a[1] || 0)).slice(0, 3).map(([k, v]) => `${k}:${v}`).join('，') : '-'
        const kDist = n.keyword_distribution ? Object.entries(n.keyword_distribution).sort((a, b) => (b[1] || 0) - (a[1] || 0)).slice(0, 3).map(([k, v]) => `${k}:${v}`).join('，') : '-'
        return `
          <div class="font-medium mb-1">${n.name}</div>
          <div class="text-xs text-gray-500">
            role/type: ${(n.role || '-')}/${(n.type || '-')}<br/>
            mentions: ${n.mentions}<br/>
            平台: ${pDist}<br/>
            关键词: ${kDist}
          </div>
        `
      },
    },
    series: [
      {
        type: 'graph',
        layout: 'force',
        roam: 'move',
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        data: chartNodes as any[],
        links: chartEdges,
        force: {
          repulsion: 240,
          edgeLength: [60, 120],
        },
      },
    ],
  }
}

const update = async () => {
  await nextTick()
  if (!chartRef.value) return
  let inst = getInstance()
  if (!inst) inst = initChart()
  setOption(buildOption())
}

watch(() => props.data, update, { deep: true })
onMounted(() => update())
</script>

<template>
  <div class="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
    <div class="flex items-center justify-between mb-2">
      <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300">项目级实体共现网络（TopN + 阈值）</h3>
      <div class="text-xs text-gray-500 dark:text-gray-400">
        <span v-if="data?.params?.top_n">Top {{ data.params.top_n }}</span>
        <span v-if="data?.params?.min_co_occurrence"> / min co={{ data.params.min_co_occurrence }}</span>
      </div>
    </div>
    <div ref="chartRef" class="w-full h-80" />
  </div>
</template>


