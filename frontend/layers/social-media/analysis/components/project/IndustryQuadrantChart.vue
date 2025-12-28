<script setup lang="ts">
import { ref, watch, onMounted, nextTick } from 'vue'
import type { EChartsOption } from 'echarts'
import type { IndustryQuadrantPoint } from '../../../types/project-snapshot'
import TabSwitch from '../shared/TabSwitch.vue'

const props = defineProps<{
  data: IndustryQuadrantPoint[]
  selected?: string | null
}>()

const emit = defineEmits<{
  (e: 'select', item: IndustryQuadrantPoint): void
}>()

const { chartRef, initChart, setOption, getInstance, on } = useCharts()

type ScaleMode = 'linear' | 'log'
const scaleMode = ref<ScaleMode>('linear')

const scaleModeOptions = [
  { value: 'linear', label: '线性' },
  { value: 'log', label: '对数' },
]

// 角色颜色
const roleColors: Record<string, string> = {
  Target: '#10b981',
  Competitor: '#f59e0b',
  Context: '#94a3b8',
}

const regionColors = {
  positive: 'rgba(16, 185, 129, 0.12)',
  negative: 'rgba(239, 68, 68, 0.12)',
}

let indexByName: Record<string, { seriesIndex: number; dataIndex: number }> = {}

