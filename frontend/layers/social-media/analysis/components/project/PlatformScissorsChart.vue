<script setup lang="ts">
import { computed, ref, watch, onMounted, nextTick } from 'vue'
import type { EChartsOption } from 'echarts'
import TabSwitch from '../shared/TabSwitch.vue'

interface PlatformScissorsItem {
  platform: string
  subject_mentions: number
  industry_mentions: number
  subject_share: number
  industry_share: number
  delta: number
  subject_organic_mentions?: number
  subject_promo_mentions?: number
  industry_organic_mentions?: number
  industry_promo_mentions?: number
}

interface PlatformScissorsData {
  subject_total_mentions: number
  industry_total_mentions: number
  by_platform: PlatformScissorsItem[]
  subject_total_organic_mentions?: number
  subject_total_promo_mentions?: number
  industry_total_organic_mentions?: number
  industry_total_promo_mentions?: number
}

const props = defineProps<{
  data?: PlatformScissorsData | null
  subject?: string
}>()

const { chartRef, initChart, setOption, getInstance } = useCharts()

// ==================== 视图模式 ====================

type ScissorsViewMode = 'all' | 'organic' | 'promo'
const scissorsViewMode = ref<ScissorsViewMode>('all')

const scissorsViewOptions = [
  { value: 'all', label: '全量' },
  { value: 'organic', label: '有机' },
  { value: 'promo', label: '推广' },
]

// ==================== 能力检测 ====================

const items = computed(() => props.data?.by_platform || [])

const hasSpamData = computed(() =>
  items.value.some(i =>
    i.subject_organic_mentions != null ||
    i.industry_organic_mentions != null ||
    i.subject_promo_mentions != null ||
    i.industry_promo_mentions != null,
  ),
)

// ==================== 视图数值计算 ====================

interface PlatformDisplayValues {
  subjectShare: number   // 0-100
  industryShare: number  // 0-100
  delta: number          // 0-100 差值
}

const getDisplayValues = computed((): PlatformDisplayValues[] => {
  if (!items.value.length) return []

  if (scissorsViewMode.value === 'all') {
    return items.value.map(i => ({
      subjectShare: parseFloat((i.subject_share * 100).toFixed(1)),
      industryShare: parseFloat((i.industry_share * 100).toFixed(1)),
      delta: parseFloat((i.delta * 100).toFixed(1)),
    }))
  }

  const isOrganic = scissorsViewMode.value === 'organic'

  // 归一化分母：优先使用后端提供的总量，否则从各平台求和
  const subjectTotal = isOrganic
    ? (props.data?.subject_total_organic_mentions ?? items.value.reduce((s, i) => s + (i.subject_organic_mentions || 0), 0))
    : (props.data?.subject_total_promo_mentions ?? items.value.reduce((s, i) => s + (i.subject_promo_mentions || 0), 0))

  const industryTotal = isOrganic
    ? (props.data?.industry_total_organic_mentions ?? items.value.reduce((s, i) => s + (i.industry_organic_mentions || 0), 0))
    : (props.data?.industry_total_promo_mentions ?? items.value.reduce((s, i) => s + (i.industry_promo_mentions || 0), 0))

  return items.value.map(i => {
    const subjectMentions = isOrganic
      ? (i.subject_organic_mentions ?? 0)
      : (i.subject_promo_mentions ?? 0)
    const industryMentions = isOrganic
      ? (i.industry_organic_mentions ?? 0)
      : (i.industry_promo_mentions ?? 0)

    const subjectShare = subjectTotal > 0
      ? parseFloat(((subjectMentions / subjectTotal) * 100).toFixed(1))
      : 0
    const industryShare = industryTotal > 0
      ? parseFloat(((industryMentions / industryTotal) * 100).toFixed(1))
      : 0

    return { subjectShare, industryShare, delta: parseFloat((subjectShare - industryShare).toFixed(1)) }
  })
})

// ==================== 格式化 ====================

const subjectLabel = computed(() => props.subject || '目标')
const viewLabel = computed(() => {
  if (scissorsViewMode.value === 'organic') return '有机'
  if (scissorsViewMode.value === 'promo') return '推广'
  return ''
})

