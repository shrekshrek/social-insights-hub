<script setup lang="ts">
import { computed, ref, watch, onMounted, nextTick } from 'vue'
import type { EChartsOption } from 'echarts'
import TopicDrilldownPanel from './TopicDrilldownPanel.vue'

interface TopicRadarItem {
  name: string
  category?: string
  heat: number
  sentiment?: number
  mentions: number
  original_terms?: Array<{ text: string; count: number }>
  platform_distribution?: Record<string, number>
  keyword_distribution?: Record<string, number>
  post_ids_sample?: Array<{ task_id: number; post_id: number }>
}

const props = defineProps<{
  pains?: TopicRadarItem[]
  gains?: TopicRadarItem[]
  controversies?: TopicRadarItem[]
  unmetNeeds?: TopicRadarItem[]
}>()

const emit = defineEmits<{
  (e: 'select' | 'open-posts', item: TopicRadarItem, type: 'pain' | 'gain' | 'controversy' | 'unmet'): void
}>()

const { chartRef, initChart, setOption, getInstance, on } = useCharts()

// 侧边栏状态
const panelOpen = ref(false)
const selectedItem = ref<TopicRadarItem | null>(null)
const selectedType = ref<'pain' | 'gain' | 'controversy' | 'unmet' | null>(null)

const handleSelect = (item: TopicRadarItem, type: 'pain' | 'gain' | 'controversy' | 'unmet') => {
  selectedItem.value = item
  selectedType.value = type
  panelOpen.value = true
  emit('select', item, type)
}

const closePanel = () => {
  panelOpen.value = false
}

// 当前激活的 Tab
const activeTab = ref<'radar' | 'unmet'>('radar')

// 检查是否有图表数据
const hasChartData = computed(() => {
  const pains = props.pains || []
  const gains = props.gains || []
  const controversies = props.controversies || []
  return pains.length > 0 || gains.length > 0 || controversies.length > 0
})

