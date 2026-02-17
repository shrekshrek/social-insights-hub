<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from 'vue'
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

// 品牌图例可见性状态（默认全部显示）
const visibleBrands = ref<Set<string>>(new Set())

// 从 data 计算图例项
const brandLegendItems = computed(() => {
  if (!props.data || props.data.mode === 'none') return []
  return (props.data.series || []).map((s, index) => ({
    name: s.name,
    color: BRAND_COLORS[index % BRAND_COLORS.length],
  }))
})

// 切换品牌显示
const toggleBrand = (name: string) => {
  const newSet = new Set(visibleBrands.value)
  if (newSet.has(name)) {
    newSet.delete(name)
  } else {
    newSet.add(name)
  }
  visibleBrands.value = newSet
  updateChart()
}

// 当数据变化时重置可见性（新品牌默认全部显示）
watch(() => props.data?.series, (newSeries) => {
  if (newSeries) {
    visibleBrands.value = new Set(newSeries.map(s => s.name))
  }
}, { immediate: true })

const getOption = (): EChartsOption => {
  if (!props.data || props.data.mode === 'none') return {}

  const { series = [] } = props.data

  // 构建产品列表映射和 spam 分布映射用于 tooltip
  const productsMap: Record<string, string[]> = {}
  const spamMap: Record<string, CompetitorRadar['series'][0]['spam_distribution']> = {}
  series.forEach(s => {
    productsMap[s.name] = s.products || []
    spamMap[s.name] = s.spam_distribution ?? undefined
  })

  if (props.data.mode === 'radar') {
    const { dimensions = [] } = props.data

    // 按可见性过滤 series
    const visibleSeries = series
      .map((s, index) => ({ ...s, originalIndex: index }))
      .filter(s => visibleBrands.value.has(s.name))

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

          // spam 分布信息 (4D: 高/低广告 × 原文/评论)
          const sd = spamMap[name]
          if (sd?.high_spam && sd?.low_spam && (sd.high_spam.total > 0 || sd.low_spam.total > 0)) {
            html += `<div class="text-xs mt-1"><span style="color:#f59e0b;">推广 ${sd.high_spam.total} (原${sd.high_spam.post}/评${sd.high_spam.comment})</span> / <span style="color:#22c55e;">有机 ${sd.low_spam.total} (原${sd.low_spam.post}/评${sd.low_spam.comment})</span></div>`
          }

          return html
        }
      },
      radar: {
        center: ['50%', '50%'],
        indicator: dimensions.map(d => ({ name: d, max: 1 })),
        radius: '75%'
      },
      // 每个品牌作为独立的 series，使用固定颜色（按可见性过滤）
      series: visibleSeries.map(s => ({
        type: 'radar',
        name: s.name,
        lineStyle: {
          color: BRAND_COLORS[s.originalIndex % BRAND_COLORS.length],
          width: 2
        },
        itemStyle: {
          color: BRAND_COLORS[s.originalIndex % BRAND_COLORS.length]
        },
        areaStyle: {
          color: BRAND_COLORS[s.originalIndex % BRAND_COLORS.length],
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
    const categories = ['正面', '中性', '负面']

    // 按可见性过滤 series
    const visibleSeries = series
      .map((s, index) => ({ ...s, originalIndex: index }))
      .filter(s => visibleBrands.value.has(s.name))

    const barSeries = visibleSeries.map(s => {
      const dist = s.sentiment_distribution || { positive: 0, neutral: 0, negative: 0 }
      const total = (dist.positive + dist.neutral + dist.negative) || 1
      return {
        name: s.name,
        type: 'bar',
        stack: s.name, // 不堆叠，分组展示
        itemStyle: {
          color: BRAND_COLORS[s.originalIndex % BRAND_COLORS.length]
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
            const sd = spamMap[p.seriesName]
            const spamInfo = sd?.high_spam && sd?.low_spam && (sd.high_spam.total > 0 || sd.low_spam.total > 0)
              ? ` <span style="color:#f59e0b;">推广${sd.high_spam.total}(原${sd.high_spam.post}/评${sd.high_spam.comment})</span>/<span style="color:#22c55e;">有机${sd.low_spam.total}(原${sd.low_spam.post}/评${sd.low_spam.comment})</span>`
              : ''
            html += `
              <div class="flex items-center gap-2 text-xs">
                <span style="background:${p.color};width:8px;height:8px;border-radius:50%;display:inline-block;"></span>
                <span>${p.seriesName}${productInfo}: ${p.value}%${spamInfo}</span>
              </div>
            `
          })

          return html
        }
      },
      grid: {
        top: 30,
        right: 10,
        bottom: 10,
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
    // 使用 notMerge 确保 series 数量变化时正确更新（图例切换场景）
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
      <div class="flex items-center gap-3">
        <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300">
          {{ data?.mode === 'radar' ? '竞品雷达 (多维对比)' : '竞品情感对比' }}
        </h3>
        <slot />
      </div>
    </div>
    <!-- 图表 -->
    <div ref="chartRef" class="w-full h-80" />

    <!-- 图例 - 底部居中（与 ContextGraphChart 一致，放在 chart 外部） -->
    <div v-if="brandLegendItems.length > 1" class="flex flex-wrap justify-center gap-x-2 gap-y-1 text-xs mt-3">
      <button
        v-for="item in brandLegendItems"
        :key="item.name"
        class="flex items-center gap-1 px-1.5 py-0.5 rounded whitespace-nowrap transition-all cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700"
        :class="visibleBrands.has(item.name) ? 'opacity-100' : 'opacity-40 line-through'"
        @click="toggleBrand(item.name)"
      >
        <span class="w-2 h-2 shrink-0 rounded-full" :style="{ backgroundColor: item.color }" />
        <span class="text-gray-500">{{ item.name }}</span>
      </button>
    </div>
  </div>
</template>

