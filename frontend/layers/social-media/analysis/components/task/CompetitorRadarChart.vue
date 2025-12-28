<script setup lang="ts">
import { watch, onMounted, nextTick } from 'vue'
import type { EChartsOption } from 'echarts'
import type { CompetitorRadar } from '../../types'

const props = defineProps<{
  data?: CompetitorRadar
}>()

const { chartRef, initChart, setOption, getInstance } = useCharts()

// 品牌固定颜色（第一个是本品蓝色，后面是竞品颜色）
const BRAND_COLORS = [
  '#3b82f6', // 蓝色 - 本品
  '#22c55e', // 绿色 - 竞品1
  '#f59e0b', // 橙色 - 竞品2
  '#ef4444', // 红色 - 竞品3
  '#8b5cf6', // 紫色 - 竞品4
  '#06b6d4', // 青色 - 竞品5
]

const getOption = (): EChartsOption => {
  if (!props.data || props.data.mode === 'none') return {}

  if (props.data.mode === 'radar') {
    const { dimensions = [], series = [] } = props.data
    
    // 构建产品列表映射用于 tooltip
    const productsMap: Record<string, string[]> = {}
    series.forEach(s => {
      productsMap[s.name] = s.products || []
    })
    
    return {
      animation: false,  // 关闭动画，避免 resize 时的问题
      tooltip: {
        trigger: 'item',
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        formatter: (params: any) => {
          const name = params.name || ''
          const products = productsMap[name] || []
          const values = params.value || []
          
          let html = `<div class="font-medium mb-2">${name}</div>`
          
          // 如果有多个产品，显示产品列表
          if (products.length > 1) {
            html += `<div class="text-xs text-gray-400 mb-2">包含: ${products.join(', ')}</div>`
          }
          
          // 显示各维度数值
          dimensions.forEach((dim, i) => {
            const val = values[i] !== undefined ? (values[i] * 100).toFixed(0) : '-'
            html += `<div class="text-xs">${dim}: ${val}%</div>`
          })
          
          return html
        }
      },
      legend: {
        bottom: 0,
        data: series.map(s => s.name),
        selectedMode: 'multiple' // 支持多选切换
      },
      radar: {
        indicator: dimensions.map(d => ({ name: d, max: 1 })),
        radius: '75%'
      },
      // 每个品牌作为独立的 series，使用固定颜色
      series: series.map((s, index) => ({
        type: 'radar',
        name: s.name,
        lineStyle: {
          color: BRAND_COLORS[index % BRAND_COLORS.length],
          width: 2
        },
        itemStyle: {
          color: BRAND_COLORS[index % BRAND_COLORS.length]
        },
        areaStyle: {
          color: BRAND_COLORS[index % BRAND_COLORS.length],
          opacity: 0.1
        },
        data: [{
          value: s.data,
          name: s.name
        }]
      }))
    }
  } else {
    // Bar Mode (Sentiment comparison)
    const { series = [] } = props.data
    // 假设 series 只有两个（本品 vs 竞品）
    // 展示 正面/中性/负面 占比
    const categories = ['正面', '中性', '负面']
    
    // 构建产品列表映射用于 tooltip
    const productsMap: Record<string, string[]> = {}
    series.forEach(s => {
      productsMap[s.name] = s.products || []
    })
    
    const barSeries = series.map((s, index) => {
      const dist = s.sentiment_distribution || { positive: 0, neutral: 0, negative: 0 }
      const total = (dist.positive + dist.neutral + dist.negative) || 1
      return {
        name: s.name,
        type: 'bar',
        stack: s.name, // 不堆叠，分组展示
        itemStyle: {
          color: BRAND_COLORS[index % BRAND_COLORS.length]
        },
        data: [
          (dist.positive / total),
          (dist.neutral / total),
          (dist.negative / total)
        ].map(v => parseFloat((v * 100).toFixed(1)))
      }
    })

    return {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        formatter: (params: any) => {
          if (!Array.isArray(params) || params.length === 0) return ''
          
          const category = params[0].axisValue
          let html = `<div class="font-medium mb-2">${category}</div>`
          
          params.forEach((p: { seriesName: string; value: number; color: string }) => {
            const products = productsMap[p.seriesName] || []
            const productInfo = products.length > 1 ? ` (${products.length}个产品)` : ''
            html += `
              <div class="flex items-center gap-2 text-xs">
                <span style="background:${p.color};width:8px;height:8px;border-radius:50%;display:inline-block;"></span>
                <span>${p.seriesName}${productInfo}: ${p.value}%</span>
              </div>
            `
          })
          
          return html
        }
      },
      legend: {
        bottom: 0,
        selectedMode: 'multiple' // 支持多选切换
      },
      grid: {
        top: 30,
        right: 10,
        bottom: 30,
        left: 10,
        containLabel: true
      },
      xAxis: {
        type: 'category',
        data: categories
      },
      yAxis: {
        type: 'value',
        axisLabel: { formatter: '{value}%' }
      },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      series: barSeries as any
    }
  }
}

const updateChart = async () => {
  await nextTick()
  if (chartRef.value && props.data) {
    let instance = getInstance()
    if (!instance) {
      instance = initChart()
    }
    // 不使用 notMerge，保持 legend 选中状态
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
      <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300">
        {{ data?.mode === 'radar' ? '竞品雷达 (多维对比)' : '竞品情感对比' }}
      </h3>
    </div>
    <div ref="chartRef" class="w-full h-80" />
  </div>
</template>