// ECharts 配置：气泡图 (X=声量, Y=情感)
const getOption = (): EChartsOption => {
  const pains = props.pains || []
  const gains = props.gains || []
  const controversies = props.controversies || []

  if (!pains.length && !gains.length && !controversies.length) return {}

  // 计算最大热度用于归一化气泡大小
  const allItems = [...pains, ...gains, ...controversies]
  const maxHeat = Math.max(...allItems.map(i => i.heat || 0), 1)
  const sortedHeats = allItems.map(i => i.heat || 0).sort((a, b) => a - b)
  const volumeThreshold = sortedHeats.length ? sortedHeats[Math.floor(sortedHeats.length / 2)] : 0
  const labelNameSet = new Set(
    allItems
      .slice()
      .sort((a, b) => (b.heat || 0) - (a.heat || 0))
      .slice(0, 30)
      .map(i => i.name)
      .filter(Boolean)
  )
  const truncateLabel = (s: string) => (s.length > 6 ? `${s.slice(0, 6)}…` : s)

  const buildSeries = (
    items: TopicRadarItem[],
    name: string,
    color: string,
    type: 'pain' | 'gain' | 'controversy'
  ) => ({
    name,
    type: 'scatter' as const,
    symbolSize: (val: number[]) => Math.max(8, Math.min(35, ((val[2] ?? 0) / maxHeat) * 35 + 8)),
    label: {
      show: true,
      position: 'right' as const,
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
      color,
      opacity: 0.7,
    },
    emphasis: {
      itemStyle: {
        opacity: 1,
        shadowBlur: 8,
        shadowColor: color,
      },
    },
    data: items.map(i => [
      i.heat,
      i.sentiment ?? 0,
      i.heat,
      i.name,
      i.category || '',
      i.mentions,
      type,
      i,
    ]),
  })

  const zoneLabelTextStyle = { fontSize: 11, fontWeight: 600, color: '#6b7280' }
  const buildZones = () => ({
    silent: true,
    itemStyle: { opacity: 0.18 },
    label: { show: true, color: '#6b7280', fontSize: 11, fontWeight: 600 },
    data: [
      [
        {
          name: '护城河',
          xAxis: volumeThreshold,
          yAxis: 0.2,
          itemStyle: { color: '#10b981' },
          label: { show: true, position: 'insideTopLeft', ...zoneLabelTextStyle },
        },
        { xAxis: 'max', yAxis: 1 },
      ],
      [
        {
          name: '机会区',
          xAxis: volumeThreshold,
          yAxis: -1,
          itemStyle: { color: '#ef4444' },
          label: { show: true, position: 'insideBottomLeft', ...zoneLabelTextStyle },
        },
        { xAxis: 'max', yAxis: -0.2 },
      ],
    ],
  })

  return {
    animation: false,
    tooltip: {
      trigger: 'item',
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      formatter: (params: any) => {
        const [heat, sentiment, , name, category, mentions] = params.data as [number, number, number, string, string, number]
        return `
          <div style="font-weight:600;margin-bottom:4px">${name}</div>
          <div style="font-size:11px;color:#888">${category || '未分类'}</div>
          <div style="margin-top:6px;font-size:12px">
            <div>热度：<b>${heat.toFixed(0)}</b></div>
            <div>情感：<b style="color:${sentiment >= 0 ? '#10b981' : '#ef4444'}">${sentiment.toFixed(2)}</b></div>
            <div>提及：<b>${mentions}</b></div>
          </div>
        `
      },
    },
    grid: {
      left: 50,
      right: 20,
      top: 20,
      bottom: 55,
    },
    xAxis: {
      type: 'value',
      name: '声量',
      nameLocation: 'middle',
      nameGap: 28,
      nameTextStyle: { fontSize: 11, color: '#6b7280' },
      axisLine: { lineStyle: { color: '#e5e7eb' } },
      splitLine: { lineStyle: { color: '#f3f4f6', type: 'dashed' } },
      axisLabel: {
        fontSize: 10,
        formatter: (v: number) => {
          if (v >= 1000000) return `${(v / 1000000).toFixed(0)}M`
          if (v >= 1000) return `${(v / 1000).toFixed(0)}K`
          return v.toString()
        },
      },
    },
    yAxis: {
      type: 'value',
      name: '情感',
      nameLocation: 'middle',
      nameGap: 38,
      nameTextStyle: { fontSize: 11, color: '#6b7280' },
      min: -1,
      max: 1,
      axisLine: { lineStyle: { color: '#e5e7eb' } },
      splitLine: { lineStyle: { color: '#f3f4f6', type: 'dashed' } },
      axisLabel: { fontSize: 10 },
    },
    series: [
      {
        ...buildSeries(pains, '痛点', '#ef4444', 'pain'),
        markArea: buildZones(),
      },
      buildSeries(gains, '爽点', '#10b981', 'gain'),
      buildSeries(controversies, '争议点', '#f59e0b', 'controversy'),
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ] as any,
  }
}

const updateChart = async () => {
  await nextTick()
  if (chartRef.value && hasChartData.value) {
    let instance = getInstance()
    if (!instance) {
      instance = initChart()
      // 绑定点击事件
      on('click', (params: unknown) => {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const p = params as any
        if (p.data && p.data[7]) {
          const type = p.data[6] as 'pain' | 'gain' | 'controversy'
          const item = p.data[7] as TopicRadarItem
          handleSelect(item, type)
        }
      })
    }
    setOption(getOption())
  }
}

watch([() => props.pains, () => props.gains, () => props.controversies], updateChart, { deep: true })

onMounted(() => {
  updateChart()
})

// Unmet Needs 列表
const unmetNeedsList = computed(() => props.unmetNeeds || [])

const handleUnmetClick = (item: TopicRadarItem) => {
  handleSelect(item, 'unmet')
}
</script>

