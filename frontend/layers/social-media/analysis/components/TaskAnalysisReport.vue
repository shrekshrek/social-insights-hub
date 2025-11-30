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

/** 获取情感标签 */
const getSentimentLabel = (sentiment: number) => {
  if (sentiment >= 1.5) return '强烈正面'
  if (sentiment >= 0.5) return '正面'
  if (sentiment >= -0.5) return '中性'
  if (sentiment >= -1.5) return '负面'
  return '强烈负面'
}

/** 获取情感颜色 */
const getSentimentColor = (sentiment: number) => {
  if (sentiment >= 0.5) return 'success'
  if (sentiment >= -0.5) return 'neutral'
  return 'error'
}
</script>

<template>
  <div class="space-y-6">
    <!-- 核心指标卡片 -->
    <section>
      <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">核心指标</h3>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
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
      </div>
    </section>

    <!-- 四象限统计 -->
    <section>
      <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">舆情四象限分布</h3>
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
      <div class="overflow-x-auto bg-gray-50 dark:bg-gray-800 rounded-lg">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-gray-200 dark:border-gray-700">
              <th class="text-left py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">实体</th>
              <th class="text-left py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">类型</th>
              <th class="text-left py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">角色</th>
              <th class="text-right py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">热度</th>
              <th class="text-right py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">提及</th>
              <th class="text-center py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">情感</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="entity in data.insights.top_entities.slice(0, 10)"
              :key="entity.name"
              class="border-b border-gray-100 dark:border-gray-700/50"
            >
              <td class="py-2 px-3 font-medium text-gray-900 dark:text-white">{{ entity.name }}</td>
              <td class="py-2 px-3">
                <UBadge color="neutral" variant="subtle" size="xs">{{ entity.type }}</UBadge>
              </td>
              <td class="py-2 px-3">
                <UBadge
                  :color="entity.role === 'target' ? 'primary' : entity.role === 'competitor' ? 'warning' : 'neutral'"
                  variant="subtle"
                  size="xs"
                >
                  {{ entity.role === 'target' ? '本品' : entity.role === 'competitor' ? '竞品' : '其他' }}
                </UBadge>
              </td>
              <td class="py-2 px-3 text-right font-mono text-gray-700 dark:text-gray-300">{{ entity.heat.toFixed(1) }}</td>
              <td class="py-2 px-3 text-right text-gray-700 dark:text-gray-300">{{ entity.mentions }}</td>
              <td class="py-2 px-3 text-center">
                <UBadge :color="getSentimentColor(entity.avg_sentiment)" variant="subtle" size="xs">
                  {{ entity.avg_sentiment >= 0 ? '+' : '' }}{{ entity.avg_sentiment.toFixed(2) }}
                </UBadge>
              </td>
            </tr>
          </tbody>
        </table>
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
              class="flex items-center justify-between text-sm"
            >
              <span class="truncate text-gray-700 dark:text-gray-300">{{ item.label }}</span>
              <span class="text-gray-500 dark:text-gray-400 font-mono">{{ item.mentions }}</span>
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
              class="flex items-center justify-between text-sm"
            >
              <span class="truncate text-gray-700 dark:text-gray-300">{{ item.label }}</span>
              <span class="text-gray-500 dark:text-gray-400 font-mono">{{ item.mentions }}</span>
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
              class="flex items-center justify-between text-sm"
            >
              <span class="truncate text-gray-700 dark:text-gray-300">{{ item.label }}</span>
              <span class="text-gray-500 dark:text-gray-400 font-mono">{{ item.mentions }}</span>
            </div>
          </div>
          <p v-else class="text-sm text-gray-400 dark:text-gray-500">暂无数据</p>
        </div>
      </div>
    </section>

    <!-- KOL 声音 -->
    <section v-if="data.insights.kol_voices.length > 0">
      <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">KOL 声音 TOP 5</h3>
      <div class="space-y-3">
        <div
          v-for="kol in data.insights.kol_voices.slice(0, 5)"
          :key="kol.post_id"
          class="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg"
        >
          <div class="flex items-center justify-between mb-2">
            <div class="flex items-center gap-2">
              <UIcon name="i-heroicons-user-circle" class="w-5 h-5 text-gray-400" />
              <span class="font-medium text-gray-900 dark:text-white">{{ kol.author }}</span>
            </div>
            <div class="flex items-center gap-2">
              <UBadge :color="getSentimentColor(kol.sentiment)" variant="subtle" size="xs">
                {{ getSentimentLabel(kol.sentiment) }}
              </UBadge>
              <span class="text-xs text-gray-500 dark:text-gray-400">CII: {{ kol.cii.toFixed(1) }}</span>
            </div>
          </div>
          <p class="text-sm text-gray-600 dark:text-gray-400">{{ kol.summary }}</p>
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
