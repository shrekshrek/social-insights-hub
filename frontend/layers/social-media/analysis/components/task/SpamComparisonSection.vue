<script setup lang="ts">
/**
 * 广告/有机内容对比分析组件
 *
 * 双列展示高广告 vs 低广告的原文/评论深度分析对比
 */
import { ref } from 'vue'
import type { SpamComparison, SpamComparisonGroup } from '../../types'
import TabSwitch from '../shared/TabSwitch.vue'

defineProps<{
  data: SpamComparison
}>()

// 左右两列各自的 Tab 状态
const highSpamTab = ref<'post' | 'comment'>('post')
const lowSpamTab = ref<'post' | 'comment'>('post')

const tabOptions = [
  { value: 'post', label: '原文分析' },
  { value: 'comment', label: '评论分析' },
]

/** 获取当前 Tab 对应的数据块 */
const getBlock = (group: SpamComparisonGroup, tab: 'post' | 'comment') => {
  return tab === 'post' ? group.post_analysis : group.comment_analysis
}

/** 情感标签 */
const getSentimentLabel = (s: number) => {
  if (s >= 0.5) return '正面'
  if (s > 0) return '偏正面'
  if (s === 0) return '中性'
  if (s > -0.5) return '偏负面'
  return '负面'
}

/** 情感颜色 */
const getSentimentColor = (s: number) => {
  if (s > 0) return 'success'
  if (s === 0) return 'neutral'
  return 'error'
}
</script>