const formatCompactNumber = (n: number) => {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`
  if (n >= 10000) return `${(n / 10000).toFixed(1)}w`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return n.toFixed(0)
}

const median = (arr: number[]) => {
  if (!arr.length) return null
  const a = arr.slice().sort((x, y) => x - y)
  const mid = Math.floor(a.length / 2)
  if (a.length % 2 === 1) return a[mid] ?? null
  const left = a[mid - 1]
  const right = a[mid]
  if (left == null || right == null) return null
  return (left + right) / 2
}

// ECharts 配置
const getOption = (): EChartsOption => {
  const points = props.data || []
  if (!points.length) return {}

  // 用 mentions 做点大小（信息增益更高）
  const maxMentions = Math.max(...points.map(p => p.mentions || 0), 1)
  const heatValues = points.map(p => p.heat || 0).filter(x => x > 0)
  const maxHeat = Math.max(...heatValues, 1)
  const minPositiveHeat = heatValues.length ? Math.min(...heatValues) : 1
  const heatMid = median(heatValues)
  const labelNameSet = new Set(
    points
      .slice()
      .sort((a, b) => (b.heat || 0) - (a.heat || 0))
      .slice(0, 30)
      .map(p => p.name)
      .filter(Boolean)
  )
  const selectedName = (props.selected || '').toString().trim()
  if (selectedName) labelNameSet.add(selectedName)
  const truncateLabel = (s: string) => (s.length > 6 ? `${s.slice(0, 6)}…` : s)

  // 构建 series 数据（按 role 分组）
  const seriesData: Record<string, Array<[number, number, number, string, IndustryQuadrantPoint]>> = {
    Target: [],
    Competitor: [],
    Context: [],
  }

  for (const p of points) {
    const role = p.role || 'Context'
    const rawHeat = p.heat || 0
    // log 轴要求正数，<=0 的点压到一个最小值（避免丢失）
    const heat = scaleMode.value === 'log' ? Math.max(rawHeat, Math.max(minPositiveHeat, 0.1)) : rawHeat
    const sentiment = p.sentiment || 0
    const m = p.mentions || 0
    const size = Math.max(8, Math.min(34, 8 + Math.sqrt(m / maxMentions) * 26))
    seriesData[role]?.push([heat, sentiment, size, p.name, p])
  }

  indexByName = {}
  const series: unknown[] = []
  let seriesIndex = 0
  for (const [role, arr] of Object.entries(seriesData)) {
    if (!arr.length) continue
    arr.forEach((v, i) => {
      const name = v[3]
      if (name && !indexByName[name]) indexByName[name] = { seriesIndex, dataIndex: i }
    })
    series.push({
      name: role === 'Target' ? '主体' : role === 'Competitor' ? '竞品' : '行业实体',
      type: 'scatter',
      symbolSize: (val: number[]) => val[2] || 8,
      label: {
        show: true,
        distance: 2,
        color: '#6b7280',
        fontSize: 10,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        formatter: (p: any) => {
          const nm = (p?.data?.[3] || '').toString()
          if (!nm) return ''
          return labelNameSet.has(nm) ? truncateLabel(nm) : ''
        },
      },
      labelLayout: { hideOverlap: true, moveOverlap: 'shiftY' },
      itemStyle: {
        color: roleColors[role],
        opacity: 0.75,
      },
      emphasis: {
        label: {
          show: true,
          formatter: (p: { data: unknown[] }) => (Array.isArray(p.data) ? String((p.data[3] as string) || '') : ''),
          color: '#111827',
          backgroundColor: 'rgba(255,255,255,0.85)',
          borderRadius: 4,
          padding: [2, 6],
        },
        itemStyle: {
          opacity: 1,
          borderColor: '#111827',
          borderWidth: 1,
          shadowBlur: 10,
          shadowColor: roleColors[role],
        },
      },
      data: arr,
    })
    seriesIndex += 1
  }

  // 参考线：y=0 以及 x=heat 中位数（用于快速定位风险/护城河区）
  const markLineData: Array<Record<string, unknown>> = [
    { yAxis: 0 },
  ]
  if (typeof heatMid === 'number' && heatMid > 0) {
    markLineData.push({ xAxis: heatMid })
  }
  const highlightArea: Array<Array<Record<string, unknown>>> = []
  if (typeof heatMid === 'number' && heatMid > 0 && maxHeat > heatMid) {
    highlightArea.push([
      { xAxis: heatMid, yAxis: 0, itemStyle: { color: regionColors.positive } },
      { xAxis: maxHeat, yAxis: 1 },
    ])
    highlightArea.push([
      { xAxis: heatMid, yAxis: -1, itemStyle: { color: regionColors.negative } },
      { xAxis: maxHeat, yAxis: 0 },
    ])
  }
  if (series.length) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const s0 = series[0] as any
    s0.markLine = {
      symbol: 'none',
      silent: true,
      lineStyle: { color: '#e5e7eb', type: 'solid' },
      label: { show: false },
      data: markLineData,
    }
    if (highlightArea.length) {
      s0.markArea = {
        silent: true,
        data: highlightArea,
      }
    }
  }

  return {
    animation: false,
    tooltip: {
      trigger: 'item',
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      formatter: (params: any) => {
        const [heat, sentiment, , name, point] = params.data as [number, number, number, string, IndustryQuadrantPoint]
        const roleLabel = point.role === 'Target' ? '主体' : point.role === 'Competitor' ? '竞品' : '行业实体'
        const mentions = point.mentions || 0
        const eff = mentions > 0 ? (Number(point.heat || heat) / mentions) : 0
        return `
          <div style="font-weight:600;margin-bottom:4px">${name}</div>
          <div style="font-size:12px;color:#888">${roleLabel}</div>
          <div style="margin-top:6px">
            <div>热度：<b>${formatCompactNumber(Number(point.heat || heat))}</b></div>
            <div>情感：<b style="color:${sentiment >= 0 ? '#10b981' : '#ef4444'}">${sentiment.toFixed(2)}</b></div>
            <div>提及：<b>${mentions}</b></div>
            <div>效能：<b>${mentions > 0 ? eff.toFixed(1) : '-'}</b>x</div>
          </div>
        `
      },
    },
    legend: { show: false },
    grid: {
      left: 50,
      right: 20,
      top: 20,
      bottom: 50,
    },
    xAxis: {
      type: scaleMode.value === 'log' ? 'log' : 'value',
      logBase: 10,
      min: scaleMode.value === 'log' ? Math.max(minPositiveHeat, 0.1) : undefined,
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
          if (v >= 10000) return `${(v / 10000).toFixed(0)}w`
          if (v >= 1000) return `${(v / 1000).toFixed(0)}k`
          return v.toFixed(0)
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
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    series: series as any,
  }
}

const applyHighlight = () => {
  const instance = getInstance()
  if (!instance) return
  const s = (instance.getOption()?.series as unknown[]) || []
  for (let i = 0; i < s.length; i += 1) {
    instance.dispatchAction({ type: 'downplay', seriesIndex: i })
  }
  const selected = (props.selected || '').toString().trim()
  if (!selected) return
  const idx = indexByName[selected]
  if (!idx) return
  instance.dispatchAction({ type: 'highlight', seriesIndex: idx.seriesIndex, dataIndex: idx.dataIndex })
  instance.dispatchAction({ type: 'showTip', seriesIndex: idx.seriesIndex, dataIndex: idx.dataIndex })
}

const updateChart = async () => {
  await nextTick()
  const points = props.data || []
  if (chartRef.value && points.length) {
    let instance = getInstance()
    if (!instance) {
      instance = initChart()
      // 绑定点击事件
      on('click', (params: unknown) => {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const p = params as any
        if (p.data && p.data[4]) {
          emit('select', p.data[4] as IndustryQuadrantPoint)
        }
      })
    }
    setOption(getOption())
    applyHighlight()
  }
}

watch(() => props.data, updateChart, { deep: true })
watch(() => props.selected, () => applyHighlight())
watch(scaleMode, updateChart)

onMounted(() => {
  updateChart()
})
</script>

<template>
  <div class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 flex flex-col">
    <div class="flex items-center justify-between mb-3 shrink-0">
      <h3 class="text-sm font-semibold text-gray-900 dark:text-white">行业象限</h3>
      <div class="flex items-center gap-2">
        <TabSwitch v-model="scaleMode" :options="scaleModeOptions" />
        <span class="text-xs text-gray-500 dark:text-gray-400">热度 × 情感</span>
      </div>
    </div>

    <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-gray-500 dark:text-gray-400 mb-2">
      <span class="inline-flex items-center gap-1">
        <span class="w-2 h-2 rounded-full" :style="{ backgroundColor: roleColors.Target }" />
        主体
      </span>
      <span class="inline-flex items-center gap-1">
        <span class="w-2 h-2 rounded-full" :style="{ backgroundColor: roleColors.Competitor }" />
        竞品
      </span>
      <span class="inline-flex items-center gap-1">
        <span class="w-2 h-2 rounded-full" :style="{ backgroundColor: roleColors.Context }" />
        行业实体
      </span>
    </div>
    <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-gray-500 dark:text-gray-400 mb-1">
      <span class="inline-flex items-center gap-1">
        <span class="w-2.5 h-2.5 rounded-sm" :style="{ backgroundColor: regionColors.positive }" />
        高热正面（护城河）
      </span>
      <span class="inline-flex items-center gap-1">
        <span class="w-2.5 h-2.5 rounded-sm" :style="{ backgroundColor: regionColors.negative }" />
        高热负面（风险）
      </span>
      <span class="text-[10px] text-gray-400">仅高热区高亮</span>
    </div>

    <div v-if="data?.length" ref="chartRef" class="flex-1 min-h-72" />
    <div v-else class="flex-1 min-h-72 flex items-center justify-center text-sm text-gray-400">
      暂无行业象限数据
    </div>
  </div>
</template>
