<script setup lang="ts">
import { watch, onMounted, nextTick, ref, computed } from 'vue'
import type { EChartsOption } from 'echarts'
import type { TaskAnalysisResultData } from '../types'
import PostListModal from './PostListModal.vue'
import ClickableCount from './ClickableCount.vue'
import IpaChart from './IpaChart.vue'
import ContextGraphChart from './ContextGraphChart.vue'
import CompetitorRadarChart from './CompetitorRadarChart.vue'

const props = defineProps<{
  data: TaskAnalysisResultData
}>()

// 帖子列表弹窗状态
const postListModalOpen = ref(false)
const postListModalTitle = ref('')
const postListModalPostIds = ref<number[]>([])

/** 打开帖子列表弹窗 */
const openPostListModal = (title: string, postIds: number[]) => {
  if (!postIds || postIds.length === 0) return
  postListModalTitle.value = title
  postListModalPostIds.value = postIds
  postListModalOpen.value = true
}

/** 获取 taskId */
const taskId = computed(() => props.data.meta.task_id || 0)

// 列表展开状态
const topEntitiesExpanded = ref(false)
const kolVoicesExpanded = ref(false)

/** 获取四象限中某个象限的帖子IDs */
const getQuadrantPostIds = (quadrant: string): number[] => {
  const items = props.data.charts.quadrant || []
  return items
    .filter(item => item.quadrant === quadrant)
    .map(item => item.post_id)
}

// 时间分布图表
const { chartRef: timeChartRef, initChart: initTimeChart, setOption: setTimeOption, getInstance: getTimeInstance } = useCharts()

