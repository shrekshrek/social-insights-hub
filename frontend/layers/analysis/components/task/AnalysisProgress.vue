<template>
  <UCard>
    <div class="space-y-4">
      <!-- 状态标题 -->
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <UIcon
            :name="statusIcon"
            :class="statusIconClass"
          />
          <h4 class="font-semibold text-gray-900 dark:text-gray-100">
            {{ statusLabel }}
          </h4>
        </div>
        <UBadge
          :color="statusBadgeColor"
          variant="subtle"
        >
          {{ statusBadgeLabel }}
        </UBadge>
      </div>

      <!-- 进度条 -->
      <div v-if="status === 'processing'" class="space-y-2">
        <div class="flex items-center justify-between text-sm">
          <span class="text-gray-600 dark:text-gray-400">
            处理进度
          </span>
          <span class="font-medium text-gray-900 dark:text-gray-100">
            {{ analyzedCount }} / {{ totalCount }}
          </span>
        </div>
        <UProgress
          :model-value="progress"
          :max="100"
          :color="progressColor"
          size="md"
        />
        <div class="flex items-center justify-between text-xs text-gray-500">
          <span>{{ progress.toFixed(1) }}%</span>
          <span v-if="estimatedTimeRemaining">
            预计剩余: {{ formatDuration(estimatedTimeRemaining) }}
          </span>
        </div>
      </div>

      <!-- 统计信息 -->
      <div class="grid grid-cols-2 gap-4 border-t border-gray-200 dark:border-gray-700 pt-4">
        <div class="space-y-1">
          <p class="text-xs text-gray-500 dark:text-gray-400">
            当前Token使用
          </p>
          <p class="text-lg font-semibold text-gray-900 dark:text-gray-100">
            {{ formatTokens(currentTokens) }}
          </p>
        </div>

        <div class="space-y-1">
          <p class="text-xs text-gray-500 dark:text-gray-400">
            当前成本
          </p>
          <p class="text-lg font-semibold text-gray-900 dark:text-gray-100">
            {{ formatCost(currentCost) }}
          </p>
          <UBadge
            v-if="estimatedTotalCost"
            color="gray"
            size="xs"
            variant="subtle"
          >
            预计总成本: {{ formatCost(estimatedTotalCost) }}
          </UBadge>
        </div>
      </div>

      <!-- 详细信息 -->
      <div
        v-if="result"
        class="space-y-2 border-t border-gray-200 dark:border-gray-700 pt-4 text-sm"
      >
        <div class="flex items-center justify-between">
          <span class="text-gray-600 dark:text-gray-400">
            任务类型
          </span>
          <span class="text-gray-900 dark:text-gray-100">
            {{ analysisTypeLabel }}
          </span>
        </div>

        <div v-if="result.processing_time" class="flex items-center justify-between">
          <span class="text-gray-600 dark:text-gray-400">
            已耗时
          </span>
          <span class="text-gray-900 dark:text-gray-100">
            {{ formatDuration(result.processing_time) }}
          </span>
        </div>

        <div v-if="result.started_at" class="flex items-center justify-between">
          <span class="text-gray-600 dark:text-gray-400">
            开始时间
          </span>
          <span class="text-gray-900 dark:text-gray-100">
            {{ formatDateTime(result.started_at) }}
          </span>
        </div>

        <div v-if="result.completed_at" class="flex items-center justify-between">
          <span class="text-gray-600 dark:text-gray-400">
            完成时间
          </span>
          <span class="text-gray-900 dark:text-gray-100">
            {{ formatDateTime(result.completed_at) }}
          </span>
        </div>
      </div>

      <!-- 错误信息 -->
      <div
        v-if="status === 'failed' && result?.error_message"
        class="border-t border-gray-200 dark:border-gray-700 pt-4"
      >
        <div class="flex items-start gap-2 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
          <UIcon
            name="i-heroicons-exclamation-circle"
            class="h-5 w-5 text-red-500 flex-shrink-0"
          />
          <div class="flex-1 text-sm text-red-700 dark:text-red-300">
            <p class="font-medium mb-1">错误信息</p>
            <p class="text-xs">{{ result.error_message }}</p>
          </div>
        </div>
      </div>

      <!-- 操作按钮 -->
      <div class="flex gap-2 border-t border-gray-200 dark:border-gray-700 pt-4">
        <UButton
          v-if="status === 'processing'"
          color="red"
          variant="soft"
          size="sm"
          icon="i-heroicons-stop"
          @click="$emit('cancel')"
        >
          取消任务
        </UButton>

        <UButton
          v-if="status === 'completed'"
          color="primary"
          variant="soft"
          size="sm"
          icon="i-heroicons-eye"
          @click="$emit('view-results')"
        >
          查看结果
        </UButton>

        <UButton
          v-if="status === 'failed'"
          color="gray"
          variant="soft"
          size="sm"
          icon="i-heroicons-arrow-path"
          @click="$emit('retry')"
        >
          重试
        </UButton>

        <CostDetailPopover
          v-if="result?.token_usage"
          :stats="result.token_usage"
          button-label=""
          class="ml-auto"
        />
      </div>
    </div>
  </UCard>
