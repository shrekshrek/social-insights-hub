<script setup lang="ts">
/**
 * 时间分布图表组件
 * 
 * 展示内容发布时间分布的折线图
 */
import { watch, onMounted, nextTick } from 'vue'
import type { EChartsOption } from 'echarts'

interface TimeDistributionItem {
  date: string
  count: number
  post_ids?: number[]
}

const props = defineProps<{
  data: TimeDistributionItem[]
  skippedCount?: number  // 无发布时间的帖子数
}>()

const emit = defineEmits<{
  (e: 'click-date', date: string, postIds: number[]): void
}>()

const { chartRef, initChart, setOption, getInstance } = useCharts()

const getOption = (): EChartsOption => {
  const dist = props.data || []
  if (dist.length === 0) return {}
  
  return {
    animation: false,
    tooltip: {
      trigger: 'item',
      confine: true,
      // backgroundColor: 'rgba(255, 255, 255, 0.95)',
      // borderColor: '#e5e7eb',
      borderWidth: 1,
      padding: [8, 12],
      textStyle: { color: '#374151', fontSize: 12 },
      formatter: (params: unknown) => {
        const p = params as { name: string; value: number; dataIndex: number }
        if (!p) return ''
        const fullDate = dist[p.dataIndex]?.date || p.name
        return `<div style="font-weight: 500; margin-bottom: 4px;">${fullDate}</div>
                <div>发布数量: <span style="color: #3b82f6; font-weight: 600;">${p.value}</span> 条</div>`
      }
    },
    grid: {
      left: '10px',
      right: '10px',
      bottom: '0px',
      top: '10px',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: dist.map(i => i.date.slice(5)),  // 只显示 MM-DD
      axisLabel: {
        rotate: 45,
        fontSize: 10,
        color: '#9ca3af'
      },
      axisLine: { lineStyle: { color: '#e5e7eb' } }
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#f3f4f6', type: 'dashed' } },
      axisLabel: { fontSize: 10, color: '#9ca3af' }
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
        itemStyle: { shadowBlur: 10, shadowColor: 'rgba(59, 130, 246, 0.5)' }
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
            { offset: 1, color: 'rgba(59, 130, 246, 0.05)' }
          ]
        }
      }
    }]
  }
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
      setOption(option)
    }
  }
}

watch(() => props.data, updateChart, { deep: true })

onMounted(() => {
  updateChart()
})

// 计算统计信息
const totalDays = computed(() => props.data?.length || 0)
const totalCount = computed(() => props.data?.reduce((sum, i) => sum + i.count, 0) || 0)
</script>

<template>
  <div class="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
    <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">内容发布时间分布</h3>
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

