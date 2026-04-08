<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import type { EChartsOption } from 'echarts'
import type { IndustryQuadrantPoint } from '../../../types/monitor-slice'
import TabSwitch from '../shared/TabSwitch.vue'

interface GroupShareItemForQuadrant {
  name: string
  heat: number
  organic_heat?: number
  promo_heat?: number
  mentions: number
  role?: string
  sentiment?: number
  organic_sentiment?: number
  promo_sentiment?: number
  spam_distribution?: {
    high_spam: { total: number; post: number; comment: number }
    low_spam: { total: number; post: number; comment: number }
  }
  source_tasks?: Array<{ task_id: number; mentions: number }>
  post_ids_sample?: Array<{ task_id: number; post_id: number }>
}

const props = defineProps<{
  data: IndustryQuadrantPoint[]
  groupData?: GroupShareItemForQuadrant[]
  selected?: string | null
}>()

const emit = defineEmits<{
  (e: 'select', item: IndustryQuadrantPoint): void
}>()

const { chartRef, initChart, setOption, getInstance, on } = useCharts()

// ==================== 缩放模式 ====================

type ScaleMode = 'linear' | 'log'
const scaleMode = ref<ScaleMode>('linear')

const scaleModeOptions = [
  { value: 'linear', label: '线性' },
  { value: 'log', label: '对数' },
]

// ==================== 象限视图模式 ====================

type QuadrantViewMode = 'all' | 'organic' | 'promo'
const quadrantViewMode = ref<QuadrantViewMode>('all')

const quadrantViewOptions = [
  { value: 'all', label: '全量' },
  { value: 'promo', label: '推广' },
  { value: 'organic', label: '有机' },
]

// ==================== 聚合模式 ====================

type AggregateMode = 'entity' | 'brand'
const aggregateMode = ref<AggregateMode>('entity')

const aggregateModeOptions = [
  { value: 'entity', label: '个体' },
  { value: 'brand', label: '品牌' },
]

const hasGroupData = computed(() => (props.groupData || []).length > 0)

/** 当前生效的数据源 */
const effectiveItems = computed<IndustryQuadrantPoint[]>(() => {
  if (aggregateMode.value === 'brand' && hasGroupData.value) {
    return (props.groupData || []).filter(g => g.mentions > 0).map(g => ({
      name: g.name,
      role: g.role,
      heat: g.heat,
      organic_heat: g.organic_heat,
      promo_heat: g.promo_heat,
      sentiment: g.sentiment ?? 0,
      organic_sentiment: g.organic_sentiment,
      promo_sentiment: g.promo_sentiment,
      mentions: g.mentions,
      spam_distribution: g.spam_distribution,
      source_tasks: g.source_tasks,
      post_ids_sample: g.post_ids_sample,
    }))
  }
  return props.data || []
})

// ==================== 能力检测 ====================

const items = computed(() => effectiveItems.value)

/** 是否有 spam 分布数据（决定是否显示视图切换） */
const hasSpamData = computed(() =>
  items.value.some(p => p.spam_distribution != null),
)

// ==================== 角色与样式 ====================

const roleColors: Record<string, string> = {
  Target: '#10b981',
  Competitor: '#f59e0b',
  Context: '#94a3b8',
}

const regionColors = {
  positive: 'rgba(16, 185, 129, 0.12)',
  negative: 'rgba(239, 68, 68, 0.12)',
}

// ==================== 视图数值计算 ====================

interface PointDisplayValues {
  /** X 轴：全量→热度，有机→有机热度，推广→推广热度 */
  xVal: number
  /** Y 轴：全量→总体情感，有机→有机情感，推广→推广情感 */
  yVal: number
  /** true 时 Y 使用总体情感作为 fallback（暂无分层精确值） */
  isFallback: boolean
}

const getPointDisplayValues = (p: IndustryQuadrantPoint): PointDisplayValues => {
  if (quadrantViewMode.value === 'all') {
    return { xVal: p.heat || 0, yVal: p.sentiment || 0, isFallback: false }
  }

  const sd = p.spam_distribution

  if (quadrantViewMode.value === 'organic') {
    const xVal = p.organic_heat ?? (sd ? sd.low_spam.total : (p.mentions || 0))
    const yVal = p.organic_sentiment ?? p.sentiment ?? 0
    return { xVal, yVal, isFallback: p.organic_sentiment == null }
  }

  // promo
  const xVal = p.promo_heat ?? (sd ? sd.high_spam.total : (p.mentions || 0))
  const yVal = p.promo_sentiment ?? p.sentiment ?? 0
  return { xVal, yVal, isFallback: p.promo_sentiment == null }
}