</template>

<script setup lang="ts">
import type { AnalysisJob, AnalysisStatus } from '../../types'

interface Props {
  result: AnalysisJob
  autoRefresh?: boolean
  refreshInterval?: number
}

const props = withDefaults(defineProps<Props>(), {
  autoRefresh: true,
  refreshInterval: 2000,
})

const _emit = defineEmits<{
  'cancel': []
  'retry': []
  'view-results': []
}>()

const { formatTokens, formatCost, formatDuration, estimateRemainingCost } = useTokenUsage()

// 计算属性
const status = computed<AnalysisStatus>(() => props.result.status as AnalysisStatus)

const progress = computed(() => {
  if (props.result.source_count === 0) return 0
  return (props.result.analyzed_count / props.result.source_count) * 100
})

const analyzedCount = computed(() => props.result.analyzed_count)
const totalCount = computed(() => props.result.source_count)
const currentTokens = computed(() => props.result.token_usage?.summary.total_tokens || 0)
const currentCost = computed(() => props.result.token_usage?.summary.total_cost_cny || 0)

const estimatedTimeRemaining = computed(() => {
  // 简单估算：根据已完成的时间和进度估算剩余时间
  if (!props.result.processing_time || props.result.analyzed_count === 0) return null
  const avgTimePerItem = props.result.processing_time / props.result.analyzed_count
  const remainingItems = props.result.source_count - props.result.analyzed_count
  return avgTimePerItem * remainingItems
})

const estimatedTotalCost = computed(() => {
  if (status.value !== 'processing') return null
  return estimateRemainingCost(
    currentCost.value,
    analyzedCount.value,
    totalCount.value
  )
})

const statusIcon = computed(() => {
  const icons = {
    pending: 'i-heroicons-clock',
    processing: 'i-heroicons-arrow-path',
    completed: 'i-heroicons-check-circle',
    failed: 'i-heroicons-x-circle',
  }
  return icons[status.value] || icons.pending
})

const statusIconClass = computed(() => {
  const classes = {
    pending: 'h-5 w-5 text-gray-500 animate-pulse',
    processing: 'h-5 w-5 text-blue-500 animate-spin',
    completed: 'h-5 w-5 text-green-500',
    failed: 'h-5 w-5 text-red-500',
  }
  return classes[status.value] || classes.pending
})

const statusLabel = computed(() => {
  const labels = {
    pending: '等待处理',
    processing: '正在分析',
    completed: '分析完成',
    failed: '分析失败',
  }
  return labels[status.value] || '未知状态'
})

const statusBadgeColor = computed(() => {
  const colors = {
    pending: 'gray',
    processing: 'blue',
    completed: 'green',
    failed: 'red',
  }
  return colors[status.value] || 'gray'
})

const statusBadgeLabel = computed(() => {
  const labels = {
    pending: '排队中',
    processing: '处理中',
    completed: '已完成',
    failed: '失败',
  }
  return labels[status.value] || '未知'
})

const progressColor = computed(() => {
  if (progress.value < 30) return 'blue'
  if (progress.value < 70) return 'primary'
  return 'green'
})

const analysisTypeLabel = computed(() => {
  const labels: Record<string, string> = {
    screening_posts: '原文初筛',
    screening_comments: '评论初筛',
    deep_posts: '原文深度分析',
    deep_comments: '评论深度分析',
    monitor_slice_summary: '监测切片总分析',
  }
  return labels[props.result.analysis_type] || props.result.analysis_type
})

const formatDateTime = (dateStr: string) => {
  return new Date(dateStr).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
</script>
