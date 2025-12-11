<script setup lang="ts">
import { watch, onMounted, nextTick, ref } from 'vue'
import type { EChartsOption } from 'echarts'
import type { ContextGraph, ContextNode } from '../types'

const props = defineProps<{
  data?: ContextGraph
}>()

const emit = defineEmits<{
  (e: 'click-node', title: string, postIds: number[]): void
}>()

const { chartRef, initChart, setOption, getInstance } = useCharts()

const getOption = (): EChartsOption => {
  if (!props.data) return {}

  const { center_node, nodes, edges } = props.data
  
  // 转换节点
  // 中心节点
  const chartNodes = [
    {
      name: center_node,
      symbolSize: 40,
      itemStyle: { color: '#3b82f6' },
      label: { show: true, position: 'bottom' },
      category: 'center'
    }
  ]
  
  // 周边节点
  nodes.forEach(node => {
    chartNodes.push({
      name: node.name,
      symbolSize: 20 + (node.weight * 20), // 根据权重调整大小
      itemStyle: {
        color: node.type === 'audience' ? '#8b5cf6' : node.type === 'scenario' ? '#10b981' : '#f59e0b'
      },
      label: { show: true, position: 'right' },
      category: node.type,
      // 附加数据用于点击
      ...node
    })
  })

  return {
    tooltip: {
      trigger: 'item',
      formatter: (params: any) => {
        if (params.dataType === 'edge') return ''
        const node = params.data
        if (node.category === 'center') return `<div class="font-medium">${node.name}</div>`
        
        return `
          <div class="font-medium mb-1">${node.name}</div>
          <div class="text-xs text-gray-500">
            类型: ${node.type === 'audience' ? '人群' : node.type === 'scenario' ? '场景' : '话题'} <br/>
            关联度: ${(node.weight * 100).toFixed(1)}% <br/>
            共现次数: ${node.co_occurrence}
          </div>
        `
      }
    },
    series: [
      {
        type: 'graph',
        layout: 'force',
        data: chartNodes,
        links: edges.map(e => ({
          source: e.source,
          target: e.target,
          value: e.value,
          lineStyle: {
            width: 1 + e.value * 5,
            opacity: 0.6
          }
        })),
        roam: true,
        label: {
          show: true,
          fontSize: 10
        },
        force: {
          repulsion: 200,
          edgeLength: [50, 100]
        }
      }
    ]
  }
}

// 点击处理
const handleClick = (params: any) => {
  if (params.dataType === 'node' && params.data.category !== 'center') {
    const node = params.data as ContextNode
    if (node && node.post_ids?.length) {
      emit('click-node', `${node.name} (关联内容)`, node.post_ids)
    }
  }
}

const updateChart = async () => {
  await nextTick()
  if (chartRef.value && props.data) {
    let instance = getInstance()
    if (!instance) {
      instance = initChart()
      instance?.on('click', handleClick)
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
  <div class="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
    <div class="flex items-center justify-between mb-4">
      <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300">关联网络 (人-货-场)</h3>
      <div class="flex gap-2 text-xs">
        <div class="flex items-center gap-1">
          <span class="w-2 h-2 rounded-full bg-blue-500"></span>
          <span class="text-gray-500">本品</span>
        </div>
        <div class="flex items-center gap-1">
          <span class="w-2 h-2 rounded-full bg-purple-500"></span>
          <span class="text-gray-500">人群</span>
        </div>
        <div class="flex items-center gap-1">
          <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
          <span class="text-gray-500">场景</span>
        </div>
        <div class="flex items-center gap-1">
          <span class="w-2 h-2 rounded-full bg-amber-500"></span>
          <span class="text-gray-500">话题</span>
        </div>
      </div>
    </div>
    <div ref="chartRef" class="w-full h-64"></div>
  </div>
</template>

