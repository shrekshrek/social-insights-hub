<script setup lang="ts">
import { ref, watch, onMounted, nextTick } from 'vue'
import type { EChartsOption } from 'echarts'
import type { ContextGraph, ContextNode } from '../../types'

const props = defineProps<{
  data?: ContextGraph
}>()

const emit = defineEmits<{
  (e: 'click-node', title: string, postIds: number[]): void
}>()

const { chartRef, initChart, setOption, getInstance } = useCharts()

// 图例配置
const legendItems = [
  { key: 'center', label: '本品', color: 'bg-blue-500', chartColor: '#3b82f6' },
  { key: 'audience', label: '人群', color: 'bg-purple-500', chartColor: '#8b5cf6' },
  { key: 'scenario', label: '场景', color: 'bg-emerald-500', chartColor: '#10b981' },
  { key: 'feature', label: '优点', color: 'bg-green-500', chartColor: '#22c55e' },
  { key: 'issue', label: '问题', color: 'bg-red-500', chartColor: '#ef4444' },
  { key: 'competitor', label: '竞品', color: 'bg-orange-500', chartColor: '#f97316' },
  { key: 'topic', label: '话题', color: 'bg-amber-500', chartColor: '#f59e0b' },
]

// 类别可见性状态（默认全部显示）
const visibleCategories = ref<Set<string>>(new Set(legendItems.map(l => l.key)))

// 切换类别显示
const toggleCategory = (key: string) => {
  if (key === 'center') return // 中心节点不可隐藏
  
  const newSet = new Set(visibleCategories.value)
  if (newSet.has(key)) {
    newSet.delete(key)
  } else {
    newSet.add(key)
  }
  visibleCategories.value = newSet
  updateChart()
}

// 节点类型颜色映射
const typeColorMap: Record<string, string> = {
  audience: '#8b5cf6',   // 紫色 - 人群
  scenario: '#10b981',   // 绿色 - 场景
  feature: '#22c55e',    // 亮绿 - 产品优点
  issue: '#ef4444',      // 红色 - 产品问题
  competitor: '#f97316', // 橙色 - 竞品
  topic: '#f59e0b',      // 琥珀色 - 话题（默认）
}

const getOption = (): EChartsOption => {
  if (!props.data) return {}

  const { center_node, nodes, edges } = props.data
  
  // 用于去重的节点名称集合
  const addedNodeNames = new Set<string>()
  
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
  addedNodeNames.add(center_node)
  
  // 周边节点（根据可见性过滤，并进行去重）
  nodes.forEach(node => {
    if (!visibleCategories.value.has(node.type)) return
    
    // 跳过已存在的节点名称（防止重复）
    if (addedNodeNames.has(node.name)) return
    addedNodeNames.add(node.name)
    
    chartNodes.push({
      // 附加数据用于点击
      ...node,
      symbolSize: 20 + (node.weight * 20), // 根据权重调整大小
      itemStyle: {
        color: typeColorMap[node.type] || '#f59e0b'
      },
      label: { show: true, position: 'right' },
      category: node.type
    })
  })
  
  // 过滤边（只保留可见节点的边）
  const visibleNodeNames = new Set(chartNodes.map(n => n.name))
  const filteredEdges = edges.filter(e => 
    visibleNodeNames.has(e.source) && visibleNodeNames.has(e.target)
  )

  return {
    animation: false,  // 关闭动画，避免 resize 时的问题
    tooltip: {
      trigger: 'item',
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      formatter: (params: any) => {
        if (params.dataType === 'edge') return ''
        const node = params.data
        if (node.category === 'center') return `<div class="font-medium">${node.name}</div>`
        
        // 节点类型中文映射
        const typeLabelMap: Record<string, string> = {
          audience: '人群',
          scenario: '场景',
          feature: '产品优点',
          issue: '产品问题',
          competitor: '竞品',
          topic: '话题',
        }
        
        return `
          <div class="font-medium mb-1">${node.name}</div>
          <div class="text-xs text-gray-500">
            类型: ${typeLabelMap[node.type] || '其他'} <br/>
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
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        data: chartNodes as any[],
        links: filteredEdges.map(e => ({
          source: e.source,
          target: e.target,
          value: e.value,
          lineStyle: {
            width: 1 + e.value * 5,
            opacity: 0.6
          }
        })),
        // 禁用滚轮缩放，仅保留拖拽平移
        roam: 'move',
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
// eslint-disable-next-line @typescript-eslint/no-explicit-any
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
    <!-- 标题 + slot (全部/推广/有机按钮) -->
    <div class="flex items-center gap-3 mb-4">
      <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300">关联网络</h3>
      <slot />
    </div>

    <!-- 图表 -->
    <div ref="chartRef" class="w-full h-80" />

    <!-- 图例 - 底部居中 -->
    <div class="flex justify-center gap-2 text-xs mt-3">
      <button
        v-for="item in legendItems"
        :key="item.key"
        class="flex items-center gap-1 px-1.5 py-0.5 rounded transition-all"
        :class="[
          visibleCategories.has(item.key)
            ? 'opacity-100'
            : 'opacity-40 line-through',
          item.key === 'center' ? 'cursor-default' : 'cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700'
        ]"
        @click="toggleCategory(item.key)"
      >
        <span class="w-2 h-2 rounded-full" :class="item.color" />
        <span class="text-gray-500">{{ item.label }}</span>
      </button>
    </div>
  </div>
</template>

