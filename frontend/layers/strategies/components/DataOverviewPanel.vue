<template>
  <div class="space-y-4">
    <!-- 整体进度条：仅在采集进行中显示。allAnalyzed=true 时进度条变成静态 100%
         无增量信息，纯视觉冗余，隐藏；任务卡片照常保留作为数据来源审计记录 -->
    <div v-if="!allAnalyzed && totalCount > 0" class="flex items-center gap-3">
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
            <NuxtLink
              v-for="t in group"
              :key="t.task_id"
              :to="`/social-media/tasks/${t.task_id}`"
              class="flex items-center gap-1.5 text-xs p-1.5 rounded hover:ring-1 hover:ring-primary-300 transition"
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
              <span class="text-gray-400 shrink-0 ml-auto">{{ formatTaskCounts(t) }}</span>
            </NuxtLink>
          </div>
        </div>
      </div>

      <!-- 无维度映射：平铺展示（兜底） -->
      <div v-else class="grid grid-cols-3 gap-1.5">
        <NuxtLink
          v-for="t in tasks"
          :key="t.task_id"
          :to="`/social-media/tasks/${t.task_id}`"
          class="flex items-center gap-1.5 text-xs p-1.5 rounded hover:ring-1 hover:ring-primary-300 transition"
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
          <span class="text-gray-400 shrink-0 ml-auto">{{ formatTaskCounts(t) }}</span>
        </NuxtLink>
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
          <NuxtLink
            v-for="t in group"
            :key="t.task_id"
            :to="`/news-media/tasks/${t.task_id}`"
            class="flex items-center gap-1.5 text-xs p-1.5 rounded hover:ring-1 hover:ring-primary-300 transition"
            :class="statusBg(t.status)"
          >
            <UIcon
              :name="statusIcon(t.status)"
              :class="[statusIconColor(t.status), t.status === 'running' ? 'animate-spin' : '']"
              class="shrink-0"
            />
            <span class="font-medium truncate">{{ t.keyword }}</span>
            <span class="text-gray-400 shrink-0 ml-auto">{{ t.articles_count }} 篇</span>
          </NuxtLink>
        </div>
      </div>
    </div>

    <!-- 专题研究（行业 / 创意）：在 collecting 阶段与全量采集并行启动 -->
    <div v-if="researchCards.length" class="space-y-1.5">
      <div class="flex items-center gap-2">
        <UIcon name="i-heroicons-academic-cap" class="text-purple-500 size-4" />
        <span class="text-xs font-medium text-gray-500">专题研究</span>
      </div>
      <div class="grid grid-cols-3 gap-1.5">
        <component
          :is="card.taskId ? NuxtLink : 'div'"
          v-for="card in researchCards"
          :key="card.key"
          :to="card.taskId ? `/research-agent/${card.taskId}` : undefined"
          class="flex items-center gap-1.5 text-xs p-1.5 rounded"
          :class="[
            statusBg(card.status),
            card.taskId ? 'hover:ring-1 hover:ring-primary-300 transition' : '',
          ]"
        >
          <UIcon
            :name="statusIcon(card.status)"
            :class="[statusIconColor(card.status), card.status === 'running' ? 'animate-spin' : '']"
            class="shrink-0"
          />
          <span class="font-medium truncate">{{ card.label }}</span>
          <UBadge variant="subtle" size="sm" :color="researchBadgeColor(card.status)" class="shrink-0 ml-auto">
            {{ researchStatusLabel(card.status, card.hasTask) }}
          </UBadge>
        </component>
      </div>
    </div>

    <!-- 切片列表（按渠道分组） -->
    <div v-if="slices.length" class="space-y-3">
      <h4 class="text-xs font-medium text-gray-500">
        分析切片（{{ slices.length }} 个 · 社媒 {{ socialSlices.length }} · 新闻 {{ newsSlices.length }}）
      </h4>

      <!-- 社媒切片 -->
      <div v-if="socialSlices.length" class="space-y-1.5">
        <div class="flex items-center gap-2">
          <UIcon name="i-heroicons-chat-bubble-left-right" class="text-blue-400 size-4" />
          <span class="text-xs font-medium text-gray-500">社媒切片</span>
        </div>
        <div class="grid grid-cols-3 gap-2">
          <NuxtLink
            v-for="s in socialSlices"
            :key="`social-${s.slice_id}`"
            :to="`/social-media/monitors/${s.monitor_id}/analysis?slice_id=${s.slice_id}`"
            class="flex items-center gap-2 text-sm p-2 border border-gray-100 dark:border-gray-800 rounded-lg hover:border-primary-300 hover:text-primary-600 transition-colors"
          >
            <UIcon name="i-heroicons-document-chart-bar" class="text-gray-400 shrink-0" />
            <span class="font-medium truncate flex-1 min-w-0">{{ s.slice_name || `切片 #${s.slice_id}` }}</span>
            <UBadge
              :color="sliceStatusColor(s.status)"
              variant="subtle"
              size="sm"
              class="shrink-0"
            >
              {{ sliceStatusLabel(s.status) }}
            </UBadge>
          </NuxtLink>
        </div>
      </div>

      <!-- 新闻切片 -->
      <div v-if="newsSlices.length" class="space-y-1.5">
        <div class="flex items-center gap-2">
          <UIcon name="i-heroicons-newspaper" class="text-amber-500 size-4" />
          <span class="text-xs font-medium text-gray-500">新闻切片</span>
        </div>
        <div class="grid grid-cols-3 gap-2">
          <NuxtLink
            v-for="s in newsSlices"
            :key="`news-${s.slice_id}`"
            :to="`/news-media/slices/${s.slice_id}`"
            class="flex items-center gap-2 text-sm p-2 border border-gray-100 dark:border-gray-800 rounded-lg hover:border-primary-300 hover:text-primary-600 transition-colors"
          >
            <UIcon name="i-heroicons-document-text" class="text-gray-400 shrink-0" />
            <span class="font-medium truncate flex-1 min-w-0">{{ s.slice_name || `切片 #${s.slice_id}` }}</span>
            <UBadge
              :color="sliceStatusColor(s.status)"
              variant="subtle"
              size="sm"
              class="shrink-0"
            >
              {{ sliceStatusLabel(s.status) }}
            </UBadge>
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
        <div class="space-y-1.5">
          <div
            v-for="qc in coverageResult.question_coverage"
            :key="qc.question_id"
          >
            <div class="flex items-start gap-2 text-sm">
              <UIcon
                :name="qc.covered ? 'i-heroicons-check' : 'i-heroicons-x-mark'"
                :class="qc.covered ? 'text-green-500' : 'text-red-400'"
                class="mt-0.5 shrink-0"
              />
              <div class="flex-1">
                <span>{{ qc.question }}</span>
                <span v-if="qc.note" class="text-xs text-gray-400 ml-1">{{ qc.note }}</span>
              </div>
            </div>

            <!-- 未覆盖时显示 probe 阶段诊断（根因分析） -->
            <details
              v-if="!qc.covered && getDiagnosticForRQ(qc.question_id)"
              class="ml-6 mt-1.5"
            >
              <summary class="text-xs text-gray-500 dark:text-gray-400 cursor-pointer hover:text-gray-700 dark:hover:text-gray-200 select-none">
                查看 probe 阶段诊断
              </summary>
              <div class="mt-2 pl-3 border-l-2 border-amber-200 dark:border-amber-800/40 space-y-1.5">
                <div class="text-xs text-gray-500 dark:text-gray-400">
                  关联维度：{{ getDiagnosticForRQ(qc.question_id)?.dimensionNames.join('、') }}
                </div>
                <div
                  v-for="a in getDiagnosticForRQ(qc.question_id)?.assessments ?? []"
                  :key="a.task_id"
                  class="text-xs flex items-start gap-2"
                >
                  <UIcon
                    :name="a.verdict === 'pass' ? 'i-heroicons-check-circle' : 'i-heroicons-exclamation-circle'"
                    :class="a.verdict === 'pass' ? 'text-green-500' : 'text-red-400'"
                    class="mt-0.5 shrink-0"
                  />
                  <div class="flex-1 min-w-0">
                    <div class="text-gray-700 dark:text-gray-300">
                      <span class="font-mono">{{ a.platform }}</span> /
                      <span>{{ a.keyword }}</span>
                      <span v-if="a.subject_match !== undefined" class="ml-1.5 text-gray-400">
                        subject_match=<span :class="a.subject_match ? 'text-green-600' : 'text-red-500'">{{ a.subject_match }}</span>
                      </span>
                      <span v-if="a.competitor_match !== undefined" class="ml-1.5 text-gray-400">
                        competitor_match=<span :class="a.competitor_match ? 'text-green-600' : 'text-red-500'">{{ a.competitor_match }}</span>
                      </span>
                      <span v-if="a.relevant_source_posts !== undefined" class="ml-1.5 text-gray-400">
                        相关源帖={{ a.relevant_source_posts }}
                      </span>
                    </div>
                    <div v-if="a.note" class="text-gray-500 mt-0.5 leading-snug">
                      {{ a.note }}
                    </div>
                    <div v-if="a.verdict === 'fail' && a.suggestion_reason" class="text-amber-600 dark:text-amber-400 mt-0.5 leading-snug">
                      建议：{{ a.suggestion_reason }}
                    </div>
                  </div>
                </div>
              </div>
            </details>
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
import { NuxtLink } from '#components'
import type {
  SliceSummary,
  CoverageCheckResult,
  CollectionTaskStatus,
  NewsCollectionTaskStatus,
  ResearchAgentStatus,
  ProbeAssessment,
  DataPlanItem,
} from '../types'
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
  /** 行业研究任务状态（approve_probe 时启动，与全量采集并行） */
  industryResearch?: ResearchAgentStatus
  /** 创意研究任务状态（campaign_strategy / full_strategy 路径） */
  creativeResearch?: ResearchAgentStatus
  /** 数据计划（用于反查 RQ → 维度 → 任务） */
  dataPlan?: DataPlanItem[]
  /** Probe 阶段的 per-task assessments（用于覆盖失败 RQ 的根因诊断） */
  probeAssessments?: ProbeAssessment[]
}>()

