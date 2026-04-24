<template>
  <div class="space-y-4">
    <!-- 整体进度条 -->
    <div v-if="showProgress || totalCount > 0" class="flex items-center gap-3">
      <div class="flex-1 bg-gray-200 dark:bg-gray-700 rounded-full h-2">
        <div
          class="h-2 rounded-full transition-all duration-300"
          :class="allAnalyzed ? 'bg-green-500' : 'bg-primary-500'"
          :style="{ width: `${progressPercent}%` }"
        />
      </div>
      <span class="text-sm text-gray-500 shrink-0">
        {{ completedCount }} / {{ totalCount }} 已完成
      </span>
    </div>

    <!-- 社媒任务状态：按维度分组 -->
    <div v-if="tasks.length">
      <!-- 有维度映射：分组展示 -->
      <div v-if="dimensionGroups" class="space-y-3">
        <div v-for="(group, dimName) in dimensionGroups" :key="dimName" class="space-y-1.5">
          <div class="flex items-center gap-2">
            <span class="text-xs font-medium text-gray-500">{{ dimName }}</span>
            <span
              class="text-xs"
              :class="group.every(t => isTerminal(t.status)) ? 'text-green-500' : 'text-gray-400'"
            >
              {{ group.filter(t => t.status === 'completed').length }}/{{ group.length }} 已完成
            </span>
          </div>
          <div class="grid grid-cols-3 gap-1.5">
            <div
              v-for="t in group"
              :key="t.task_id"
              class="flex items-center gap-1.5 text-xs p-1.5 rounded"
              :class="statusBg(t.status)"
            >
              <UIcon
                :name="statusIcon(t.status)"
                :class="[statusIconColor(t.status), t.status === 'running' ? 'animate-spin' : '']"
                class="shrink-0"
              />
              <span class="font-medium truncate">{{ t.keyword }}</span>
              <UBadge variant="subtle" size="sm" color="neutral" class="shrink-0">
                {{ platformLabel(t.platform) }}
              </UBadge>
              <span class="text-gray-400 shrink-0 ml-auto">{{ t.posts_count }} 帖</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 无维度映射：平铺展示（兜底） -->
      <div v-else class="grid grid-cols-3 gap-1.5">
        <div
          v-for="t in tasks"
          :key="t.task_id"
          class="flex items-center gap-1.5 text-xs p-1.5 rounded"
          :class="statusBg(t.status)"
        >
          <UIcon
            :name="statusIcon(t.status)"
            :class="[statusIconColor(t.status), t.status === 'running' ? 'animate-spin' : '']"
            class="shrink-0"
          />
          <span class="font-medium truncate">{{ t.keyword }}</span>
          <UBadge variant="subtle" size="sm" color="neutral" class="shrink-0">
            {{ platformLabel(t.platform) }}
          </UBadge>
          <span class="text-gray-400 shrink-0 ml-auto">{{ t.posts_count }} 帖</span>
        </div>
      </div>
    </div>

    <!-- 新闻任务状态：按维度分组 -->
    <div v-if="newsTasks.length" class="space-y-3">
      <div v-for="(group, dimName) in newsDimensionGroups" :key="dimName" class="space-y-1.5">
        <div class="flex items-center gap-2">
          <span class="text-xs font-medium text-gray-500">{{ dimName }}</span>
          <span class="text-xs text-gray-400">新闻</span>
          <span
            class="text-xs"
            :class="group.every(t => isTerminal(t.status)) ? 'text-green-500' : 'text-gray-400'"
          >
            {{ group.filter(t => t.status === 'completed').length }}/{{ group.length }} 已完成
          </span>
        </div>
        <div class="grid grid-cols-3 gap-1.5">
          <div
            v-for="t in group"
            :key="t.task_id"
            class="flex items-center gap-1.5 text-xs p-1.5 rounded"
            :class="statusBg(t.status)"
          >
            <UIcon
              :name="statusIcon(t.status)"
              :class="[statusIconColor(t.status), t.status === 'running' ? 'animate-spin' : '']"
              class="shrink-0"
            />
            <span class="font-medium truncate">{{ t.keyword }}</span>
            <span class="text-gray-400 shrink-0 ml-auto">{{ t.articles_count }} 篇</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 切片列表 -->
    <div v-if="slices.length">
      <h4 class="text-xs font-medium text-gray-500 mb-2">
        分析切片（{{ slices.length }} 个）
      </h4>
      <div class="grid grid-cols-3 gap-2">
        <div
          v-for="s in slices"
          :key="s.slice_id"
          class="flex items-center gap-2 text-sm p-2 border border-gray-100 dark:border-gray-800 rounded-lg"
        >
          <UIcon name="i-heroicons-document-chart-bar" class="text-gray-400 shrink-0" />
          <NuxtLink
            :to="`/social-media/monitors/${s.monitor_id}/analysis?slice_id=${s.slice_id}`"
            class="flex-1 min-w-0 hover:text-primary-600 transition-colors"
          >
            <div class="font-medium truncate">{{ s.slice_name || `切片 #${s.slice_id}` }}</div>
          </NuxtLink>
        </div>
      </div>
    </div>

    <!-- 覆盖度验证 -->
    <div v-if="coverageResult" class="space-y-3">
      <div
        class="p-3 rounded-lg border"
        :class="coverageResult.overall_ready
          ? 'border-green-200 bg-green-50 dark:bg-green-900/20'
          : 'border-amber-200 bg-amber-50 dark:bg-amber-900/20'"
      >
        <div class="flex items-center gap-2">
          <UIcon
            :name="coverageResult.overall_ready ? 'i-heroicons-check-circle' : 'i-heroicons-exclamation-triangle'"
            :class="coverageResult.overall_ready ? 'text-green-500' : 'text-amber-500'"
          />
          <span class="font-medium text-sm">
            {{ coverageResult.overall_ready ? '数据就绪 — 可进行策略生成' : '数据覆盖不完整' }}
          </span>
        </div>
      </div>

      <!-- 研究问题覆盖 -->
      <div v-if="coverageResult.question_coverage?.length">
        <h4 class="text-xs font-medium text-gray-500 mb-1.5">研究问题覆盖度</h4>
        <div class="space-y-1">
          <div
            v-for="qc in coverageResult.question_coverage"
            :key="qc.question_id"
            class="flex items-start gap-2 text-sm"
          >
            <UIcon
              :name="qc.covered ? 'i-heroicons-check' : 'i-heroicons-x-mark'"
              :class="qc.covered ? 'text-green-500' : 'text-red-400'"
              class="mt-0.5 shrink-0"
            />
            <div>
              <span>{{ qc.question }}</span>
              <span v-if="qc.note" class="text-xs text-gray-400 ml-1">{{ qc.note }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 数据亮点 -->
      <div v-if="coverageResult.data_highlights?.length">
        <h4 class="text-xs font-medium text-gray-500 mb-1.5">数据亮点</h4>
        <div class="space-y-1">
          <div
            v-for="(h, i) in coverageResult.data_highlights"
            :key="i"
            class="text-sm text-gray-600 dark:text-gray-400"
          >
            · {{ h }}
          </div>
        </div>
      </div>

      <!-- 切片调整建议 -->
      <div v-if="coverageResult.slice_adjustments?.length">
        <h4 class="text-xs font-medium text-gray-500 mb-1.5">切片调整建议</h4>
        <div class="space-y-1.5">
          <div
            v-for="(sa, i) in coverageResult.slice_adjustments"
            :key="i"
            class="text-sm text-gray-600 dark:text-gray-400"
          >
            <span class="font-medium">{{ sa.slice_name }}</span>：{{ sa.issue }}
            <span class="text-gray-500"> → {{ sa.suggestion }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { SliceSummary, CoverageCheckResult, CollectionTaskStatus, NewsCollectionTaskStatus } from '../types'
import { platformLabel } from '../composables/useStrategyConstants'

const props = defineProps<{
  tasks: CollectionTaskStatus[]
  newsTasks: NewsCollectionTaskStatus[]
  slices: SliceSummary[]
  completedCount: number
  totalCount: number
  allAnalyzed: boolean
  showProgress: boolean
  coverageResult: CoverageCheckResult | null
  /** task_id(string) → dimension_name 映射，用于按维度分组展示社媒任务 */
  taskDimensionMap?: Record<string, string>
}>()

const progressPercent = computed(() => {
  if (props.totalCount === 0) return 0
  return Math.round((props.completedCount / props.totalCount) * 100)
})

/** 任务终态（completed / failed） */
const isTerminal = (status: string) => status === 'completed' || status === 'failed'

const statusBg = (status: string): string => {
  if (status === 'completed') return 'bg-green-50 dark:bg-green-900/20'
  if (status === 'failed') return 'bg-red-50 dark:bg-red-900/20'
  if (status === 'running') return 'bg-primary-50 dark:bg-primary-900/20'
  return 'bg-gray-50 dark:bg-gray-800'
}

const statusIcon = (status: string): string => {
  if (status === 'completed') return 'i-heroicons-check-circle'
  if (status === 'failed') return 'i-heroicons-x-circle'
  if (status === 'running') return 'i-heroicons-arrow-path'
  return 'i-heroicons-clock'
}

const statusIconColor = (status: string): string => {
  if (status === 'completed') return 'text-green-500'
  if (status === 'failed') return 'text-red-400'
  if (status === 'running') return 'text-primary-500'
  return 'text-gray-400'
}

/** 按维度分组社媒任务 */
const dimensionGroups = computed((): Record<string, CollectionTaskStatus[]> | null => {
  if (!props.taskDimensionMap || !props.tasks.length) return null

  const groups: Record<string, CollectionTaskStatus[]> = {}
  for (const task of props.tasks) {
    const dim = props.taskDimensionMap[String(task.task_id)] || '其他'
    if (!groups[dim]) groups[dim] = []
    groups[dim].push(task)
  }

  // 过滤空组
  const filtered = Object.fromEntries(Object.entries(groups).filter(([, ts]) => ts.length > 0))
  return Object.keys(filtered).length > 0 ? filtered : null
})

/** 按维度分组新闻任务（dimension 由 backend 基于 _news_task_dimension_map 注入） */
const newsDimensionGroups = computed((): Record<string, NewsCollectionTaskStatus[]> => {
  const groups: Record<string, NewsCollectionTaskStatus[]> = {}
  for (const t of props.newsTasks) {
    const dim = t.dimension || '其他'
    if (!groups[dim]) groups[dim] = []
    groups[dim].push(t)
  }
  return groups
})
</script>
