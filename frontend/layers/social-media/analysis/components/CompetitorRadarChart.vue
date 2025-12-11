<script setup lang="ts">
import { watch, onMounted, nextTick, ref } from 'vue'
import type { EChartsOption } from 'echarts'
import type { CompetitorRadar } from '../types'

const props = defineProps<{
  data?: CompetitorRadar
}>()

const { chartRef, initChart, setOption, getInstance } = useCharts()

const getOption = (): EChartsOption => {
  if (!props.data || props.data.mode === 'none') return {}

  if (props.data.mode === 'radar') {
    const { dimensions = [], series = [] } = props.data
    return {
      tooltip: {
        trigger: 'item'
      },
      legend: {
        bottom: 0,
        data: series.map(s => s.name)
      },
      radar: {
        indicator: dimensions.map(d => ({ name: d, max: 1 })),
        radius: '65%'
      },
      series: [
        {
          type: 'radar',
          data: series.map(s => ({
            value: s.data,
            name: s.name
          }))
        }
      ]
    }
  } else {
    // Bar Mode (Sentiment comparison)
    const { series = [] } = props.data
    // 假设 series 只有两个（本品 vs 竞品）
    // 展示 正面/中性/负面 占比
    const categories = ['正面', '中性', '负面']
    const barSeries = series.map(s => {
      const dist = s.sentiment_distribution || { positive: 0, neutral: 0, negative: 0 }
      const total = (dist.positive + dist.neutral + dist.negative) || 1
      return {
        name: s.name,
        type: 'bar',
        stack: s.name, // 不堆叠，分组展示
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
        axisPointer: { type: 'shadow' }
      },
      legend: {
        bottom: 0
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
    setOption(getOption(), { notMerge: true })
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
    <div ref="chartRef" class="w-full h-64"></div>
  </div>
</template>