<template>
  <section>
    <div class="flex items-center gap-2 mb-3">
      <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300">广告/有机内容对比</h3>
      <UBadge color="neutral" variant="subtle" size="xs">
        广告阈值 {{ data.config.threshold }}
      </UBadge>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <!-- 左列：高广告 -->
      <div class="border border-orange-200 dark:border-orange-800/40 rounded-lg overflow-hidden">
        <!-- 头部 -->
        <div class="px-4 py-2.5 bg-orange-50 dark:bg-orange-900/20 flex items-center justify-between">
          <div class="flex items-center gap-2">
            <span class="w-2 h-2 rounded-full bg-orange-500" />
            <span class="text-sm font-medium text-gray-900 dark:text-white">高广告内容</span>
            <span class="text-xs text-gray-500 dark:text-gray-400">
              {{ data.high_spam.post_count }} 条
            </span>
          </div>
          <TabSwitch v-model="highSpamTab" :options="tabOptions" />
        </div>

        <!-- 指标 -->
        <div class="px-4 py-2 flex items-center gap-4 text-xs border-b border-orange-100 dark:border-orange-800/30 bg-orange-50/50 dark:bg-orange-900/10">
          <span class="text-gray-500 dark:text-gray-400">
            CII <span class="font-mono font-medium text-gray-700 dark:text-gray-300">{{ data.high_spam.metrics.avg_cii.toFixed(1) }}</span>
          </span>
          <span class="text-gray-500 dark:text-gray-400">
            情感 <span class="font-mono font-medium text-gray-700 dark:text-gray-300">{{ data.high_spam.metrics.avg_sentiment.toFixed(2) }}</span>
          </span>
          <span class="text-gray-500 dark:text-gray-400">
            深度 <span class="font-mono font-medium text-gray-700 dark:text-gray-300">{{ data.high_spam.deep_analyzed_count }}</span>
          </span>
          <span class="text-gray-500 dark:text-gray-400">
            评论 <span class="font-mono font-medium text-gray-700 dark:text-gray-300">{{ data.high_spam.comment_analyzed_count }}</span>
          </span>
        </div>

        <!-- 内容 -->
        <div class="p-4 space-y-4">
          <!-- 实体列表 -->
          <div>
            <p class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">Top 实体</p>
            <div v-if="getBlock(data.high_spam, highSpamTab).top_entities.length" class="space-y-2">
              <div
                v-for="entity in getBlock(data.high_spam, highSpamTab).top_entities.slice(0, 5)"
                :key="entity.name"
                class="flex items-start justify-between gap-2 text-sm"
              >
                <div class="flex items-center gap-1.5 min-w-0">
                  <span class="font-medium text-gray-900 dark:text-white truncate">{{ entity.name }}</span>
                  <UBadge color="neutral" variant="subtle" size="xs">{{ entity.type }}</UBadge>
                </div>
                <div class="flex items-center gap-2 shrink-0 text-xs">
                  <span class="text-gray-400">{{ entity.mentions }}次</span>
                  <UBadge :color="getSentimentColor(entity.sentiment)" variant="subtle" size="xs">
                    {{ getSentimentLabel(entity.sentiment) }}
                  </UBadge>
                </div>
              </div>
              <!-- 特性/问题摘要（取第一个实体的） -->
              <div
                v-for="entity in getBlock(data.high_spam, highSpamTab).top_entities.slice(0, 3)"
                :key="'detail-' + entity.name"
                class="text-xs text-gray-500 dark:text-gray-400 pl-1"
              >
                <span v-if="entity.top_features.length" class="text-green-600 dark:text-green-400">
                  {{ entity.name }}特性: {{ entity.top_features.slice(0, 3).join('、') }}
                </span>
                <span v-if="entity.top_features.length && entity.top_issues.length" class="mx-1">|</span>
                <span v-if="entity.top_issues.length" class="text-red-600 dark:text-red-400">
                  问题: {{ entity.top_issues.slice(0, 3).join('、') }}
                </span>
              </div>
            </div>
            <p v-else class="text-xs text-gray-400">暂无数据</p>
          </div>

          <!-- 观点列表 -->
          <div>
            <p class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">Top 观点</p>
            <div v-if="getBlock(data.high_spam, highSpamTab).top_opinions.length" class="space-y-2">
              <div
                v-for="opinion in getBlock(data.high_spam, highSpamTab).top_opinions.slice(0, 5)"
                :key="opinion.category"
                class="text-sm"
              >
                <div class="flex items-center justify-between gap-2">
                  <span class="text-gray-900 dark:text-white">{{ opinion.category }}</span>
                  <div class="flex items-center gap-2 text-xs">
                    <span class="text-gray-400">{{ opinion.mentions }}次</span>
                    <UBadge :color="getSentimentColor(opinion.sentiment)" variant="subtle" size="xs">
                      {{ getSentimentLabel(opinion.sentiment) }}
                    </UBadge>
                  </div>
                </div>
                <p v-if="opinion.sample_opinions.length" class="text-xs text-gray-500 dark:text-gray-400 mt-0.5 line-clamp-1">
                  {{ opinion.sample_opinions.slice(0, 2).join('；') }}
                </p>
              </div>
            </div>
            <p v-else class="text-xs text-gray-400">暂无数据</p>
          </div>
        </div>
      </div>

      <!-- 右列：低广告 -->
      <div class="border border-emerald-200 dark:border-emerald-800/40 rounded-lg overflow-hidden">
        <!-- 头部 -->
        <div class="px-4 py-2.5 bg-emerald-50 dark:bg-emerald-900/20 flex items-center justify-between">
          <div class="flex items-center gap-2">
            <span class="w-2 h-2 rounded-full bg-emerald-500" />
            <span class="text-sm font-medium text-gray-900 dark:text-white">有机内容</span>
            <span class="text-xs text-gray-500 dark:text-gray-400">
              {{ data.low_spam.post_count }} 条
            </span>
          </div>
          <TabSwitch v-model="lowSpamTab" :options="tabOptions" />
        </div>

        <!-- 指标 -->
        <div class="px-4 py-2 flex items-center gap-4 text-xs border-b border-emerald-100 dark:border-emerald-800/30 bg-emerald-50/50 dark:bg-emerald-900/10">
          <span class="text-gray-500 dark:text-gray-400">
            CII <span class="font-mono font-medium text-gray-700 dark:text-gray-300">{{ data.low_spam.metrics.avg_cii.toFixed(1) }}</span>
          </span>
          <span class="text-gray-500 dark:text-gray-400">
            情感 <span class="font-mono font-medium text-gray-700 dark:text-gray-300">{{ data.low_spam.metrics.avg_sentiment.toFixed(2) }}</span>
          </span>
          <span class="text-gray-500 dark:text-gray-400">
            深度 <span class="font-mono font-medium text-gray-700 dark:text-gray-300">{{ data.low_spam.deep_analyzed_count }}</span>
          </span>
          <span class="text-gray-500 dark:text-gray-400">
            评论 <span class="font-mono font-medium text-gray-700 dark:text-gray-300">{{ data.low_spam.comment_analyzed_count }}</span>
          </span>
        </div>

        <!-- 内容 -->
        <div class="p-4 space-y-4">
          <!-- 实体列表 -->
          <div>
            <p class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">Top 实体</p>
            <div v-if="getBlock(data.low_spam, lowSpamTab).top_entities.length" class="space-y-2">
              <div
                v-for="entity in getBlock(data.low_spam, lowSpamTab).top_entities.slice(0, 5)"
                :key="entity.name"
                class="flex items-start justify-between gap-2 text-sm"
              >
                <div class="flex items-center gap-1.5 min-w-0">
                  <span class="font-medium text-gray-900 dark:text-white truncate">{{ entity.name }}</span>
                  <UBadge color="neutral" variant="subtle" size="xs">{{ entity.type }}</UBadge>
                </div>
                <div class="flex items-center gap-2 shrink-0 text-xs">
                  <span class="text-gray-400">{{ entity.mentions }}次</span>
                  <UBadge :color="getSentimentColor(entity.sentiment)" variant="subtle" size="xs">
                    {{ getSentimentLabel(entity.sentiment) }}
                  </UBadge>
                </div>
              </div>
              <!-- 特性/问题摘要 -->
              <div
                v-for="entity in getBlock(data.low_spam, lowSpamTab).top_entities.slice(0, 3)"
                :key="'detail-' + entity.name"
                class="text-xs text-gray-500 dark:text-gray-400 pl-1"
              >
                <span v-if="entity.top_features.length" class="text-green-600 dark:text-green-400">
                  {{ entity.name }}特性: {{ entity.top_features.slice(0, 3).join('、') }}
                </span>
                <span v-if="entity.top_features.length && entity.top_issues.length" class="mx-1">|</span>
                <span v-if="entity.top_issues.length" class="text-red-600 dark:text-red-400">
                  问题: {{ entity.top_issues.slice(0, 3).join('、') }}
                </span>
              </div>
            </div>
            <p v-else class="text-xs text-gray-400">暂无数据</p>
          </div>

          <!-- 观点列表 -->
          <div>
            <p class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">Top 观点</p>
            <div v-if="getBlock(data.low_spam, lowSpamTab).top_opinions.length" class="space-y-2">
              <div
                v-for="opinion in getBlock(data.low_spam, lowSpamTab).top_opinions.slice(0, 5)"
                :key="opinion.category"
                class="text-sm"
              >
                <div class="flex items-center justify-between gap-2">
                  <span class="text-gray-900 dark:text-white">{{ opinion.category }}</span>
                  <div class="flex items-center gap-2 text-xs">
                    <span class="text-gray-400">{{ opinion.mentions }}次</span>
                    <UBadge :color="getSentimentColor(opinion.sentiment)" variant="subtle" size="xs">
                      {{ getSentimentLabel(opinion.sentiment) }}
                    </UBadge>
                  </div>
                </div>
                <p v-if="opinion.sample_opinions.length" class="text-xs text-gray-500 dark:text-gray-400 mt-0.5 line-clamp-1">
                  {{ opinion.sample_opinions.slice(0, 2).join('；') }}
                </p>
              </div>
            </div>
            <p v-else class="text-xs text-gray-400">暂无数据</p>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
