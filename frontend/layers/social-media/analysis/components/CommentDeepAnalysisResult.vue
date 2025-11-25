<script setup lang="ts">
import type { CommentDeepResult } from '../types'

defineProps<{
  data: CommentDeepResult
}>()

const getSentimentColor = (sentiment: number) => {
  if (sentiment > 0) return 'green'
  if (sentiment < 0) return 'red'
  return 'gray'
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
  <div class="space-y-6">
    <!-- 实体信息 -->
    <div v-if="data.entities && data.entities.length > 0">
      <h4 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">识别到的实体</h4>
      <div class="grid gap-4 md:grid-cols-2">
        <UCard v-for="(entity, index) in data.entities" :key="index" :ui="{ body: { padding: 'p-3' } }">
          <div class="flex justify-between items-start mb-2">
            <div class="flex items-center gap-2">
              <span class="font-medium text-gray-900 dark:text-white">{{ entity.name }}</span>
              <UBadge variant="soft" size="xs">{{ getEntityTypeLabel(entity.type) }}</UBadge>
            </div>
            <UBadge :color="getSentimentColor(entity.sentiment)" size="xs" variant="subtle">
              {{ getSentimentLabel(entity.sentiment) }}
            </UBadge>
          </div>

          <div class="space-y-2 text-xs">
            <div v-if="entity.features?.length">
              <span class="text-gray-500">特性:</span>
              <div class="flex flex-wrap gap-1 mt-1">
                <UBadge v-for="f in entity.features" :key="f" color="gray" variant="soft" size="xs">{{ f }}</UBadge>
              </div>
            </div>

            <div v-if="entity.issues?.length">
              <span class="text-red-500">问题:</span>
              <div class="flex flex-wrap gap-1 mt-1">
                <UBadge v-for="i in entity.issues" :key="i" color="red" variant="soft" size="xs">{{ i }}</UBadge>
              </div>
            </div>
            
            <div v-if="entity.expectations?.length">
              <span class="text-blue-500">期望:</span>
              <div class="flex flex-wrap gap-1 mt-1">
                <UBadge v-for="e in entity.expectations" :key="e" color="blue" variant="soft" size="xs">{{ e }}</UBadge>
              </div>
            </div>
          </div>
        </UCard>
      </div>
    </div>
    <div v-else>
      <p class="text-sm text-gray-500 dark:text-gray-400 italic">未识别到具体实体</p>
    </div>

    <!-- 通用观点 -->
    <div v-if="data.general_opinions && data.general_opinions.length > 0">
      <h4 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">通用观点</h4>
      <div class="space-y-2">
        <div 
          v-for="(opinion, index) in data.general_opinions" 
          :key="index"
          class="flex items-start gap-3 p-3 border border-gray-100 dark:border-gray-800 rounded-lg"
        >
          <UBadge :color="getSentimentColor(opinion.sentiment)" size="xs" class="shrink-0 mt-0.5">
            {{ opinion.category }}
          </UBadge>
          <div class="flex-1 space-y-1">
            <p v-for="(op, idx) in opinion.opinions" :key="idx" class="text-sm text-gray-600 dark:text-gray-400">
              {{ op }}
            </p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>


