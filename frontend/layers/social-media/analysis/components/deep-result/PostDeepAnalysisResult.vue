<script setup lang="ts">
import type { PostDeepResult } from '../../types'

defineProps<{
  data: PostDeepResult
}>()

const getSentimentColor = (sentiment: number) => {
  if (sentiment > 0) return 'success'
  if (sentiment < 0) return 'error'
  return 'neutral'
}

const getSentimentLabel = (sentiment: number) => {
  if (sentiment > 0) return '正面'
  if (sentiment < 0) return '负面'
  return '中性'
}

// 后端直接返回中文类型，无需映射
const getEntityTypeLabel = (type: string) => {
  return type
}
</script>

<template>
  <div class="space-y-4">
    <!-- 摘要 -->
    <div class="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
      <h4 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">内容摘要</h4>
      <p class="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
        {{ data.summary }}
      </p>
    </div>

    <!-- 实体信息 -->
    <div v-if="data.entities && data.entities.length > 0">
      <h4 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">识别实体</h4>
      <div class="space-y-2">
        <div
          v-for="(entity, index) in data.entities"
          :key="index"
          class="border border-gray-200 dark:border-gray-700 rounded-lg p-2.5"
        >
          <div class="flex justify-between items-center mb-1.5">
            <div class="flex items-center gap-1.5">
              <span class="font-medium text-sm text-gray-900 dark:text-white">{{ entity.name }}</span>
              <UBadge variant="subtle" size="sm">{{ getEntityTypeLabel(entity.type) }}</UBadge>
            </div>
            <UBadge :color="getSentimentColor(entity.sentiment)" variant="subtle">
              {{ getSentimentLabel(entity.sentiment) }}
            </UBadge>
          </div>

          <div class="space-y-1 text-sm">
            <div v-if="entity.features?.length" class="flex flex-wrap items-baseline gap-x-3">
              <span class="font-medium text-gray-500 dark:text-gray-400 shrink-0">特性：</span>
              <span v-for="f in entity.features" :key="f" class="text-gray-700 dark:text-gray-300">{{ f }}</span>
            </div>
            <div v-if="entity.issues?.length" class="flex flex-wrap items-baseline gap-x-3">
              <span class="font-medium text-red-500 dark:text-red-400 shrink-0">问题：</span>
              <span v-for="i in entity.issues" :key="i" class="text-gray-700 dark:text-gray-300">{{ i }}</span>
            </div>
            <div v-if="entity.expectations?.length" class="flex flex-wrap items-baseline gap-x-3">
              <span class="font-medium text-blue-500 dark:text-blue-400 shrink-0">期望：</span>
              <span v-for="e in entity.expectations" :key="e" class="text-gray-700 dark:text-gray-300">{{ e }}</span>
            </div>
            <div v-if="entity.audience?.length" class="flex flex-wrap items-baseline gap-x-3">
              <span class="font-medium text-purple-500 dark:text-purple-400 shrink-0">受众：</span>
              <span v-for="a in entity.audience" :key="a" class="text-gray-700 dark:text-gray-300">{{ a }}</span>
            </div>
            <div v-if="entity.scenarios?.length" class="flex flex-wrap items-baseline gap-x-3">
              <span class="font-medium text-cyan-500 dark:text-cyan-400 shrink-0">场景：</span>
              <span v-for="s in entity.scenarios" :key="s" class="text-gray-700 dark:text-gray-300">{{ s }}</span>
            </div>
            <div v-if="entity.market_factors?.length" class="flex flex-wrap items-baseline gap-x-3">
              <span class="font-medium text-amber-500 dark:text-amber-400 shrink-0">市场：</span>
              <span v-for="m in entity.market_factors" :key="m" class="text-gray-700 dark:text-gray-300">{{ m }}</span>
            </div>
            <div v-if="entity.competitors?.length" class="flex flex-wrap items-baseline gap-x-3">
              <span class="font-medium text-orange-500 dark:text-orange-400 shrink-0">竞品：</span>
              <span v-for="c in entity.competitors" :key="c" class="text-gray-700 dark:text-gray-300">{{ c }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 通用观点 -->
    <div v-if="data.general_opinions && data.general_opinions.length > 0">
      <h4 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">通用观点</h4>
      <div class="space-y-2">
        <div
          v-for="(opinion, index) in data.general_opinions"
          :key="index"
          class="border border-gray-200 dark:border-gray-700 rounded-lg p-2.5"
        >
          <div class="flex justify-between items-center mb-1.5">
            <span class="text-sm font-medium text-gray-700 dark:text-gray-300">{{ opinion.category }}</span>
            <UBadge :color="getSentimentColor(opinion.sentiment)" variant="subtle">
              {{ getSentimentLabel(opinion.sentiment) }}
            </UBadge>
          </div>
          <div class="text-sm text-gray-600 dark:text-gray-400">
            <p v-for="(op, idx) in opinion.opinions" :key="idx">{{ op }}</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>