/** 反查给定 RQ 的 probe 阶段 per-task 诊断信息
 *
 * 链路：questionId → data_plan(question_ids 含此 RQ) → dimension_name → task_id → assessment
 */
function getDiagnosticForRQ(questionId: string): {
  dimensionNames: string[]
  assessments: ProbeAssessment[]
} | null {
  if (!props.dataPlan?.length || !props.probeAssessments?.length) return null
  const dimNames = new Set(
    props.dataPlan
      .filter(dp => (dp.question_ids ?? []).includes(questionId))
      .map(dp => dp.dimension_name)
      .filter(Boolean),
  )
  if (!dimNames.size) return null

  const dimMap = props.taskDimensionMap ?? {}
  const relatedTaskIds = new Set(
    Object.entries(dimMap)
      .filter(([, dim]) => dimNames.has(dim))
      .map(([taskId]) => Number(taskId)),
  )
  if (!relatedTaskIds.size) return null

  const assessments = props.probeAssessments.filter(a => relatedTaskIds.has(a.task_id))
  if (!assessments.length) return null

  return { dimensionNames: Array.from(dimNames), assessments }
}

const progressPercent = computed(() => {
  if (props.totalCount === 0) return 0
  return Math.round((props.completedCount / props.totalCount) * 100)
})

