<template>
  <div class="space-y-4">
    <!-- 进度条（仅在有任务数据或仍在探测时显示） -->
    <div v-if="totalCount > 0 || !allAnalyzed" class="flex items-center gap-3">
      <div class="flex-1 bg-gray-200 dark:bg-gray-700 rounded-full h-2">
        <div
          class="h-2 rounded-full transition-all duration-300"
          :class="allAnalyzed ? 'bg-green-500' : 'bg-primary-500'"
          :style="{ width: `${progressPercent}%` }"
        />
      </div>
      <span class="text-sm text-gray-500 shrink-0">
        {{ analyzedCount }} / {{ totalCount }} 已分析
      </span>
    </div>

    <!-- 等待采集提示 -->
    <div v-if="!tasks.length && !allAnalyzed" class="text-center py-4">
      <UIcon name="i-heroicons-arrow-path" class="animate-spin text-lg text-primary-400 mb-1" />
      <p class="text-sm text-gray-400">新的探测任务已创建，等待爬虫采集...</p>
    </div>

    <!-- 任务状态列表 -->
    <div v-if="tasks.length" class="grid grid-cols-3 gap-1.5">
      <div
        v-for="t in tasks"
        :key="t.task_id"
        class="flex items-center gap-1.5 text-xs p-1.5 rounded"
        :class="t.has_analysis ? 'bg-green-50 dark:bg-green-900/20' : 'bg-gray-50 dark:bg-gray-800'"
      >
        <UIcon
          :name="t.has_analysis ? 'i-heroicons-check-circle' : 'i-heroicons-clock'"
          :class="t.has_analysis ? 'text-green-500' : 'text-gray-400'"
          class="shrink-0"
        />
        <span class="font-medium truncate">{{ t.keyword }}</span>
        <UBadge variant="soft" size="xs" color="neutral" class="shrink-0">{{ platformLabel(t.platform) }}</UBadge>
      </div>
    </div>

    <!-- AI 验证中提示 -->
    <div v-if="allAnalyzed && !probeReview" class="flex items-center gap-2 text-sm text-gray-500">
      <UIcon name="i-heroicons-arrow-path" class="animate-spin text-primary-400 shrink-0" />
      <span>AI 正在验证数据质量，请稍候...</span>
    </div>

    <!-- 审查结果 -->
    <div v-if="probeReview" class="space-y-3">
      <!-- 总体判定 -->
      <div
        class="p-3 rounded-lg border"
        :class="verdictInfo.style"
      >
        <div class="flex items-center gap-2">
          <UIcon :name="verdictInfo.icon" :class="verdictInfo.iconColor" />
          <span class="font-medium text-sm">{{ verdictInfo.label }}</span>
        </div>
      </div>

      <!-- 逐任务评估 -->
      <div v-if="probeReview.assessments?.length" class="space-y-1.5">
        <h4 class="text-xs font-medium text-gray-500">逐任务评估</h4>
        <div
          v-for="a in probeReview.assessments"
          :key="a.task_id"
          class="text-sm p-2 rounded border"
          :class="a.verdict === 'pass'
            ? 'border-green-200 bg-green-50 dark:bg-green-900/10'
            : 'border-amber-200 bg-amber-50 dark:bg-amber-900/10'"
        >
          <div class="flex items-center gap-2">
            <UBadge
              :color="a.verdict === 'pass' ? 'success' : 'warning'"
              variant="soft"
              size="xs"
            >
              {{ a.verdict === 'pass' ? '通过' : '待调整' }}
            </UBadge>
            <span class="font-medium">{{ a.keyword }}</span>
            <span class="text-xs text-gray-400">{{ platformLabel(a.platform) }}</span>
          </div>
          <p v-if="a.note" class="text-xs text-gray-500 mt-1">{{ a.note }}</p>
        </div>
      </div>

      <!-- 调整建议 -->
      <div v-if="probeReview.refinement_suggestions?.length" class="space-y-2">
        <h4 class="text-xs font-medium text-gray-500">AI 调整建议</h4>
        <div
          v-for="(s, i) in probeReview.refinement_suggestions"
          :key="i"
          class="text-sm p-2.5 bg-amber-50 dark:bg-amber-900/20 rounded"
        >
          <div class="flex items-center gap-2">
            <span class="text-gray-500 line-through">{{ s.original_keyword }}</span>
            <UIcon name="i-heroicons-arrow-right" class="text-gray-400 text-xs shrink-0" />
            <span class="font-medium text-amber-700 dark:text-amber-300">{{ s.suggested_keyword }}</span>
            <UBadge variant="soft" size="xs" color="neutral" class="shrink-0">{{ platformLabel(s.platform) }}</UBadge>
          </div>
          <p v-if="s.reason" class="text-xs text-gray-500 mt-1">{{ s.reason }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ProbeTaskStatus, ProbeReviewResult } from '../types'
import { platformLabel } from '../composables/useStrategyConstants'

const VERDICT_MAP = {
  all_pass: {
    style: 'border-green-200 bg-green-50 dark:bg-green-900/20',
    icon: 'i-heroicons-check-circle',
    iconColor: 'text-green-500',
    label: '全部通过 — 数据质量达标，将自动进入全量采集',
  },
  partial_pass: {
    style: 'border-amber-200 bg-amber-50 dark:bg-amber-900/20',
    icon: 'i-heroicons-exclamation-triangle',
    iconColor: 'text-amber-500',
    label: '部分通过 — 建议调整部分关键词后继续',
  },
  fail: {
    style: 'border-red-200 bg-red-50 dark:bg-red-900/20',
    icon: 'i-heroicons-x-circle',
    iconColor: 'text-red-500',
    label: '未通过 — 建议重新设计研究方案',
  },
} as const

const props = defineProps<{
  tasks: ProbeTaskStatus[]
  analyzedCount: number
  totalCount: number
  allAnalyzed: boolean
  probeReview: ProbeReviewResult | null
}>()

const progressPercent = computed(() => {
  if (props.totalCount === 0) return 0
  return Math.round((props.analyzedCount / props.totalCount) * 100)
})

const verdictInfo = computed(() => {
  const v = props.probeReview?.overall_verdict
  return VERDICT_MAP[v || 'fail'] || VERDICT_MAP.fail
})
</script>