const formatDeltaVal = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`

// ==================== ECharts 配置 ====================

const getOption = (): EChartsOption => {
  const vals = getDisplayValues.value
  if (!vals.length) return {}

  const platforms = items.value.map(i => i.platform)
  const subjectData = vals.map(v => v.subjectShare)
  const industryData = vals.map(v => v.industryShare)

  const sLabel = viewLabel.value ? `${subjectLabel.value}（${viewLabel.value}）` : subjectLabel.value
  const iLabel = viewLabel.value ? `行业均值（${viewLabel.value}）` : '行业平均'

  return {
    animation: false,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      formatter: (params: any) => {
        const idx = params[0]?.dataIndex ?? 0
        const item = items.value[idx]
        const val = vals[idx]
        if (!item || !val) return ''

        const deltaColor = val.delta >= 0 ? '#10b981' : '#ef4444'
        const deltaStr = formatDeltaVal(val.delta)

        // 原始提及量信息
        let mentionInfo = ''
        if (scissorsViewMode.value === 'all') {
          mentionInfo = `
            <div style="margin-top:4px;font-size:11px;color:#888">
              ${subjectLabel.value} ${item.subject_mentions} 条 · 行业 ${item.industry_mentions} 条
            </div>`
        } else if (scissorsViewMode.value === 'organic') {
          const sm = item.subject_organic_mentions ?? '-'
          const im = item.industry_organic_mentions ?? '-'
          mentionInfo = `
            <div style="margin-top:4px;font-size:11px;color:#888">
              ${subjectLabel.value}有机 ${sm} 条 · 行业有机 ${im} 条
            </div>`
        } else {
          const sm = item.subject_promo_mentions ?? '-'
          const im = item.industry_promo_mentions ?? '-'
          mentionInfo = `
            <div style="margin-top:4px;font-size:11px;color:#888">
              ${subjectLabel.value}推广 ${sm} 条 · 行业推广 ${im} 条
            </div>`
        }

        return `
          <div style="font-weight:600;margin-bottom:6px">${item.platform}</div>
          <div style="font-size:12px">
            <div>${sLabel}：<b>${val.subjectShare.toFixed(1)}%</b></div>
            <div>${iLabel}：<b>${val.industryShare.toFixed(1)}%</b></div>
            <div style="color:${deltaColor}">差异：<b>${deltaStr}</b></div>
          </div>
          ${mentionInfo}
        `
      },
    },
    legend: {
      bottom: 0,
      textStyle: { fontSize: 11 },
    },
    grid: {
      left: 10,
      right: 10,
      top: 30,
      bottom: 45,
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: platforms,
      axisLabel: { fontSize: 10, rotate: 0, interval: 0 },
      axisLine: { lineStyle: { color: '#e5e7eb' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      axisLabel: { fontSize: 10, formatter: '{value}%' },
      axisLine: { show: false },
      splitLine: { lineStyle: { color: '#f3f4f6', type: 'dashed' } },
    },
    series: [
      {
        name: sLabel,
        type: 'bar',
        barWidth: 20,
        itemStyle: { color: '#10b981' },
        data: subjectData,
      },
      {
        name: iLabel,
        type: 'bar',
        barWidth: 20,
        itemStyle: { color: '#94a3b8' },
        data: industryData,
      },
    ],
  }
}

// ==================== 图表生命周期 ====================

const updateChart = async () => {
  await nextTick()
  if (chartRef.value && items.value.length) {
    let instance = getInstance()
    if (!instance) instance = initChart()
    setOption(getOption())
  }
}

watch(() => props.data, updateChart, { deep: true })
watch(scissorsViewMode, updateChart)

onMounted(() => {
  updateChart()
})
</script>

<template>
  <div class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 h-full flex flex-col">
    <!-- 标题行 -->
    <div class="flex items-center justify-between mb-3">
      <div>
        <h3 class="text-sm font-semibold text-gray-900 dark:text-white">平台剪刀差</h3>
        <p class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
          <template v-if="scissorsViewMode === 'all'">{{ subject || '目标' }} 平台份额 vs 行业平均</template>
          <template v-else-if="scissorsViewMode === 'organic'">{{ subject || '目标' }} 有机平台份额 vs 行业有机均值</template>
          <template v-else>{{ subject || '目标' }} 推广平台份额 vs 行业推广均值</template>
        </p>
      </div>
      <TabSwitch
        v-if="hasSpamData"
        v-model="scissorsViewMode"
        :options="scissorsViewOptions"
      />
    </div>

    <!-- 无机推广说明 -->
    <div
      v-if="scissorsViewMode !== 'all' && hasSpamData"
      class="mb-2 px-2.5 py-1.5 rounded bg-blue-50 dark:bg-blue-900/20 text-[11px] text-blue-700 dark:text-blue-400 leading-relaxed"
    >
      <template v-if="scissorsViewMode === 'organic'">
        <b>有机声量份额</b>：剔除推广内容后，各平台真实用户声音占比对比。
      </template>
      <template v-else>
        <b>推广声量份额</b>：各平台推广内容占比对比，可识别哪些平台推广投入比例偏高/偏低。
      </template>
    </div>

    <div v-if="items.length" ref="chartRef" class="flex-1 min-h-[280px]" />
    <div v-else class="flex-1 min-h-[280px] flex items-center justify-center text-sm text-gray-400">
      暂无平台剪刀差数据
    </div>

    <!-- 差异明细表 -->
    <div v-if="items.length && getDisplayValues.length" class="mt-3 pt-3 border-t border-gray-100 dark:border-gray-800">
      <div class="text-xs text-gray-500 dark:text-gray-400 mb-2">
        {{ viewLabel }}差异明细
        <span class="text-[10px] ml-1 text-gray-400">（正值 = 高于行业均值）</span>
      </div>
      <div class="grid grid-cols-2 sm:grid-cols-3 gap-2">
        <div
          v-for="(item, idx) in items.slice(0, 6)"
          :key="item.platform"
          class="flex items-center justify-between p-2 rounded bg-gray-50 dark:bg-gray-800/50"
        >
          <span class="text-xs text-gray-700 dark:text-gray-300">{{ item.platform }}</span>
          <span
            class="text-xs font-mono"
            :class="(getDisplayValues[idx]?.delta ?? 0) >= 0
              ? 'text-emerald-600 dark:text-emerald-400'
              : 'text-red-600 dark:text-red-400'"
          >
            {{ formatDeltaVal(getDisplayValues[idx]?.delta ?? 0) }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>