/** 任务终态（completed / failed） */
const isTerminal = (status: string) => status === 'completed' || status === 'failed'

/** 任务卡片右侧统计：有评论时显示"X 帖 · Y 评"，无评论时只显示"X 帖" */
const formatTaskCounts = (t: CollectionTaskStatus): string => {
  const posts = `${t.posts_count} 帖`
  if (t.comments_count > 0) return `${posts} · ${t.comments_count} 评`
  return posts
}

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

/** 切片按 channel 分组 */
const socialSlices = computed(() => props.slices.filter(s => s.channel === 'social'))
const newsSlices = computed(() => props.slices.filter(s => s.channel === 'news'))

/** 切片状态展示
 *
 * - 社媒：pending（Stage1 排队）/ processing（Stage2 跑中）/ completed / failed
 * - 新闻：pending（待派发）/ analyzing（Celery insight 跑中）/ completed / failed
 *
 * 用户视角统一：未到 completed/failed 都视为"分析中"
 */
const sliceStatusLabel = (status: string): string => {
  if (status === 'completed') return '已完成'
  if (status === 'failed') return '失败'
  if (!status || status === 'pending') return '待开始'
  return '分析中'
}

const sliceStatusColor = (status: string) => {
  if (status === 'completed') return 'success' as const
  if (status === 'failed') return 'error' as const
  if (!status || status === 'pending') return 'neutral' as const
  return 'primary' as const
}

/** 专题研究卡片：仅展示 has_task=true 的（避免空槽位） */
const researchCards = computed(() => {
  const cards: Array<{
    key: string
    label: string
    status: string
    hasTask: boolean
    taskId: number | null
  }> = []
  if (props.industryResearch?.has_task) {
    cards.push({
      key: 'industry',
      label: '行业研究',
      status: props.industryResearch.status || 'pending',
      hasTask: true,
      taskId: props.industryResearch.task_id,
    })
  }
  if (props.creativeResearch?.has_task) {
    cards.push({
      key: 'creative',
      label: '创意研究',
      status: props.creativeResearch.status || 'pending',
      hasTask: true,
      taskId: props.creativeResearch.task_id,
    })
  }
  return cards
})

const researchStatusLabel = (status: string, hasTask: boolean): string => {
  if (!hasTask) return '未启动'
  if (status === 'completed') return '已完成'
  if (status === 'failed') return '失败'
  if (status === 'running') return '研究中'
  return '排队中'
}

const researchBadgeColor = (status: string) => {
  if (status === 'completed') return 'success' as const
  if (status === 'failed') return 'error' as const
  if (status === 'running') return 'primary' as const
  return 'neutral' as const
}
</script>