/** 时间分布图表配置 */
const getTimeChartOption = (): EChartsOption => {
  const dist = props.data.charts.time_distribution || []
  return {
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(255, 255, 255, 0.95)',
      borderColor: '#e5e7eb',
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

/** 处理时间分布图表点击事件 */
const handleTimeChartClick = (params: { dataIndex: number }) => {
  const dist = props.data.charts.time_distribution || []
  const item = dist[params.dataIndex]
  if (!item) return
  const postIds = item.post_ids
  if (postIds && postIds.length > 0) {
    openPostListModal(`${item.date} 发布的内容`, postIds)
  }
}

/** 初始化时间分布图表 */
const setupTimeChart = async () => {
  await nextTick()
  // 等待 DOM 渲染完成
  await new Promise(resolve => setTimeout(resolve, 100))
  if (timeChartRef.value && props.data.charts.time_distribution?.length) {
    const instance = initTimeChart()
    if (instance) {
      setTimeOption(getTimeChartOption())
      // 添加点击事件监听
      instance.off('click')
      instance.on('click', handleTimeChartClick)
    }
  }
}

// 数据变化时更新图表
watch(() => props.data.charts.time_distribution, async () => {
  await nextTick()
  if (timeChartRef.value && props.data.charts.time_distribution?.length) {
    // 如果图表未初始化，先初始化
    let instance = getTimeInstance()
    if (!instance) {
      instance = initTimeChart()
      if (!instance) return
      // 添加点击事件监听
      instance.on('click', handleTimeChartClick)
    }
    setTimeOption(getTimeChartOption())
  }
}, { deep: true })

onMounted(() => {
  setupTimeChart()
})

/** 格式化百分比 */
const formatPercent = (value: number) => {
  return `${(value * 100).toFixed(1)}%`
}

/** 获取 NSR 颜色 */
const getNsrColor = (nsr: number) => {
  if (nsr >= 1) return 'success'
  if (nsr >= 0) return 'info'
  if (nsr >= -1) return 'warning'
  return 'error'
}

/** 获取 SERP 颜色 */
const getSerpColor = (serp: number) => {
  if (serp >= 70) return 'success'
  if (serp >= 50) return 'info'
  if (serp >= 30) return 'warning'
  return 'error'
}

/** 获取情感标签（派生情感值范围 [-1, 1]） */
const getSentimentLabel = (sentiment: number) => {
  if (sentiment >= 0.6) return '正面'
  if (sentiment >= 0.2) return '偏正面'
  if (sentiment >= -0.2) return '中性'
  if (sentiment >= -0.6) return '偏负面'
  return '负面'
}

/** 获取情感颜色（派生情感值范围 [-1, 1]） */
const getSentimentColor = (sentiment: number) => {
  if (sentiment >= 0.2) return 'success'
  if (sentiment >= -0.2) return 'neutral'
  return 'error'
}

/** 获取风险等级颜色 */
const getRiskColor = (risk: string) => {
  if (risk === 'high') return 'error'
  if (risk === 'medium') return 'warning'
  return 'success'
}

/** 获取风险等级标签 */
const getRiskLabel = (risk: string) => {
  if (risk === 'high') return '高风险'
  if (risk === 'medium') return '中风险'
  return '低风险'
}

/** 获取反差方向标签 */
const getConflictDirectionLabel = (direction: string) => {
  if (direction === 'post_positive') return '帖子更正面'
  if (direction === 'comment_positive') return '评论更正面'
  return '情感一致'
}

const hasContextGraph = computed(() => !!props.data.charts.context_graph?.nodes?.length)
const hasCompetitorRadar = computed(() => !!(props.data.charts.competitor_radar && props.data.charts.competitor_radar.mode !== 'none'))

</script>

<template>
  <div class="space-y-6">
    <!-- 分析概览：元数据 + 数据量统计 + 数据新鲜度 -->
    <section class="p-4 bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-gray-800 dark:to-gray-800 rounded-lg border border-blue-100 dark:border-gray-700">
      <div class="flex flex-wrap items-center justify-between gap-4">
        <!-- 左侧：分析时间和关键词 -->
        <div class="flex items-center gap-4">
          <div v-if="data.meta.analyzed_at" class="flex items-center gap-2 text-sm">
            <UIcon name="i-heroicons-clock" class="w-4 h-4 text-blue-500" />
            <span class="text-gray-500 dark:text-gray-400">分析时间:</span>
            <span class="text-gray-700 dark:text-gray-300">{{ new Date(data.meta.analyzed_at).toLocaleString('zh-CN') }}</span>
          </div>
          <div v-if="data.meta.keywords?.length" class="flex items-center gap-2 text-sm">
            <UIcon name="i-heroicons-tag" class="w-4 h-4 text-blue-500" />
            <span class="text-gray-500 dark:text-gray-400">关键词:</span>
            <div class="flex gap-1">
              <UBadge v-for="kw in data.meta.keywords.slice(0, 5)" :key="kw" color="primary" variant="subtle" size="xs">
                {{ kw }}
              </UBadge>
            </div>
          </div>
        </div>
        <!-- 右侧：数据量统计 + 数据新鲜度 -->
        <div class="flex items-center gap-6 text-sm">
          <!-- 数据量 -->
          <div class="flex items-center gap-4">
            <div class="flex items-center gap-1">
              <span class="text-gray-500 dark:text-gray-400">总量</span>
              <span class="font-mono font-medium text-gray-900 dark:text-white">{{ data.meta.data_volume.total }}</span>
            </div>
            <div class="flex items-center gap-1">
              <span class="text-gray-500 dark:text-gray-400">初筛</span>
              <span class="font-mono font-medium text-blue-600 dark:text-blue-400">{{ data.meta.data_volume.screened }}</span>
            </div>
            <div class="flex items-center gap-1">
              <span class="text-gray-500 dark:text-gray-400">深度</span>
              <span class="font-mono font-medium text-green-600 dark:text-green-400">{{ data.meta.data_volume.deep_analyzed }}</span>
            </div>
            <div class="flex items-center gap-1">
              <span class="text-gray-500 dark:text-gray-400">评论</span>
              <span class="font-mono font-medium text-purple-600 dark:text-purple-400">{{ data.meta.data_volume.comment_analyzed }}</span>
            </div>
          </div>
          <!-- 分隔线 -->
          <div class="h-4 w-px bg-gray-300 dark:bg-gray-600" />
          <!-- 数据新鲜度 -->
          <div class="flex items-center gap-3">
            <UTooltip text="数据新鲜度">
              <UIcon name="i-heroicons-calendar-days" class="w-4 h-4 text-blue-500" />
            </UTooltip>
            <div class="flex items-center gap-1">
              <span class="text-gray-500 dark:text-gray-400">7天</span>
              <span class="font-mono font-medium text-gray-900 dark:text-white">{{ formatPercent(data.freshness.last_7_days) }}</span>
            </div>
            <div class="flex items-center gap-1">
              <span class="text-gray-500 dark:text-gray-400">30天</span>
              <span class="font-mono font-medium text-gray-900 dark:text-white">{{ formatPercent(data.freshness.last_30_days) }}</span>
            </div>
            <div class="flex items-center gap-1">
              <span class="text-gray-500 dark:text-gray-400">均龄</span>
              <span class="font-mono font-medium text-gray-900 dark:text-white">{{ data.freshness.avg_age_days.toFixed(0) }}天</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 核心指标卡片 -->
    <section>
      <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">核心指标</h3>
      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        <!-- NSR 净情感率 -->
        <div class="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
          <div class="flex items-center justify-between mb-2">
            <span class="text-sm text-gray-500 dark:text-gray-400">NSR 净情感率</span>
            <UBadge :color="getNsrColor(data.metrics.nsr)" variant="subtle" size="xs">
              {{ data.metrics.nsr >= 0 ? '+' : '' }}{{ data.metrics.nsr.toFixed(2) }}
            </UBadge>
          </div>
          <p class="text-2xl font-bold text-gray-900 dark:text-white">
            {{ getSentimentLabel(data.metrics.nsr) }}
          </p>
          <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">范围: -2 ~ +2</p>
        </div>

        <!-- CII 互动指数 -->
        <div class="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
          <div class="flex items-center justify-between mb-2">
            <span class="text-sm text-gray-500 dark:text-gray-400">平均 CII</span>
          </div>
          <p class="text-2xl font-bold text-gray-900 dark:text-white">
            {{ data.metrics.avg_cii.toFixed(1) }}
          </p>
          <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">内容互动指数</p>
        </div>

        <!-- SERP 健康度 -->
        <div class="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
          <div class="flex items-center justify-between mb-2">
            <span class="text-sm text-gray-500 dark:text-gray-400">SERP 健康度</span>
            <UBadge :color="getSerpColor(data.metrics.serp_health)" variant="subtle" size="xs">
              {{ data.metrics.serp_health.toFixed(0) }}
            </UBadge>
          </div>
          <UProgress
            :model-value="data.metrics.serp_health"
            :max="100"
            size="sm"
            :color="getSerpColor(data.metrics.serp_health)"
            class="mt-2"
          />
          <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">搜索结果质量</p>
        </div>

        <!-- 营销浓度 -->
        <div class="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
          <div class="flex items-center justify-between mb-2">
            <span class="text-sm text-gray-500 dark:text-gray-400">营销浓度</span>
          </div>
          <p class="text-2xl font-bold text-gray-900 dark:text-white">
            {{ formatPercent(data.metrics.marketing_analysis.promotion_ratio) }}
          </p>
          <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
            自然内容: {{ formatPercent(data.metrics.marketing_analysis.organic_ratio) }}
          </p>
        </div>

        <!-- 舆论反差度 -->
        <div class="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
          <div class="flex items-center justify-between mb-2">
            <span class="text-sm text-gray-500 dark:text-gray-400">舆论反差度</span>
            <UBadge :color="getRiskColor(data.metrics.sentiment_conflict.risk_level)" variant="subtle" size="xs">
              {{ getRiskLabel(data.metrics.sentiment_conflict.risk_level) }}
            </UBadge>
          </div>
          <p class="text-2xl font-bold text-gray-900 dark:text-white">
            {{ data.metrics.sentiment_conflict.avg_conflict.toFixed(2) }}
          </p>
          <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
            {{ getConflictDirectionLabel(data.metrics.sentiment_conflict.conflict_direction) }}
            <span v-if="data.metrics.sentiment_conflict.high_conflict_count > 0" class="text-orange-500">
              ({{ data.metrics.sentiment_conflict.high_conflict_count }}条高反差)
            </span>
          </p>
        </div>
      </div>
    </section>

    <!-- 四象限统计 -->
    <section>
      <div class="flex items-center gap-2 mb-3">
        <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300">舆情四象限分布</h3>
        <UTooltip text="按情感(正/负)和CII互动指数(高/低)划分，以均值为分界">
          <UIcon name="i-heroicons-question-mark-circle" class="w-4 h-4 text-gray-400" />
        </UTooltip>
      </div>
      <div class="grid grid-cols-2 md:grid-cols-5 gap-3">
        <button
          class="text-center p-3 bg-red-50 dark:bg-red-900/20 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors cursor-pointer"
          :disabled="data.charts.quadrant_summary.Q1_danger === 0"
          @click="openPostListModal('爆雷区帖子', getQuadrantPostIds('Q1_danger'))"
        >
          <p class="text-xl font-bold text-red-600 dark:text-red-400">{{ data.charts.quadrant_summary.Q1_danger }}</p>
          <p class="text-xs text-gray-600 dark:text-gray-400">爆雷区</p>
          <p class="text-xs text-gray-400 dark:text-gray-500">高互动/负面</p>
        </button>
        <button
          class="text-center p-3 bg-green-50 dark:bg-green-900/20 rounded-lg hover:bg-green-100 dark:hover:bg-green-900/30 transition-colors cursor-pointer"
          :disabled="data.charts.quadrant_summary.Q2_brand === 0"
          @click="openPostListModal('品牌区帖子', getQuadrantPostIds('Q2_brand'))"
        >
          <p class="text-xl font-bold text-green-600 dark:text-green-400">{{ data.charts.quadrant_summary.Q2_brand }}</p>
          <p class="text-xs text-gray-600 dark:text-gray-400">品牌区</p>
          <p class="text-xs text-gray-400 dark:text-gray-500">高互动/正面</p>
        </button>
        <button
          class="text-center p-3 bg-orange-50 dark:bg-orange-900/20 rounded-lg hover:bg-orange-100 dark:hover:bg-orange-900/30 transition-colors cursor-pointer"
          :disabled="data.charts.quadrant_summary.Q3_complaint === 0"
          @click="openPostListModal('吐槽区帖子', getQuadrantPostIds('Q3_complaint'))"
        >
          <p class="text-xl font-bold text-orange-600 dark:text-orange-400">{{ data.charts.quadrant_summary.Q3_complaint }}</p>
          <p class="text-xs text-gray-600 dark:text-gray-400">吐槽区</p>
          <p class="text-xs text-gray-400 dark:text-gray-500">低互动/负面</p>
        </button>
        <button
          class="text-center p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg hover:bg-blue-100 dark:hover:bg-blue-900/30 transition-colors cursor-pointer"
          :disabled="data.charts.quadrant_summary.Q4_niche === 0"
          @click="openPostListModal('自嗨区帖子', getQuadrantPostIds('Q4_niche'))"
        >
          <p class="text-xl font-bold text-blue-600 dark:text-blue-400">{{ data.charts.quadrant_summary.Q4_niche }}</p>
          <p class="text-xs text-gray-600 dark:text-gray-400">自嗨区</p>
          <p class="text-xs text-gray-400 dark:text-gray-500">低互动/正面</p>
        </button>
        <button
          class="text-center p-3 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors cursor-pointer"
          :disabled="data.charts.quadrant_summary.neutral === 0"
          @click="openPostListModal('中性区帖子', getQuadrantPostIds('neutral'))"
        >
          <p class="text-xl font-bold text-gray-600 dark:text-gray-300">{{ data.charts.quadrant_summary.neutral }}</p>
          <p class="text-xs text-gray-600 dark:text-gray-400">中性区</p>
          <p class="text-xs text-gray-400 dark:text-gray-500">情感中立</p>
        </button>
      </div>
    </section>

    <!-- 时间分布折线图 (ECharts) -->
    <section v-if="data.charts.time_distribution?.length">
      <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">内容发布时间分布</h3>
      <div class="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
        <ClientOnly>
          <template #fallback>
            <div class="flex items-center justify-center h-48">
              <UIcon name="i-heroicons-arrow-path" class="animate-spin h-6 w-6 text-gray-400" />
              <span class="ml-2 text-sm text-gray-400">正在加载图表...</span>
            </div>
          </template>
          <div ref="timeChartRef" class="w-full h-48" />
        </ClientOnly>
        <div class="mt-3 flex items-center justify-between text-xs text-gray-500">
          <span>共 {{ data.charts.time_distribution.length }} 天</span>
          <span>总计 {{ data.charts.time_distribution.reduce((sum, i) => sum + i.count, 0) }} 条内容</span>
        </div>
      </div>
    </section>

    <!-- 产品力诊断 (IPA) -->
    <section v-if="data.charts.ipa_analysis?.quadrants">
      <ClientOnly>
        <IpaChart :data="data.charts.ipa_analysis" @click-point="openPostListModal" />
      </ClientOnly>
    </section>

    <!-- 热门观点：问题 vs 特性 -->
    <section v-if="data.insights.top_topics?.length">
      <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">热门话题</h3>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <!-- 热门问题（负面观点） -->
        <div class="p-4 bg-red-50 dark:bg-red-900/10 rounded-lg border border-red-100 dark:border-red-900/30">
          <div class="flex items-center gap-2 mb-3">
            <UIcon name="i-heroicons-exclamation-triangle" class="w-5 h-5 text-red-500" />
            <span class="font-medium text-gray-900 dark:text-white">热门问题</span>
            <span class="text-xs text-gray-400">(负面观点)</span>
          </div>
          <div v-if="data.insights.top_topics.filter(t => t.sentiment < 0).length" class="space-y-3">
            <div
              v-for="issue in data.insights.top_topics.filter(t => t.sentiment < 0).slice(0, 5)"
              :key="issue.name"
              class="text-sm"
            >
              <div class="flex items-center justify-between mb-1">
                <span class="font-medium text-gray-800 dark:text-gray-200">{{ issue.name }}</span>
                <div class="flex items-center gap-2 text-xs">
                  <span class="text-gray-500 dark:text-gray-400">
                    热度 <span class="font-mono text-gray-700 dark:text-gray-300">{{ issue.heat.toFixed(1) }}</span>
                  </span>
                  <ClickableCount
                    :count="issue.mentions"
                    :post-ids="issue.post_ids"
                    :label="issue.name"
                    @click="openPostListModal"
                  />
                </div>
              </div>
              <ul v-if="issue.opinions?.length" class="text-xs text-gray-600 dark:text-gray-400 mb-1 list-disc list-inside space-y-0.5">
                <li v-for="(op, idx) in issue.opinions.slice(0, 3)" :key="idx">{{ op.text }} ({{ op.count }})</li>
              </ul>
              <div class="flex items-center gap-2 text-xs text-gray-400">
                <span>帖子 {{ issue.post_source_count || 0 }} / 评论 {{ issue.comment_source_count || 0 }}</span>
              </div>
            </div>
          </div>
          <p v-else class="text-sm text-gray-400">暂无数据</p>
        </div>

        <!-- 热门特性（正面观点） -->
        <div class="p-4 bg-green-50 dark:bg-green-900/10 rounded-lg border border-green-100 dark:border-green-900/30">
          <div class="flex items-center gap-2 mb-3">
            <UIcon name="i-heroicons-star" class="w-5 h-5 text-green-500" />
            <span class="font-medium text-gray-900 dark:text-white">热门特性</span>
            <span class="text-xs text-gray-400">(正面观点)</span>
          </div>
          <div v-if="data.insights.top_topics.filter(t => t.sentiment > 0).length" class="space-y-3">
            <div
              v-for="feature in data.insights.top_topics.filter(t => t.sentiment > 0).slice(0, 5)"
              :key="feature.name"
              class="text-sm"
            >
              <div class="flex items-center justify-between mb-1">
                <span class="font-medium text-gray-800 dark:text-gray-200">{{ feature.name }}</span>
                <div class="flex items-center gap-2 text-xs">
                  <span class="text-gray-500 dark:text-gray-400">
                    热度 <span class="font-mono text-gray-700 dark:text-gray-300">{{ feature.heat.toFixed(1) }}</span>
                  </span>
                  <ClickableCount
                    :count="feature.mentions"
                    :post-ids="feature.post_ids"
                    :label="feature.name"
                    @click="openPostListModal"
                  />
                </div>
              </div>
              <ul v-if="feature.opinions?.length" class="text-xs text-gray-600 dark:text-gray-400 mb-1 list-disc list-inside space-y-0.5">
                <li v-for="(op, idx) in feature.opinions.slice(0, 3)" :key="idx">{{ op.text }} ({{ op.count }})</li>
              </ul>
              <div class="flex items-center gap-2 text-xs text-gray-400">
                <span>帖子 {{ feature.post_source_count || 0 }} / 评论 {{ feature.comment_source_count || 0 }}</span>
              </div>
            </div>
          </div>
          <p v-else class="text-sm text-gray-400">暂无数据</p>
        </div>
      </div>
    </section>

    <!-- KANO 模型 -->
    <section v-if="data.insights.opportunities.kano_model">
      <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">KANO 需求分层</h3>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <!-- 基本型需求 -->
        <div class="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
          <div class="flex items-center gap-2 mb-3">
            <UIcon name="i-heroicons-exclamation-circle" class="w-5 h-5 text-red-500" />
            <span class="font-medium text-gray-900 dark:text-white">基本型需求（痛点）</span>
          </div>
          <div v-if="data.insights.opportunities.kano_model.must_be.length" class="space-y-3">
            <div
              v-for="item in data.insights.opportunities.kano_model.must_be.slice(0, 5)"
              :key="item.name"
              class="text-sm"
            >
              <div class="flex items-center justify-between">
                <span class="font-medium text-gray-700 dark:text-gray-300">{{ item.name }}</span>
                <div class="flex items-center gap-2 shrink-0 text-xs">
                  <ClickableCount
                    :count="item.mentions"
                    :post-ids="item.post_ids"
                    :label="item.name"
                    @click="openPostListModal"
                  />
                  <UBadge :color="getSentimentColor(item.sentiment)" variant="subtle" size="xs">
                    {{ item.sentiment >= 0 ? '+' : '' }}{{ item.sentiment.toFixed(1) }}
                  </UBadge>
                </div>
              </div>
              <div class="mt-1">
                <UProgress :model-value="item.score" :max="Math.max(...data.insights.opportunities.kano_model.must_be.map(i => i.score))" size="xs" color="error" />
              </div>
            </div>
          </div>
          <p v-else class="text-sm text-gray-400 dark:text-gray-500">暂无数据</p>
        </div>

        <!-- 期望型需求 -->
        <div class="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
          <div class="flex items-center gap-2 mb-3">
            <UIcon name="i-heroicons-arrow-trending-up" class="w-5 h-5 text-blue-500" />
            <span class="font-medium text-gray-900 dark:text-white">期望型需求（愿望）</span>
          </div>
          <div v-if="data.insights.opportunities.kano_model.one_dimensional.length" class="space-y-3">
            <div
              v-for="item in data.insights.opportunities.kano_model.one_dimensional.slice(0, 5)"
              :key="item.name"
              class="text-sm"
            >
              <div class="flex items-center justify-between">
                <span class="font-medium text-gray-700 dark:text-gray-300">{{ item.name }}</span>
                <div class="flex items-center gap-2 shrink-0 text-xs">
                  <ClickableCount
                    :count="item.mentions"
                    :post-ids="item.post_ids"
                    :label="item.name"
                    @click="openPostListModal"
                  />
                  <UBadge :color="getSentimentColor(item.sentiment)" variant="subtle" size="xs">
                    {{ item.sentiment >= 0 ? '+' : '' }}{{ item.sentiment.toFixed(1) }}
                  </UBadge>
                </div>
              </div>
              <div class="mt-1">
                <UProgress :model-value="item.score" :max="Math.max(...data.insights.opportunities.kano_model.one_dimensional.map(i => i.score))" size="xs" color="info" />
              </div>
            </div>
          </div>
          <p v-else class="text-sm text-gray-400 dark:text-gray-500">暂无数据</p>
        </div>

        <!-- 兴奋型需求 -->
        <div class="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
          <div class="flex items-center gap-2 mb-3">
            <UIcon name="i-heroicons-sparkles" class="w-5 h-5 text-green-500" />
            <span class="font-medium text-gray-900 dark:text-white">兴奋型需求（惊喜）</span>
          </div>
          <div v-if="data.insights.opportunities.kano_model.attractive.length" class="space-y-3">
            <div
              v-for="item in data.insights.opportunities.kano_model.attractive.slice(0, 5)"
              :key="item.name"
              class="text-sm"
            >
              <div class="flex items-center justify-between">
                <span class="font-medium text-gray-700 dark:text-gray-300">{{ item.name }}</span>
                <div class="flex items-center gap-2 shrink-0 text-xs">
                  <ClickableCount
                    :count="item.mentions"
                    :post-ids="item.post_ids"
                    :label="item.name"
                    @click="openPostListModal"
                  />
                  <UBadge :color="getSentimentColor(item.sentiment)" variant="subtle" size="xs">
                    {{ item.sentiment >= 0 ? '+' : '' }}{{ item.sentiment.toFixed(1) }}
                  </UBadge>
                </div>
              </div>
              <div class="mt-1">
                <UProgress :model-value="item.score" :max="Math.max(...data.insights.opportunities.kano_model.attractive.map(i => i.score))" size="xs" color="success" />
              </div>
            </div>
          </div>
          <p v-else class="text-sm text-gray-400 dark:text-gray-500">暂无数据</p>
        </div>
      </div>
    </section>

    <!-- 关联网络与竞品分析 (并排展示) -->
    <div v-if="hasContextGraph || hasCompetitorRadar" class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <!-- 关联网络 (Context Graph) -->
      <section v-if="hasContextGraph" :class="{'lg:col-span-2': !hasCompetitorRadar}">
        <ClientOnly>
          <ContextGraphChart :data="data.charts.context_graph" @click-node="openPostListModal" />
        </ClientOnly>
      </section>

      <!-- 竞品分析 -->
      <section v-if="hasCompetitorRadar" :class="{'lg:col-span-2': !hasContextGraph}">
        <ClientOnly>
          <CompetitorRadarChart :data="data.charts.competitor_radar" />
        </ClientOnly>
      </section>
    </div>

    <!-- 热门实体 -->
    <section v-if="data.insights.top_entities.length > 0">
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300">热门实体</h3>
        <button
          v-if="data.insights.top_entities.length > 5"
          class="text-xs text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300"
          @click="topEntitiesExpanded = !topEntitiesExpanded"
        >
          {{ topEntitiesExpanded ? '收起' : `查看全部 ${Math.min(data.insights.top_entities.length, 10)} 项` }}
        </button>
      </div>
      <div class="space-y-2">
        <div
          v-for="entity in data.insights.top_entities.slice(0, topEntitiesExpanded ? 10 : 5)"
          :key="entity.name"
          class="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg"
        >
          <!-- 实体基本信息行 -->
          <div class="flex items-center justify-between flex-wrap gap-2">
            <div class="flex items-center gap-2">
              <span class="font-medium text-gray-900 dark:text-white">{{ entity.name }}</span>
              <UBadge color="neutral" variant="subtle" size="xs">{{ entity.type }}</UBadge>
              <UBadge
                :color="entity.role === 'target' ? 'primary' : entity.role === 'competitor' ? 'warning' : 'neutral'"
                variant="subtle"
                size="xs"
              >
                {{ entity.role === 'target' ? '本品' : entity.role === 'competitor' ? '竞品' : '其他' }}
              </UBadge>
            </div>
            <div class="flex items-center gap-2 text-xs">
              <span class="text-gray-500 dark:text-gray-400">
                热度 <span class="font-mono text-gray-700 dark:text-gray-300">{{ entity.heat.toFixed(1) }}</span>
              </span>
              <ClickableCount
                :count="entity.mentions"
                :post-ids="entity.post_ids"
                :label="entity.name"
                @click="openPostListModal"
              />
              <UBadge :color="getSentimentColor(entity.sentiment)" variant="subtle" size="xs">
                {{ getSentimentLabel(entity.sentiment) }}
              </UBadge>
            </div>
          </div>
          <!-- 情感分布 -->
          <div v-if="entity.sentiment_distribution" class="mt-2 flex items-center gap-2 text-xs">
            <span class="text-gray-500 dark:text-gray-400">情感分布:</span>
            <span class="text-green-600 dark:text-green-400">正面 {{ entity.sentiment_distribution.positive }}</span>
            <span class="text-gray-500 dark:text-gray-400">中性 {{ entity.sentiment_distribution.neutral }}</span>
            <span class="text-red-600 dark:text-red-400">负面 {{ entity.sentiment_distribution.negative }}</span>
          </div>
          <!-- 归一化信息（别名、关联实体） -->
          <div v-if="entity.normalized_info" class="mt-2 space-y-1 text-xs">
            <div v-if="entity.normalized_info.aliases?.length" class="flex flex-wrap items-baseline gap-x-2">
              <span class="text-gray-400 dark:text-gray-500 shrink-0">别名:</span>
              <span v-for="alias in entity.normalized_info.aliases.slice(0, 3)" :key="alias" class="text-gray-500 dark:text-gray-400">{{ alias }}</span>
            </div>
            <div v-if="entity.normalized_info.related?.length" class="flex flex-wrap items-baseline gap-x-2">
              <span class="text-gray-400 dark:text-gray-500 shrink-0">关联:</span>
              <span v-for="rel in entity.normalized_info.related.slice(0, 3)" :key="rel" class="text-indigo-500 dark:text-indigo-400">{{ rel }}</span>
            </div>
            <div v-if="entity.normalized_info.merged_from?.length" class="flex flex-wrap items-baseline gap-x-2">
              <UTooltip :text="`已合并 ${entity.normalized_info.merged_from.length} 个相似实体`">
                <span class="text-gray-400 dark:text-gray-500 italic">
                  (合并自: {{ entity.normalized_info.merged_from.slice(0, 2).join('、') }}{{ entity.normalized_info.merged_from.length > 2 ? '...' : '' }})
                </span>
              </UTooltip>
            </div>
          </div>
          <!-- 特性、问题和期望 -->
          <div v-if="entity.top_features?.length || entity.top_issues?.length || entity.top_expectations?.length" class="mt-2 space-y-1 text-xs">
            <div v-if="entity.top_features?.length" class="flex flex-wrap items-baseline gap-x-3">
              <span class="font-medium text-green-600 dark:text-green-400 shrink-0">特性：</span>
              <span v-for="f in entity.top_features.slice(0, 3)" :key="f" class="text-gray-700 dark:text-gray-300">{{ f }}</span>
            </div>
            <div v-if="entity.top_issues?.length" class="flex flex-wrap items-baseline gap-x-3">
              <span class="font-medium text-red-600 dark:text-red-400 shrink-0">问题：</span>
              <span v-for="i in entity.top_issues.slice(0, 3)" :key="i" class="text-gray-700 dark:text-gray-300">{{ i }}</span>
            </div>
            <div v-if="entity.top_expectations?.length" class="flex flex-wrap items-baseline gap-x-3">
              <span class="font-medium text-blue-600 dark:text-blue-400 shrink-0">期望：</span>
              <span v-for="e in entity.top_expectations.slice(0, 3)" :key="e" class="text-gray-700 dark:text-gray-300">{{ e }}</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 高影响力内容 -->
    <section v-if="data.insights.kol_voices.length > 0">
      <div class="flex items-center justify-between mb-3">
        <div class="flex items-center gap-2">
          <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300">高影响力内容 TOP {{ Math.min(data.insights.kol_voices.length, 10) }}</h3>
        </div>
        <button
          v-if="data.insights.kol_voices.length > 5"
          class="text-xs text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300"
          @click="kolVoicesExpanded = !kolVoicesExpanded"
        >
          {{ kolVoicesExpanded ? '收起' : `查看全部 ${Math.min(data.insights.kol_voices.length, 10)} 项` }}
        </button>
      </div>
      <div class="space-y-2">
        <div
          v-for="item in data.insights.kol_voices.slice(0, kolVoicesExpanded ? 10 : 5)"
          :key="item.post_id"
          class="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg"
        >
          <div class="flex items-center justify-between mb-2">
            <div class="flex items-center gap-2">
              <UIcon name="i-heroicons-fire" class="w-5 h-5 text-orange-500" />
              <span class="font-medium text-gray-900 dark:text-white">{{ item.author }}</span>
            </div>
            <div class="flex items-center gap-2">
              <UBadge :color="getSentimentColor(item.sentiment)" variant="subtle" size="xs">
                {{ getSentimentLabel(item.sentiment) }}
              </UBadge>
              <span class="text-xs text-gray-500 dark:text-gray-400">CII: {{ item.cii.toFixed(1) }}</span>
              <button
                class="inline-flex items-center gap-0.5 text-xs text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300"
                @click="openPostListModal(`${item.author} 的帖子`, [item.post_id])"
              >
                <UIcon name="i-heroicons-arrow-top-right-on-square" class="w-3 h-3" />
                原文
              </button>
            </div>
          </div>
          <p class="text-sm text-gray-600 dark:text-gray-400">{{ item.summary }}</p>
        </div>
      </div>
    </section>

    <!-- 帖子列表弹窗 -->
    <PostListModal
      v-model:open="postListModalOpen"
      :task-id="taskId"
      :post-ids="postListModalPostIds"
      :title="postListModalTitle"
    />
  </div>
</template>
