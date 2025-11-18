<template>
  <UCard
    :ui="{
      body: { padding: 'p-4 sm:p-6' },
      header: { padding: 'p-4 sm:px-6' }
    }"
  >
    <template #header>
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <UIcon
            name="i-heroicons-cpu-chip"
            class="h-5 w-5 text-primary-500"
          />
          <h3 class="text-lg font-semibold text-gray-900 dark:text-gray-100">
            {{ title }}
          </h3>
        </div>
        <UBadge
          v-if="badge"
          :color="badge.color"
          variant="subtle"
        >
          {{ badge.label }}
        </UBadge>
      </div>
    </template>

    <div v-if="loading" class="flex items-center justify-center py-8">
      <UIcon name="i-heroicons-arrow-path" class="h-6 w-6 animate-spin text-gray-400" />
    </div>

    <div v-else-if="!stats" class="py-8 text-center text-gray-500">
      暂无统计数据
    </div>

    <div v-else class="space-y-4">
      <!-- 主要指标 -->
      <div class="grid grid-cols-2 gap-4">
        <div class="space-y-1">
          <p class="text-sm text-gray-500 dark:text-gray-400">
            总Token数
          </p>
          <p class="text-2xl font-bold text-gray-900 dark:text-gray-100">
            {{ formatTokens(stats.total_tokens) }}
          </p>
          <p class="text-xs text-gray-400">
            输入: {{ formatTokens(stats.total_input_tokens) }} /
            输出: {{ formatTokens(stats.total_output_tokens) }}
          </p>
        </div>

        <div class="space-y-1">
          <p class="text-sm text-gray-500 dark:text-gray-400">
            总成本
          </p>
          <p class="text-2xl font-bold text-gray-900 dark:text-gray-100">
            {{ formatCost(stats.total_cost_cny) }}
          </p>
          <div class="flex items-center gap-1">
            <UBadge
              :color="getCostLevel(stats.total_cost_cny).color"
              size="xs"
              variant="subtle"
            >
              {{ getCostLevel(stats.total_cost_cny).label }}
            </UBadge>
          </div>
        </div>
      </div>

      <!-- 次要指标 -->
      <div class="grid grid-cols-3 gap-4 border-t border-gray-200 dark:border-gray-700 pt-4">
        <div class="space-y-1">
          <p class="text-xs text-gray-500 dark:text-gray-400">
            调用次数
          </p>
          <p class="text-lg font-semibold text-gray-900 dark:text-gray-100">
            {{ stats.total_calls }}
          </p>
        </div>

        <div class="space-y-1">
          <p class="text-xs text-gray-500 dark:text-gray-400">
            平均Token
          </p>
          <p class="text-lg font-semibold text-gray-900 dark:text-gray-100">
            {{ formatTokens(Math.round(stats.avg_tokens_per_call)) }}
          </p>
        </div>

        <div class="space-y-1">
          <p class="text-xs text-gray-500 dark:text-gray-400">
            平均成本
          </p>
          <p class="text-lg font-semibold text-gray-900 dark:text-gray-100">
            {{ formatCost(stats.avg_cost_per_call) }}
          </p>
        </div>
      </div>

      <!-- 时长 -->
      <div v-if="stats.total_duration_seconds" class="flex items-center justify-between border-t border-gray-200 dark:border-gray-700 pt-4">
        <span class="text-sm text-gray-500 dark:text-gray-400">
          总耗时
        </span>
        <span class="text-sm font-medium text-gray-900 dark:text-gray-100">
          {{ formatDuration(stats.total_duration_seconds) }}
        </span>
      </div>

      <!-- 详情按钮 -->
      <div v-if="showDetails" class="flex justify-end border-t border-gray-200 dark:border-gray-700 pt-4">
        <UButton
          color="gray"
          variant="ghost"
          size="sm"
          icon="i-heroicons-chevron-right"
          trailing
          @click="$emit('view-details')"
        >
          查看详情
        </UButton>
      </div>
    </div>
  </UCard>
</template>

<script setup lang="ts">
import type { TokenUsageSummary } from '../types'

interface Props {
  title?: string
  stats: TokenUsageSummary | null
  loading?: boolean
  showDetails?: boolean
  badge?: {
    label: string
    color: string
  }
}

const props = withDefaults(defineProps<Props>(), {
  title: 'Token使用统计',
  loading: false,
  showDetails: true,
})

const emit = defineEmits<{
  'view-details': []
}>()

const { formatTokens, formatCost, formatDuration, getCostLevel } = useTokenUsage()
</script>