<template>
  <div class="p-4 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-sm font-semibold text-gray-900 dark:text-white">话题雷达</h3>

      <!-- Tab 切换 -->
      <div class="flex gap-1 text-xs">
        <button
          class="px-2.5 py-1 rounded transition-colors"
          :class="activeTab === 'radar' ? 'bg-primary-100 text-primary-700 dark:bg-primary-900/30 dark:text-primary-400' : 'text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800'"
          @click="activeTab = 'radar'"
        >
          痛点/爽点
        </button>
        <button
          class="px-2.5 py-1 rounded transition-colors"
          :class="activeTab === 'unmet' ? 'bg-primary-100 text-primary-700 dark:bg-primary-900/30 dark:text-primary-400' : 'text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800'"
          @click="activeTab = 'unmet'"
        >
          未被满足需求
        </button>
      </div>
    </div>

    <!-- 雷达气泡图 -->
    <div v-show="activeTab === 'radar'">
      <div v-if="hasChartData" ref="chartRef" class="h-100" />
      <div v-else class="h-80 flex items-center justify-center text-sm text-gray-400">
        暂无话题雷达数据
      </div>

      <div class="mt-3 flex gap-4 justify-center text-xs text-gray-500 dark:text-gray-400">
        <div class="flex items-center gap-1.5">
          <span class="w-2 h-2 rounded-full bg-red-500" />
          <span>痛点 ({{ props.pains?.length || 0 }})</span>
        </div>
        <div class="flex items-center gap-1.5">
          <span class="w-2 h-2 rounded-full bg-emerald-500" />
          <span>爽点 ({{ props.gains?.length || 0 }})</span>
        </div>
        <div class="flex items-center gap-1.5">
          <span class="w-2 h-2 rounded-full bg-amber-500" />
          <span>争议点 ({{ props.controversies?.length || 0 }})</span>
        </div>
      </div>
    </div>

    <!-- 未被满足需求列表 -->
    <div v-show="activeTab === 'unmet'">
      <div v-if="unmetNeedsList.length" class="space-y-2">
        <div
          v-for="item in unmetNeedsList"
          :key="item.name"
          class="p-3 rounded-lg bg-red-50/50 dark:bg-red-900/10 border border-red-100 dark:border-red-900/30 cursor-pointer transition-colors hover:bg-red-50 dark:hover:bg-red-900/20"
          @click="handleUnmetClick(item)"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-2">
                <span class="font-medium text-gray-900 dark:text-white">{{ item.name }}</span>
                <span class="text-[10px] px-1.5 py-0.5 rounded bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400">
                  行业共性痛点
                </span>
              </div>
              <div class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                {{ item.category || '未分类' }}
              </div>
            </div>
            <div class="text-right text-xs shrink-0">
              <div class="font-mono text-gray-700 dark:text-gray-300">热度 {{ item.heat.toFixed(0) }}</div>
              <div class="text-red-600 dark:text-red-400">情感 {{ (item.sentiment ?? 0).toFixed(2) }}</div>
            </div>
          </div>

          <!-- 原话摘要 -->
          <div
            v-if="item.original_terms?.length"
            class="mt-2 pt-2 border-t border-red-100 dark:border-red-900/30"
          >
            <div class="text-[10px] text-gray-400 mb-1">用户原话</div>
            <div class="text-xs text-gray-600 dark:text-gray-400 line-clamp-2">
              {{ item.original_terms.slice(0, 3).map(t => `"${t.text}"`).join('；') }}
            </div>
          </div>
        </div>
      </div>
      <div v-else class="h-48 flex items-center justify-center text-sm text-gray-400">
        暂无"未被满足需求"数据
      </div>
    </div>

    <!-- 话题详情侧边栏 -->
    <TopicDrilldownPanel
      :item="selectedItem"
      :type="selectedType"
      :open="panelOpen"
      @close="closePanel"
      @open-posts="(item, type) => emit('open-posts', item, type)"
    />
  </div>
</template>
