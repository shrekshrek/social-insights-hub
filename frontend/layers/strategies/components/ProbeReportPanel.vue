<template>
  <div class="space-y-4">
    <!-- 进度条：审查报告出来后让位（与数据就绪面板一致）；failed 任务恒令 allAnalyzed=false，仍会保留 -->
    <div v-if="(totalCount > 0 || !allAnalyzed) && !(allAnalyzed && probeReview)" class="flex items-center gap-3">
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

    <!-- 等待采集提示（纯新闻策略无社媒任务时，新闻也未完成时才转圈） -->
    <div v-if="!socialTasks.length && !newsTasks.length && !allAnalyzed" class="text-center py-4">
      <UIcon name="i-heroicons-arrow-path" class="animate-spin text-lg text-primary-400 mb-1" />
      <p class="text-sm text-gray-400">新的探测任务已创建，等待采集...</p>
    </div>

    <!-- 社媒任务失败提示：阻塞探测验证，需 retry 或人工删除 -->
    <div
      v-if="failedSocialCount > 0 && !probeReview"
      class="p-3 rounded-lg border border-red-200 bg-red-50 dark:bg-red-900/20"
    >
      <div class="flex items-start gap-2">
        <UIcon name="i-heroicons-exclamation-triangle" class="text-red-500 size-5 shrink-0 mt-0.5" />
        <div class="flex-1 text-sm space-y-1">
          <p class="font-medium text-red-700 dark:text-red-400">
            {{ failedSocialCount }} 个社媒探测任务采集失败，探测验证暂停
          </p>
          <p class="text-xs text-red-600 dark:text-red-300">
            等待爬虫自动续采，或前往监测项目页手动删除失败任务以继续。删除时请筛选 phase=探测，避免误删全量任务。
          </p>
          <NuxtLink
            v-if="socialMonitorId"
            :to="`/social-media/monitors/${socialMonitorId}`"
            class="inline-flex items-center gap-1 text-xs text-red-700 dark:text-red-400 hover:underline mt-1"
          >
            <UIcon name="i-heroicons-arrow-top-right-on-square" class="size-3.5" />
            前往监测项目页
          </NuxtLink>
        </div>
      </div>
    </div>

    <!-- 社媒任务状态：按维度分组 -->
    <div v-if="socialTasks.length">
      <!-- 有维度映射：分组展示 -->
      <div v-if="dimensionGroups" class="space-y-3">
        <div v-for="(group, dimName) in dimensionGroups" :key="dimName" class="space-y-1.5">
          <div class="flex items-center gap-2">
            <span class="text-xs font-medium text-gray-500">{{ dimName }}</span>
            <span class="text-xs text-gray-400">
              {{ group.filter(t => t.has_analysis && t.status !== 'failed').length }}/{{ group.length }} 已分析
            </span>
            <span v-if="group.filter(t => t.status === 'failed').length" class="text-xs text-red-500">
              {{ group.filter(t => t.status === 'failed').length }} 失败
            </span>
          </div>
          <div class="grid grid-cols-3 gap-1.5">
            <div
              v-for="t in group"
              :key="t.task_id"
              class="flex items-center gap-1.5 text-xs p-1.5 rounded"
              :class="socialTaskBg(t)"
              :title="socialTaskTooltip(t)"
            >
              <UIcon
                :name="socialTaskIcon(t)"
                :class="socialTaskIconColor(t)"
                class="shrink-0"
              />
              <span class="font-medium truncate">{{ t.keyword }}</span>
              <UBadge variant="subtle" size="sm" color="neutral" class="shrink-0">{{ platformLabel(t.platform) }}</UBadge>
              <span v-if="t.status === 'failed'" class="text-red-500 shrink-0 ml-auto text-[10px]">
                {{ formatRelativeTime(t.last_updated_at) }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- 无维度映射：平铺展示（兜底） -->
      <div v-else class="grid grid-cols-3 gap-1.5">
        <div
          v-for="t in socialTasks"
          :key="t.task_id"
          class="flex items-center gap-1.5 text-xs p-1.5 rounded"
          :class="socialTaskBg(t)"
          :title="socialTaskTooltip(t)"
        >
          <UIcon
            :name="socialTaskIcon(t)"
            :class="socialTaskIconColor(t)"
            class="shrink-0"
          />
          <span class="font-medium truncate">{{ t.keyword }}</span>
          <UBadge variant="subtle" size="sm" color="neutral" class="shrink-0">{{ platformLabel(t.platform) }}</UBadge>
          <span v-if="t.status === 'failed'" class="text-red-500 shrink-0 ml-auto text-[10px]">
            {{ formatRelativeTime(t.last_updated_at) }}
          </span>
        </div>
      </div>
    </div>

    <!-- 新闻任务状态：按维度分组 -->
    <div v-if="newsTasks.length" class="space-y-3">
      <div v-for="(group, dimName) in newsTaskDimensionGroups" :key="dimName" class="space-y-1.5">
        <div class="flex items-center gap-2">
          <span class="text-xs font-medium text-gray-500">{{ dimName }}</span>
          <span class="text-xs text-gray-400">新闻</span>
          <span class="text-xs" :class="group.every(t => t.completed || t.failed) ? 'text-green-500' : 'text-gray-400'">
            {{ group.filter(t => t.completed || t.failed).length }}/{{ group.length }} 已完成
          </span>
        </div>
        <div class="grid grid-cols-3 gap-1.5">
          <div
            v-for="t in group"
            :key="t.task_id"
            class="flex items-center gap-1.5 text-xs p-1.5 rounded"
            :class="t.completed ? 'bg-green-50 dark:bg-green-900/20' : t.failed ? 'bg-red-50 dark:bg-red-900/20' : 'bg-gray-50 dark:bg-gray-800'"
          >
            <UIcon
              :name="t.completed ? 'i-heroicons-check-circle' : t.failed ? 'i-heroicons-x-circle' : 'i-heroicons-clock'"
              :class="t.completed ? 'text-green-500' : t.failed ? 'text-red-400' : 'text-gray-400'"
              class="shrink-0"
            />
            <span class="font-medium truncate">{{ t.keyword }}</span>
            <span v-if="t.completed" class="text-gray-400 shrink-0">{{ t.articles_count }} 篇</span>
            <span v-else-if="t.failed" class="text-red-400 shrink-0">失败</span>
          </div>
        </div>
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

      <!-- 渠道级警告 -->
      <div
        v-for="(ch, chKey) in channelWarnings"
        :key="chKey"
        class="p-3 rounded-lg border border-red-200 bg-red-50 dark:bg-red-900/20 flex items-start gap-2"
      >
        <UIcon name="i-heroicons-exclamation-triangle" class="text-red-500 mt-0.5 shrink-0" />
        <p class="text-sm text-red-700 dark:text-red-300">{{ ch.note }}</p>
      </div>

      <!-- 逐维度评估 -->
      <div v-if="probeReview.assessments?.length" class="space-y-3">
        <!-- 按维度分组 -->
        <template v-if="assessmentDimensionGroups">
          <div
            v-for="(group, dimName) in assessmentDimensionGroups"
            :key="dimName"
            class="space-y-1.5"
          >
            <!-- 维度标题 + 通过率 -->
            <div class="flex items-center gap-2">
              <span class="text-xs font-medium text-gray-500">{{ dimName }}</span>
              <span
                class="text-xs"
                :class="group.failCount > 0 ? 'text-amber-500' : 'text-green-500'"
              >
                {{ group.assessments.length - group.failCount }}/{{ group.assessments.length }} 通过
              </span>
            </div>
            <div class="grid md:grid-cols-2 gap-1.5">
              <div
                v-for="a in group.assessments"
                :key="a.task_id"
                class="text-xs p-2 rounded border"
                :class="a.verdict === 'pass'
                  ? 'border-green-200 bg-green-50 dark:bg-green-900/10'
                  : 'border-amber-200 bg-amber-50 dark:bg-amber-900/10'"
              >
                <div class="flex items-center gap-1.5">
                  <UIcon
                    :name="a.verdict === 'pass' ? 'i-heroicons-check-circle' : 'i-heroicons-exclamation-triangle'"
                    :class="a.verdict === 'pass' ? 'text-green-500' : 'text-amber-500'"
                    class="shrink-0 size-3.5"
                  />
                  <span class="font-medium truncate">{{ a.keyword }}</span>
                  <UBadge variant="subtle" size="sm" color="neutral" class="shrink-0">{{ platformLabel(a.platform) }}</UBadge>
                </div>
                <p v-if="a.note" class="text-gray-500 mt-0.5 line-clamp-2">{{ a.note }}</p>
              </div>
            </div>
          </div>
        </template>

        <!-- 兜底：无维度映射时平铺 -->
        <template v-else>
          <h4 class="text-xs font-medium text-gray-500">逐任务评估</h4>
          <div class="grid md:grid-cols-2 gap-1.5">
            <div
              v-for="a in probeReview.assessments"
              :key="a.task_id"
              class="text-xs p-2 rounded border"
              :class="a.verdict === 'pass'
                ? 'border-green-200 bg-green-50 dark:bg-green-900/10'
                : 'border-amber-200 bg-amber-50 dark:bg-amber-900/10'"
            >
              <div class="flex items-center gap-1.5">
                <UIcon
                  :name="a.verdict === 'pass' ? 'i-heroicons-check-circle' : 'i-heroicons-exclamation-triangle'"
                  :class="a.verdict === 'pass' ? 'text-green-500' : 'text-amber-500'"
                  class="shrink-0 size-3.5"
                />
                <span class="font-medium truncate">{{ a.keyword }}</span>
                <UBadge variant="subtle" size="sm" color="neutral" class="shrink-0">{{ platformLabel(a.platform) }}</UBadge>
              </div>
              <p v-if="a.note" class="text-gray-500 mt-0.5 line-clamp-2">{{ a.note }}</p>
            </div>
          </div>
        </template>
      </div>

      <!-- 调整建议 -->
      <div v-if="probeReview.refinement_suggestions?.length" class="space-y-2">
        <h4 class="text-xs font-medium text-gray-500">
          {{ readonly ? 'AI 调整建议（历史记录，仅供参考）' : 'AI 调整建议（默认采纳，可逐条改词/删除/跳过）' }}
        </h4>
        <div
          v-for="(s, i) in probeReview.refinement_suggestions"
          :key="i"
          class="text-sm p-2.5 rounded space-y-2 transition-colors"
          :class="readonly ? 'bg-gray-50 dark:bg-gray-800' : rowBg(decisions[i]?.action)"
        >
          <div class="flex items-center gap-2 flex-wrap">
            <span class="text-gray-500 line-through">{{ s.original_keyword }}</span>
            <UIcon name="i-heroicons-arrow-right" class="text-gray-400 text-xs shrink-0" />
            <span v-if="s.suggested_keyword" class="font-medium text-amber-700 dark:text-amber-300">{{ s.suggested_keyword }}</span>
            <UBadge v-else variant="subtle" size="sm" color="error" class="shrink-0">建议移除</UBadge>
            <UBadge variant="subtle" size="sm" color="neutral" class="shrink-0">{{ platformLabel(s.platform) }}</UBadge>

            <div v-if="!readonly" class="ml-auto flex items-center gap-1">
              <UButton
                size="xs"
                :variant="(decisions[i]?.action ?? 'accept') === 'accept' ? 'solid' : 'ghost'"
                color="primary"
                @click="setAction(i, 'accept')"
              >
                采纳
              </UButton>
              <UButton
                size="xs"
                :variant="decisions[i]?.action === 'edit' ? 'solid' : 'ghost'"
                color="primary"
                @click="setAction(i, 'edit')"
              >
                改词
              </UButton>
              <UButton
                size="xs"
                :variant="decisions[i]?.action === 'delete' ? 'solid' : 'ghost'"
                color="error"
                @click="setAction(i, 'delete')"
              >
                删除任务
              </UButton>
              <UButton
                size="xs"
                :variant="decisions[i]?.action === 'skip' ? 'solid' : 'ghost'"
                color="neutral"
                @click="setAction(i, 'skip')"
              >
                保留原状
              </UButton>
            </div>
          </div>

          <UInput
            v-if="!readonly && decisions[i]?.action === 'edit'"
            v-model="decisions[i]!.customKeyword"
            placeholder="输入新关键词，留空 = 删除任务"
            size="xs"
            class="w-full"
          />

          <p v-if="s.reason" class="text-xs text-gray-500">{{ s.reason }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { SocialProbeTaskStatus, NewsProbeTaskStatus, ProbeReviewResult, ProbeAssessment, SocialRefinementItem, NewsRefinementItem } from '../types'
import { platformLabel } from '../composables/useStrategyConstants'

/** 用户对每条 AI 建议的处置 */
type DecisionAction = 'accept' | 'edit' | 'delete' | 'skip'
interface Decision {
  action: DecisionAction
  /** edit 模式下用户输入的自定义关键词 */
  customKeyword?: string
}

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
  socialTasks: SocialProbeTaskStatus[]
  newsTasks: NewsProbeTaskStatus[]
  analyzedCount: number
  totalCount: number
  allAnalyzed: boolean
  probeReview: ProbeReviewResult | null
  /** task_id(string) → dimension_name 映射，用于按维度分组展示 */
  taskDimensionMap?: Record<string, string>
  /** data_plan 维度名称有序列表，决定分组顺序 */
  dimensionNames?: string[]
  /** 当前策略关联的 SocialMonitor ID，用于失败任务横幅深链跳转到监测项目页 */
  socialMonitorId?: number | null
  /** 只读模式：探测阶段已结束（status > probing 或无编辑权限）时为 true，
   *  此时调整建议区域隐藏 per-item 动作按钮，仅作历史展示 */
  readonly?: boolean
}>()

/** 失败的社媒任务计数：方案 B 下这些任务阻塞 all_analyzed，需要 retry 或人工删除 */
const failedSocialCount = computed(
  () => props.socialTasks.filter(t => t.status === 'failed').length,
)

const progressPercent = computed(() => {
  if (props.totalCount === 0) return 0
  return Math.round((props.analyzedCount / props.totalCount) * 100)
})

const verdictInfo = computed(() => {
  const v = props.probeReview?.overall_verdict
  return VERDICT_MAP[v || 'fail'] || VERDICT_MAP.fail
})

/** 渠道级警告：筛选 channel_summary 中 all_fail 的渠道 */
const channelWarnings = computed(() => {
  const summary = props.probeReview?.channel_summary
  if (!summary) return {}
  return Object.fromEntries(
    Object.entries(summary).filter(([, ch]) => ch.channel_verdict === 'all_fail'),
  )
})

/** 按维度分组的社媒任务状态 */
const dimensionGroups = computed((): Record<string, SocialProbeTaskStatus[]> | null => {
  if (!props.taskDimensionMap || !props.dimensionNames?.length || !props.socialTasks.length) return null

  const groups: Record<string, SocialProbeTaskStatus[]> = {}
  for (const dim of props.dimensionNames) groups[dim] = []

  for (const task of props.socialTasks) {
    const dim = props.taskDimensionMap[String(task.task_id)]
    if (dim) {
      if (!groups[dim]) groups[dim] = []
      groups[dim].push(task)
    }
  }

  return Object.fromEntries(Object.entries(groups).filter(([, tasks]) => tasks.length > 0))
})

/** 按维度分组的新闻任务状态 */
const newsTaskDimensionGroups = computed((): Record<string, NewsProbeTaskStatus[]> => {
  const groups: Record<string, NewsProbeTaskStatus[]> = {}
  for (const task of props.newsTasks) {
    const dim = task.dimension || '新闻'
    if (!groups[dim]) groups[dim] = []
    groups[dim].push(task)
  }
  return groups
})

/** 简易相对时间格式化（中文，用于失败任务的"失败于 X 分钟前"）*/
const formatRelativeTime = (iso: string | null): string => {
  if (!iso) return ''
  const ts = new Date(iso).getTime()
  if (Number.isNaN(ts)) return ''
  const diffSec = Math.max(0, Math.floor((Date.now() - ts) / 1000))
  if (diffSec < 60) return '刚刚'
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return `${diffMin} 分钟前`
  const diffHour = Math.floor(diffMin / 60)
  if (diffHour < 24) return `${diffHour} 小时前`
  return `${Math.floor(diffHour / 24)} 天前`
}

/** 失败任务卡片的 hover 提示，给出明确的 next-step 指引 */
const socialTaskTooltip = (t: SocialProbeTaskStatus): string | undefined => {
  if (t.status !== 'failed') return undefined
  const when = formatRelativeTime(t.last_updated_at)
  return `失败${when ? '于 ' + when : ''} — 等待自动续采，或前往监测项目页删除该任务以继续`
}

/** 社媒任务卡片视觉状态：失败 → 红，已分析（成功或终态无数据）→ 绿，其他 → 灰
 *
 * 方案 B 下后端不再把 failed 计入 has_analysis，但这里仍用 status 作优先判定，
 * 即便未来 has_analysis 语义再调整也保持视觉一致。
 */
const socialTaskBg = (t: SocialProbeTaskStatus): string => {
  if (t.status === 'failed') return 'bg-red-50 dark:bg-red-900/20'
  if (t.has_analysis) return 'bg-green-50 dark:bg-green-900/20'
  return 'bg-gray-50 dark:bg-gray-800'
}

const socialTaskIcon = (t: SocialProbeTaskStatus): string => {
  if (t.status === 'failed') return 'i-heroicons-x-circle'
  if (t.has_analysis) return 'i-heroicons-check-circle'
  return 'i-heroicons-clock'
}

const socialTaskIconColor = (t: SocialProbeTaskStatus): string => {
  if (t.status === 'failed') return 'text-red-500'
  if (t.has_analysis) return 'text-green-500'
  return 'text-gray-400'
}

/** 用户对 AI 调整建议的逐条处置（key = suggestion 在数组中的索引）
 *
 * 默认行为：所有建议初始为 'accept'，与之前"整批接受"语义一致。
 * 用户可通过按钮切换 edit/delete/skip 进行 per-item 控制。
 * probeReview 变化时（如新一轮 review）自动重置。
 */
const decisions = reactive<Record<number, Decision>>({})

watch(
  () => props.probeReview?.refinement_suggestions,
  (suggestions) => {
    // 清空旧 decisions：用 length=0 清空 + 重新填充，避免 dynamic delete
    Object.keys(decisions).forEach((key) => {
      decisions[Number(key)] = { action: 'accept' }
    })
    if (!suggestions?.length) return
    // 重置为新一轮建议，默认全部 accept
    suggestions.forEach((_, i) => {
      decisions[i] = { action: 'accept' }
    })
  },
  { immediate: true },
)

const setAction = (i: number, action: DecisionAction) => {
  if (!decisions[i]) decisions[i] = { action }
  else decisions[i].action = action
}

const rowBg = (action?: DecisionAction): string => {
  switch (action) {
    case 'edit': return 'bg-blue-50 dark:bg-blue-900/20'
    case 'delete': return 'bg-red-50 dark:bg-red-900/20'
    case 'skip': return 'bg-gray-100 dark:bg-gray-800'
    case 'accept':
    default:
      return 'bg-amber-50 dark:bg-amber-900/20'
  }
}

/** 根据用户决策构造 refine_probe API 的 payload。
 *
 * - skip: 不进 list（保留任务原状）
 * - accept: 用 AI 的 suggested_keyword
 * - edit: 用用户自定义词；trim 后为空则归一化为 null = 删除任务
 * - delete: new_keyword 强制为 null = 删除任务
 *
 * 返回按 channel 拆分的两个数组，供父组件直接传入 refine API。
 */
const buildRefinements = (): { social: SocialRefinementItem[]; news: NewsRefinementItem[] } => {
  const review = props.probeReview
  if (!review?.refinement_suggestions?.length) return { social: [], news: [] }

  const social: SocialRefinementItem[] = []
  const news: NewsRefinementItem[] = []

  review.refinement_suggestions.forEach((s, i) => {
    const decision = decisions[i] ?? { action: 'accept' as DecisionAction }
    if (decision.action === 'skip') return

    let new_keyword: string | null
    if (decision.action === 'accept') new_keyword = s.suggested_keyword || null
    else if (decision.action === 'edit') new_keyword = (decision.customKeyword ?? '').trim() || null
    else /* delete */ new_keyword = null

    if (s.platform === 'news_media') {
      news.push({ task_id: s.task_id, new_keyword })
    } else {
      social.push({ task_id: s.task_id, new_keyword, platform: s.platform })
    }
  })

  return { social, news }
}

/** 用户决策的可读 summary（确认对话框展示用）：仅含非 skip 项 */
const decisionsSummary = (): string => {
  const review = props.probeReview
  if (!review?.refinement_suggestions?.length) return ''

  const parts: string[] = []
  review.refinement_suggestions.forEach((s, i) => {
    const decision = decisions[i] ?? { action: 'accept' as DecisionAction }
    if (decision.action === 'skip') return

    let target: string
    if (decision.action === 'accept') target = s.suggested_keyword || '(移除)'
    else if (decision.action === 'edit') target = (decision.customKeyword ?? '').trim() || '(移除)'
    else target = '(移除)'

    parts.push(`${s.original_keyword} → ${target}`)
  })
  return parts.join('、')
}

defineExpose({ buildRefinements, decisionsSummary })

/** 按维度分组的审查结果（用于 probeReview 展示） */
const assessmentDimensionGroups = computed((): Record<string, { assessments: ProbeAssessment[], failCount: number }> | null => {
  if (!props.taskDimensionMap || !props.dimensionNames?.length || !props.probeReview?.assessments?.length) return null

  const groups: Record<string, { assessments: ProbeAssessment[], failCount: number }> = {}
  for (const dim of props.dimensionNames) groups[dim] = { assessments: [], failCount: 0 }

  for (const a of props.probeReview.assessments) {
    const dim = props.taskDimensionMap[String(a.task_id)] || '其他'
    if (!groups[dim]) groups[dim] = { assessments: [], failCount: 0 }
    groups[dim].assessments.push(a)
    if (a.verdict === 'fail') groups[dim].failCount++
  }

  return Object.fromEntries(Object.entries(groups).filter(([, g]) => g.assessments.length > 0))
})
</script>
