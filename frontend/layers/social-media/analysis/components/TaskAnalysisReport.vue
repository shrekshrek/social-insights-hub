<script setup lang="ts">
import type { TaskAnalysisResultData } from '../types'

defineProps<{
  data: TaskAnalysisResultData
}>()

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
</script>

<template>
  <div class="space-y-6">
    <!-- 分析概览：元数据 + 数据量统计 -->
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
        <!-- 右侧：数据量统计 -->
        <div class="flex items-center gap-4 text-sm">
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
        <UTooltip text="横轴: 情感值 (正/负)，纵轴: CII互动指数 (高/低)，以均值为分界">
          <UIcon name="i-heroicons-question-mark-circle" class="w-4 h-4 text-gray-400" />
        </UTooltip>
      </div>
      <div class="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
        <div class="grid grid-cols-2 md:grid-cols-5 gap-3">
          <div class="text-center p-3 bg-red-50 dark:bg-red-900/20 rounded">
            <p class="text-xl font-bold text-red-600 dark:text-red-400">{{ data.charts.quadrant_summary.Q1_danger }}</p>
            <p class="text-xs text-gray-600 dark:text-gray-400">爆雷区</p>
            <p class="text-xs text-gray-400 dark:text-gray-500">高互动/负面</p>
          </div>
          <div class="text-center p-3 bg-green-50 dark:bg-green-900/20 rounded">
            <p class="text-xl font-bold text-green-600 dark:text-green-400">{{ data.charts.quadrant_summary.Q2_brand }}</p>
            <p class="text-xs text-gray-600 dark:text-gray-400">品牌区</p>
            <p class="text-xs text-gray-400 dark:text-gray-500">高互动/正面</p>
          </div>
          <div class="text-center p-3 bg-orange-50 dark:bg-orange-900/20 rounded">
            <p class="text-xl font-bold text-orange-600 dark:text-orange-400">{{ data.charts.quadrant_summary.Q3_complaint }}</p>
            <p class="text-xs text-gray-600 dark:text-gray-400">吐槽区</p>
            <p class="text-xs text-gray-400 dark:text-gray-500">低互动/负面</p>
          </div>
          <div class="text-center p-3 bg-blue-50 dark:bg-blue-900/20 rounded">
            <p class="text-xl font-bold text-blue-600 dark:text-blue-400">{{ data.charts.quadrant_summary.Q4_niche }}</p>
            <p class="text-xs text-gray-600 dark:text-gray-400">自嗨区</p>
            <p class="text-xs text-gray-400 dark:text-gray-500">低互动/正面</p>
          </div>
          <div class="text-center p-3 bg-gray-100 dark:bg-gray-700 rounded">
            <p class="text-xl font-bold text-gray-600 dark:text-gray-300">{{ data.charts.quadrant_summary.neutral }}</p>
            <p class="text-xs text-gray-600 dark:text-gray-400">中性区</p>
            <p class="text-xs text-gray-400 dark:text-gray-500">情感中立</p>
          </div>
        </div>
      </div>
    </section>

    <!-- 实体排行 -->
    <section v-if="data.insights.top_entities.length > 0">
      <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">热门实体 TOP 10</h3>
      <div class="space-y-2">
        <div
          v-for="entity in data.insights.top_entities.slice(0, 10)"
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
            <div class="flex items-center gap-3 text-sm">
              <span class="text-gray-500 dark:text-gray-400">
                热度 <span class="font-mono text-gray-700 dark:text-gray-300">{{ entity.heat.toFixed(1) }}</span>
              </span>
              <span class="text-gray-500 dark:text-gray-400">
                提及 <span class="text-gray-700 dark:text-gray-300">{{ entity.mentions }}</span>
              </span>
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

    <!-- 热门观点：问题 vs 特性 -->
    <section v-if="data.insights.top_issues?.length || data.insights.top_features?.length">
      <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">热门观点</h3>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <!-- 热门问题（负面观点） -->
        <div class="p-4 bg-red-50 dark:bg-red-900/10 rounded-lg border border-red-100 dark:border-red-900/30">
          <div class="flex items-center gap-2 mb-3">
            <UIcon name="i-heroicons-exclamation-triangle" class="w-5 h-5 text-red-500" />
            <span class="font-medium text-gray-900 dark:text-white">热门问题</span>
            <span class="text-xs text-gray-400">(负面观点)</span>
          </div>
          <div v-if="data.insights.top_issues?.length" class="space-y-3">
            <div
              v-for="issue in data.insights.top_issues.slice(0, 5)"
              :key="issue.topic"
              class="text-sm"
            >
              <div class="flex items-center justify-between mb-1">
                <span class="font-medium text-gray-800 dark:text-gray-200">{{ issue.topic }}</span>
                <div class="flex items-center gap-2">
                  <span class="text-xs text-gray-400">{{ issue.mentions }}次</span>
                  <span class="text-xs text-gray-400">热度 {{ issue.heat.toFixed(0) }}</span>
                </div>
              </div>
              <p v-if="issue.summary" class="text-xs text-gray-600 dark:text-gray-400 mb-1">{{ issue.summary }}</p>
              <div class="flex items-center gap-2 text-xs text-gray-400">
                <span>来源: 帖子{{ (issue.source_distribution?.post * 100 || 0).toFixed(0) }}% / 评论{{ (issue.source_distribution?.comment * 100 || 0).toFixed(0) }}%</span>
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
          <div v-if="data.insights.top_features?.length" class="space-y-3">
            <div
              v-for="feature in data.insights.top_features.slice(0, 5)"
              :key="feature.topic"
              class="text-sm"
            >
              <div class="flex items-center justify-between mb-1">
                <span class="font-medium text-gray-800 dark:text-gray-200">{{ feature.topic }}</span>
                <div class="flex items-center gap-2">
                  <span class="text-xs text-gray-400">{{ feature.mentions }}次</span>
                  <span class="text-xs text-gray-400">热度 {{ feature.heat.toFixed(0) }}</span>
                </div>
              </div>
              <p v-if="feature.summary" class="text-xs text-gray-600 dark:text-gray-400 mb-1">{{ feature.summary }}</p>
              <div class="flex items-center gap-2 text-xs text-gray-400">
                <span>来源: 帖子{{ (feature.source_distribution?.post * 100 || 0).toFixed(0) }}% / 评论{{ (feature.source_distribution?.comment * 100 || 0).toFixed(0) }}%</span>
              </div>
            </div>
          </div>
          <p v-else class="text-sm text-gray-400">暂无数据</p>
        </div>
      </div>
    </section>

    <!-- 竞品分析 -->
    <section v-if="data.insights.competition?.competitor_details?.length">
      <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">竞品分析</h3>
      <div class="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
        <!-- 情感对比概览 -->
        <div class="flex items-center justify-center gap-8 mb-4 pb-4 border-b border-gray-200 dark:border-gray-700">
          <div class="text-center">
            <p class="text-xs text-gray-500 mb-1">本品情感</p>
            <UBadge :color="getSentimentColor(data.insights.competition.target_sentiment)" variant="subtle">
              {{ data.insights.competition.target_sentiment >= 0 ? '+' : '' }}{{ data.insights.competition.target_sentiment.toFixed(2) }}
            </UBadge>
          </div>
          <div class="text-center">
            <p class="text-xs text-gray-500 mb-1">对比优势</p>
            <UBadge :color="data.insights.competition.comparison_sentiment >= 0 ? 'success' : 'error'" variant="subtle">
              {{ data.insights.competition.comparison_sentiment >= 0 ? '+' : '' }}{{ data.insights.competition.comparison_sentiment.toFixed(2) }}
            </UBadge>
          </div>
          <div class="text-center">
            <p class="text-xs text-gray-500 mb-1">竞品情感</p>
            <UBadge :color="getSentimentColor(data.insights.competition.competitor_sentiment)" variant="subtle">
              {{ data.insights.competition.competitor_sentiment >= 0 ? '+' : '' }}{{ data.insights.competition.competitor_sentiment.toFixed(2) }}
            </UBadge>
          </div>
        </div>
        <!-- 竞品详情 -->
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          <div
            v-for="comp in data.insights.competition.competitor_details.slice(0, 6)"
            :key="comp.name"
            class="p-3 bg-white dark:bg-gray-700 rounded border border-gray-200 dark:border-gray-600"
          >
            <div class="flex items-center justify-between mb-2">
              <span class="font-medium text-gray-900 dark:text-white">{{ comp.name }}</span>
              <UBadge :color="getSentimentColor(comp.sentiment)" variant="subtle" size="xs">
                {{ getSentimentLabel(comp.sentiment) }}
              </UBadge>
            </div>
            <div class="flex items-center gap-3 text-xs text-gray-500 mb-2">
              <span>热度 {{ comp.heat.toFixed(0) }}</span>
              <span>提及 {{ comp.mentions }}</span>
            </div>
            <div v-if="comp.top_features?.length" class="text-xs mb-1">
              <span class="text-green-600 dark:text-green-400">优点:</span>
              <span class="text-gray-600 dark:text-gray-400">{{ comp.top_features.slice(0, 2).join('、') }}</span>
            </div>
            <div v-if="comp.top_issues?.length" class="text-xs">
              <span class="text-red-600 dark:text-red-400">问题:</span>
              <span class="text-gray-600 dark:text-gray-400">{{ comp.top_issues.slice(0, 2).join('、') }}</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 场景与人群画像 -->
    <section v-if="data.insights.context_analysis?.scenarios?.length || data.insights.context_analysis?.audiences?.length">
      <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">场景与人群画像</h3>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <!-- 使用场景 -->
        <div class="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
          <div class="flex items-center gap-2 mb-3">
            <UIcon name="i-heroicons-map-pin" class="w-5 h-5 text-indigo-500" />
            <span class="font-medium text-gray-900 dark:text-white">使用场景</span>
          </div>
          <div v-if="data.insights.context_analysis?.scenarios?.length" class="space-y-3">
            <div
              v-for="scenario in data.insights.context_analysis.scenarios.slice(0, 5)"
              :key="scenario.label"
              class="text-sm"
            >
              <div class="flex items-center justify-between mb-1">
                <span class="font-medium text-gray-800 dark:text-gray-200">{{ scenario.label }}</span>
                <div class="flex items-center gap-2 text-xs text-gray-400">
                  <span>热度 {{ scenario.heat.toFixed(0) }}</span>
                  <span>{{ scenario.mentions }}次</span>
                </div>
              </div>
              <div v-if="scenario.associated_features?.length" class="text-xs text-green-600 dark:text-green-400">
                关联特性: {{ scenario.associated_features.slice(0, 3).join('、') }}
              </div>
              <div v-if="scenario.associated_issues?.length" class="text-xs text-red-600 dark:text-red-400">
                关联问题: {{ scenario.associated_issues.slice(0, 3).join('、') }}
              </div>
            </div>
          </div>
          <p v-else class="text-sm text-gray-400">暂无数据</p>
        </div>

        <!-- 目标人群 -->
        <div class="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
          <div class="flex items-center gap-2 mb-3">
            <UIcon name="i-heroicons-user-group" class="w-5 h-5 text-purple-500" />
            <span class="font-medium text-gray-900 dark:text-white">目标人群</span>
          </div>
          <div v-if="data.insights.context_analysis?.audiences?.length" class="space-y-3">
            <div
              v-for="audience in data.insights.context_analysis.audiences.slice(0, 5)"
              :key="audience.label"
              class="text-sm"
            >
              <div class="flex items-center justify-between mb-1">
                <span class="font-medium text-gray-800 dark:text-gray-200">{{ audience.label }}</span>
                <div class="flex items-center gap-2 text-xs text-gray-400">
                  <span>热度 {{ audience.heat.toFixed(0) }}</span>
                  <span>{{ audience.mentions }}次</span>
                </div>
              </div>
              <div v-if="audience.preferences?.length" class="text-xs text-blue-600 dark:text-blue-400">
                偏好: {{ audience.preferences.slice(0, 4).join('、') }}
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
          <div v-if="data.insights.opportunities.kano_model.must_be.length" class="space-y-2">
            <div
              v-for="item in data.insights.opportunities.kano_model.must_be.slice(0, 5)"
              :key="item.label"
              class="text-sm"
            >
              <div class="flex items-center justify-between">
                <span class="truncate text-gray-700 dark:text-gray-300">{{ item.label }}</span>
                <div class="flex items-center gap-2 shrink-0">
                  <span class="text-xs text-gray-400 dark:text-gray-500">{{ item.mentions }}次</span>
                  <UBadge :color="getSentimentColor(item.sentiment)" variant="subtle" size="xs">
                    {{ item.sentiment >= 0 ? '+' : '' }}{{ item.sentiment.toFixed(1) }}
                  </UBadge>
                </div>
              </div>
              <div class="mt-1">
                <UProgress :model-value="item.heat" :max="Math.max(...data.insights.opportunities.kano_model.must_be.map(i => i.heat))" size="xs" color="error" />
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
          <div v-if="data.insights.opportunities.kano_model.one_dimensional.length" class="space-y-2">
            <div
              v-for="item in data.insights.opportunities.kano_model.one_dimensional.slice(0, 5)"
              :key="item.label"
              class="text-sm"
            >
              <div class="flex items-center justify-between">
                <span class="truncate text-gray-700 dark:text-gray-300">{{ item.label }}</span>
                <div class="flex items-center gap-2 shrink-0">
                  <span class="text-xs text-gray-400 dark:text-gray-500">{{ item.mentions }}次</span>
                  <UBadge :color="getSentimentColor(item.sentiment)" variant="subtle" size="xs">
                    {{ item.sentiment >= 0 ? '+' : '' }}{{ item.sentiment.toFixed(1) }}
                  </UBadge>
                </div>
              </div>
              <div class="mt-1">
                <UProgress :model-value="item.heat" :max="Math.max(...data.insights.opportunities.kano_model.one_dimensional.map(i => i.heat))" size="xs" color="info" />
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
          <div v-if="data.insights.opportunities.kano_model.attractive.length" class="space-y-2">
            <div
              v-for="item in data.insights.opportunities.kano_model.attractive.slice(0, 5)"
              :key="item.label"
              class="text-sm"
            >
              <div class="flex items-center justify-between">
                <span class="truncate text-gray-700 dark:text-gray-300">{{ item.label }}</span>
                <div class="flex items-center gap-2 shrink-0">
                  <span class="text-xs text-gray-400 dark:text-gray-500">{{ item.mentions }}次</span>
                  <UBadge :color="getSentimentColor(item.sentiment)" variant="subtle" size="xs">
                    {{ item.sentiment >= 0 ? '+' : '' }}{{ item.sentiment.toFixed(1) }}
                  </UBadge>
                </div>
              </div>
              <div class="mt-1">
                <UProgress :model-value="item.heat" :max="Math.max(...data.insights.opportunities.kano_model.attractive.map(i => i.heat))" size="xs" color="success" />
              </div>
            </div>
          </div>
          <p v-else class="text-sm text-gray-400 dark:text-gray-500">暂无数据</p>
        </div>
      </div>
    </section>

    <!-- 高影响力内容 -->
    <section v-if="data.insights.kol_voices.length > 0">
      <div class="flex items-center gap-2 mb-3">
        <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300">高影响力内容 TOP 5</h3>
        <UTooltip text="按互动指数(CII)排名的高影响力帖子">
          <UIcon name="i-heroicons-question-mark-circle" class="w-4 h-4 text-gray-400" />
        </UTooltip>
      </div>
      <div class="space-y-3">
        <div
          v-for="item in data.insights.kol_voices.slice(0, 5)"
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
            </div>
          </div>
          <p class="text-sm text-gray-600 dark:text-gray-400">{{ item.summary }}</p>
        </div>
      </div>
    </section>

    <!-- 数据新鲜度 -->
    <section>
      <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">数据新鲜度</h3>
      <div class="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
        <div class="grid grid-cols-3 gap-4 text-center">
          <div>
            <p class="text-lg font-bold text-gray-900 dark:text-white">{{ formatPercent(data.freshness.last_7_days) }}</p>
            <p class="text-xs text-gray-500 dark:text-gray-400">近7天</p>
          </div>
          <div>
            <p class="text-lg font-bold text-gray-900 dark:text-white">{{ formatPercent(data.freshness.last_30_days) }}</p>
            <p class="text-xs text-gray-500 dark:text-gray-400">近30天</p>
          </div>
          <div>
            <p class="text-lg font-bold text-gray-900 dark:text-white">{{ data.freshness.avg_age_days.toFixed(0) }}天</p>
            <p class="text-xs text-gray-500 dark:text-gray-400">平均发布天数</p>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