// ==================== 辅助函数 ====================

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

// ==================== ECharts 索引（用于高亮） ====================

let indexByName: Record<string, { seriesIndex: number; dataIndex: number }> = {}

// ==================== ECharts 配置 ====================

const getOption = (): EChartsOption => {
  const points = items.value
  if (!points.length) return {}

  // 计算各点在当前视图下的显示值
  const displayVals = points.map(p => getPointDisplayValues(p))

  // X 轴数值范围（用于对数轴和中位参考线）
  const xValues = displayVals.map(v => v.xVal).filter(x => x > 0)
  const maxX = Math.max(...xValues, 1)
  const minPositiveX = xValues.length ? Math.min(...xValues) : 1
  const xMid = median(xValues)

  // 点大小仍用 mentions（保持跨模式一致的视觉权重）
  const maxMentions = Math.max(...points.map(p => p.mentions || 0), 1)

  // 显示 label 的 top N（按当前视角有效热度排序，与散点 X 轴一致）
  const labelNameSet = new Set(
    points
      .map((p, i) => ({ name: p.name, xVal: displayVals[i]?.xVal ?? 0 }))
      .sort((a, b) => b.xVal - a.xVal)
      .slice(0, 30)
      .map(({ name }) => name)
      .filter(Boolean),
  )
  const selectedName = (props.selected || '').toString().trim()
  if (selectedName) labelNameSet.add(selectedName)
  const truncateLabel = (s: string) => (s.length > 6 ? `${s.slice(0, 6)}…` : s)

  // 按 role 分组构建 series
  const seriesData: Record<string, Array<[number, number, number, string, IndustryQuadrantPoint]>> = {
    Target: [],
    Competitor: [],
    Context: [],
  }

  for (let i = 0; i < points.length; i++) {
    const p = points[i]!
    const role = p.role || 'Context'
    const { xVal: rawX, yVal } = displayVals[i]!
    const xVal = scaleMode.value === 'log' ? Math.max(rawX, Math.max(minPositiveX, 0.1)) : rawX
    const m = p.mentions || 0
    const size = Math.max(8, Math.min(34, 8 + Math.sqrt(m / maxMentions) * 26))
    seriesData[role]?.push([xVal, yVal, size, p.name, p])
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
        color: roleColors[role] || '#94a3b8',
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
          shadowColor: roleColors[role] || '#94a3b8',
        },
      },
      data: arr,
    })
    seriesIndex += 1
  }

  // 参考线：y=0 + x=中位数
  const markLineData: Array<Record<string, unknown>> = [{ yAxis: 0 }]
  if (typeof xMid === 'number' && xMid > 0) {
    markLineData.push({ xAxis: xMid })
  }
  const highlightArea: Array<Array<Record<string, unknown>>> = []
  if (typeof xMid === 'number' && xMid > 0 && maxX > xMid) {
    highlightArea.push([
      { xAxis: xMid, yAxis: 0, itemStyle: { color: regionColors.positive } },
      { xAxis: maxX, yAxis: 1 },
    ])
    highlightArea.push([
      { xAxis: xMid, yAxis: -1, itemStyle: { color: regionColors.negative } },
      { xAxis: maxX, yAxis: 0 },
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
      s0.markArea = { silent: true, data: highlightArea }
    }
  }

  const viewSuffix = quadrantViewMode.value === 'organic' ? '·有机' : quadrantViewMode.value === 'promo' ? '·推广' : ''
  const xAxisName = quadrantViewMode.value === 'organic' ? '有机热度' : quadrantViewMode.value === 'promo' ? '推广热度' : '热度'

  return {
    animation: false,
    tooltip: {
      trigger: 'item',
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      formatter: (params: any) => {
        const [xVal, yVal, , name, point] = params.data as [number, number, number, string, IndustryQuadrantPoint]
        const roleLabel = point.role === 'Target' ? '主体' : point.role === 'Competitor' ? '竞品' : '行业实体'
        const mentions = point.mentions || 0

        // 模式感知的主指标
        const isOrganic = quadrantViewMode.value === 'organic'
        const isPromo = quadrantViewMode.value === 'promo'
        const sentimentLabel = isOrganic ? '有机情感' : isPromo ? '推广情感' : '情感'
        const xLabel = isOrganic ? '有机热度' : isPromo ? '推广热度' : '热度'
        const xDisplay = isOrganic || isPromo ? formatCompactNumber(xVal) : formatCompactNumber(Number(point.heat || xVal))

        const fallbackNote = (isOrganic && point.organic_sentiment == null) || (isPromo && point.promo_sentiment == null)
          ? `<div style="margin-top:3px;font-size:10px;color:#9ca3af">（情感为总体情感，暂无分层精确值）</div>`
          : ''

        let spamInfo = ''
        if (point.spam_distribution) {
          const sd = point.spam_distribution
          const total = sd.high_spam.total + sd.low_spam.total
          const organicRatio = total > 0 ? ((sd.low_spam.total / total) * 100).toFixed(0) : '-'
          spamInfo = `
            <div style="margin-top:6px;padding-top:6px;border-top:1px solid #e5e7eb">
              <div style="font-size:11px;color:#888;margin-bottom:2px">有机占比</div>
              <div><b>${organicRatio}%</b> (${sd.low_spam.total}/${total})</div>
              <div style="font-size:10px;color:#888;margin-top:2px">
                推广 ${sd.high_spam.total} (原${sd.high_spam.post}/评${sd.high_spam.comment})<br>
                有机 ${sd.low_spam.total} (原${sd.low_spam.post}/评${sd.low_spam.comment})
              </div>
            </div>
          `
        }

        return `
          <div style="font-weight:600;margin-bottom:4px">${name}${viewSuffix}</div>
          <div style="font-size:12px;color:#888">${roleLabel}</div>
          <div style="margin-top:6px">
            <div>${xLabel}：<b>${xDisplay}</b></div>
            <div>${sentimentLabel}：<b style="color:${yVal >= 0 ? '#10b981' : '#ef4444'}">${yVal.toFixed(2)}</b></div>
            <div>总提及：<b>${mentions}</b></div>
          </div>
          ${fallbackNote}
          ${spamInfo}
        `
      },
    },
    legend: { show: false },
    grid: { left: 50, right: 20, top: 20, bottom: 50 },
    xAxis: {
      type: scaleMode.value === 'log' ? 'log' : 'value',
      logBase: 10,
      min: scaleMode.value === 'log' ? Math.max(minPositiveX, 0.1) : undefined,
      name: xAxisName,
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
      name: quadrantViewMode.value === 'organic' ? '有机情感' : quadrantViewMode.value === 'promo' ? '推广情感' : '情感',
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

// ==================== 高亮 ====================

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

// ==================== 图表生命周期 ====================

const updateChart = async () => {
  await nextTick()
  const points = items.value
  if (chartRef.value && points.length) {
    let instance = getInstance()
    if (!instance) {
      instance = initChart()
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
watch(quadrantViewMode, updateChart)
watch(aggregateMode, updateChart)

onMounted(() => {
  updateChart()
})
</script>

<template>
  <div class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 flex flex-col">
    <!-- 标题行 -->
    <div class="flex items-center justify-between mb-3 shrink-0">
      <div class="flex items-center gap-3">
        <h3 class="text-sm font-semibold text-gray-900 dark:text-white">行业象限</h3>
        <TabSwitch v-if="hasGroupData" v-model="aggregateMode" :options="aggregateModeOptions" />
        <TabSwitch
          v-if="hasSpamData"
          v-model="quadrantViewMode"
          :options="quadrantViewOptions"
        />
      </div>
      <div class="flex items-center gap-2">
        <TabSwitch v-model="scaleMode" :options="scaleModeOptions" />
        <span class="text-xs text-gray-500 dark:text-gray-400">
          {{ quadrantViewMode === 'organic' ? '有机热度 × 情感' : quadrantViewMode === 'promo' ? '推广热度 × 情感' : '热度 × 情感' }}
        </span>
      </div>
    </div>

    <!-- 角色图例 -->
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

    <!-- 区域图例 -->
    <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-gray-500 dark:text-gray-400 mb-1">
      <span class="inline-flex items-center gap-1">
        <span class="w-2.5 h-2.5 rounded-sm" :style="{ backgroundColor: regionColors.positive }" />
        高{{ quadrantViewMode === 'organic' ? '有机声量' : quadrantViewMode === 'promo' ? '推广声量' : '热度' }}正面（护城河）
      </span>
      <span class="inline-flex items-center gap-1">
        <span class="w-2.5 h-2.5 rounded-sm" :style="{ backgroundColor: regionColors.negative }" />
        高{{ quadrantViewMode === 'organic' ? '有机声量' : quadrantViewMode === 'promo' ? '推广声量' : '热度' }}负面（风险）
      </span>
      <span class="text-[10px] text-gray-400">仅高声量区高亮</span>
    </div>

    <div v-if="data?.length" ref="chartRef" class="flex-1 min-h-72" />
    <div v-else class="flex-1 min-h-72 flex items-center justify-center text-sm text-gray-400">
      暂无行业象限数据
    </div>
  </div>
</template>
