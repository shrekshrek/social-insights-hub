<script setup lang="ts">
import { h, computed, reactive, ref, watch, onMounted, onUnmounted, resolveComponent } from 'vue'
import type { TableColumn } from '@nuxt/ui'
import type {
  PostAnalysisWithPostInfo,
  AnalysisJob,
  DeepAnalysisPreview,
  TaskAnalysisResultData,
} from '../../../../../analysis/types'
import ExpandableText from '../../../../../analysis/components/ExpandableText.vue'
import PostDeepAnalysisResult from '../../../../../analysis/components/PostDeepAnalysisResult.vue'
import CommentDeepAnalysisResult from '../../../../../analysis/components/CommentDeepAnalysisResult.vue'
import TaskAnalysisReport from '../../../../../analysis/components/TaskAnalysisReport.vue'

const props = defineProps<{
  taskId: number
}>()

const toast = useToast()

const {
  getAnalysisJobs,
  getTaskPostAnalyses,
  getDeepAnalysisPreview,
  runPostScreening,
  runPostDeepAnalysis,
  runCommentDeepAnalysis,
  deleteTaskAnalyses,
  runTaskAggregation,
  getTaskAggregation,
} = useAnalysis()

/** 任务历史（用于运行中状态提示，按 task_id 筛选） */
const analysisJobsParams = computed(() => ({
  task_id: props.taskId,
  page_size: 50,
}))

const {
  data: analysisHistory,
  refresh: refreshHistory,
} = getAnalysisJobs(analysisJobsParams)

/** 统一的帖子分析列表 */
const page = ref(1)
const pageSize = ref(20)
const filterAnalyzed = ref(false)

// 搜索状态
const searchQuery = ref('')
const searchId = ref<number | null>(null)

const {
  data: postAnalysisData,
  pending: tableLoading,
  refresh: refreshPostAnalysis,
} = getTaskPostAnalyses(props.taskId, {
  page,
  pageSize,
  filterAnalyzed,
  searchQuery,
  searchId,
})

watch([page, pageSize, filterAnalyzed, searchQuery, searchId], () => {
  refreshPostAnalysis()
})

const rows = computed(() => postAnalysisData.value?.items || [])
const total = computed(() => postAnalysisData.value?.total || 0)

const formatNumber = (num?: number | null) => {
  if (num == null) return '-'
  if (num >= 10000) return `${(num / 10000).toFixed(1)}万`
  return num.toLocaleString()
}

const formatDateTime = (value?: string | null): { date: string; time: string } | null => {
  if (!value) return null
  const d = new Date(value)
  if (isNaN(d.getTime())) return null
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const hour = String(d.getHours()).padStart(2, '0')
  const min = String(d.getMinutes()).padStart(2, '0')
  return {
    date: `${year}-${month}-${day}`,
    time: `${hour}:${min}`,
  }
}

/** 阈值筛选 */
const thresholds = reactive({
  spamMax: 5,
  valueMin: 3,
  relevanceMin: 3,
})

// 深度分析对话框状态
const deepDialogOpen = ref(false)
const dialogThresholds = reactive({
  spamMax: 5,
  valueMin: 3,
  relevanceMin: 3,
})
const dialogPreview = ref<DeepAnalysisPreview | null>(null)
const dialogPreviewLoading = ref(false)

/** 深度分析预览（后端计算） */
const preview = ref<DeepAnalysisPreview | null>(null)
const previewLoading = ref(false)

const loadPreview = async () => {
  previewLoading.value = true
  try {
    preview.value = await getDeepAnalysisPreview(props.taskId, {
      spam_max: thresholds.spamMax,
      value_min: thresholds.valueMin,
      relevance_min: thresholds.relevanceMin,
    })
  } catch (error) {
    toast.add({ title: '获取预览失败', description: String(error), color: 'error' })
  } finally {
    previewLoading.value = false
  }
}

onMounted(() => {
  loadPreview()
})

watch(
  () => [thresholds.spamMax, thresholds.valueMin, thresholds.relevanceMin],
  () => {
    loadPreview()
  },
)

const deepCandidateIds = computed(() => preview.value?.deep_candidate_ids || [])
const commentCandidateIds = computed(() => preview.value?.comment_candidate_ids || [])
const matchedCount = computed(() => preview.value?.matched_count ?? 0)
const totalPostsCount = computed(() => preview.value?.total_posts ?? 0)

const processingTasks = computed<AnalysisJob[]>(() =>
  (analysisHistory.value?.items || []).filter((item) =>
    ['pending', 'processing'].includes(item.status),
  ),
)
const hasRunningTask = computed(() => processingTasks.value.length > 0)

// 初筛任务（用于显示进度）
const screeningTask = computed<AnalysisJob | undefined>(() =>
  (analysisHistory.value?.items || []).find(
    (item) =>
      item.analysis_type === 'screening_posts' &&
      ['pending', 'processing'].includes(item.status)
  ),
)

// 原文深度任务（用于显示进度）
const deepPostsTask = computed<AnalysisJob | undefined>(() =>
  (analysisHistory.value?.items || []).find(
    (item) =>
      item.analysis_type === 'deep_posts' &&
      ['pending', 'processing'].includes(item.status)
  ),
)

// 评论深度任务（用于显示进度）
const deepCommentsTask = computed<AnalysisJob | undefined>(() =>
  (analysisHistory.value?.items || []).find(
    (item) =>
      item.analysis_type === 'deep_comments' &&
      ['pending', 'processing'].includes(item.status)
  ),
)

// 依赖状态：是否有初筛结果
const hasScreeningResult = computed(() => (preview.value?.screened_count ?? 0) > 0)
// 依赖状态：是否有原文深度结果
const hasDeepResult = computed(() => (preview.value?.deep_done ?? 0) > 0)
// 依赖状态：未初筛的帖子数量
const unscreenedCount = computed(() => {
  const total = preview.value?.total_posts ?? 0
  const screened = preview.value?.screened_count ?? 0
  return total - screened
})
// 依赖状态：是否所有帖子都已初筛
const allPostsScreened = computed(() => {
  const total = preview.value?.total_posts ?? 0
  return total > 0 && unscreenedCount.value === 0
})

const actionLoading = reactive({
  screening: false,
  deep: false,
  comment: false,
  delete: false,
  aggregate: false,
})

// ==================== 聚合分析报告 ====================

/** 获取聚合分析结果 */
const {
  data: analysisResultData,
  pending: analysisResultLoading,
  refresh: refreshAnalysisResult,
} = getTaskAggregation(props.taskId)

const analysisResult = computed<TaskAnalysisResultData | null>(() => {
  return analysisResultData.value?.result || null
})

const hasAnalysisResult = computed(() => !!analysisResult.value)

/** 报告生成时间 */
const reportGeneratedAt = computed(() => {
  if (!analysisResultData.value?.analyzed_at) return null
  return new Date(analysisResultData.value.analyzed_at).toLocaleString('zh-CN')
})

/** 生成分析报告 */
const handleGenerateReport = async () => {
  if (!ensureNotRunning()) return

  actionLoading.aggregate = true
  try {
    await runTaskAggregation(props.taskId)
    await refreshAnalysisResult()
  } catch {
    // 错误已由 apiRequest 处理并显示 toast
  } finally {
    actionLoading.aggregate = false
  }
}

// 删除分析结果对话框状态
const deleteDialogOpen = ref(false)

const refreshAll = async () => {
  await Promise.all([refreshHistory(), refreshPostAnalysis(), loadPreview()])
}

// 自动轮询机制
let pollTimer: ReturnType<typeof setInterval> | null = null

const startPolling = () => {
  if (pollTimer) return
  pollTimer = setInterval(() => {
    refreshHistory()
  }, 3000)
}

const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

watch(hasRunningTask, (isRunning) => {
  if (isRunning) {
    startPolling()
  } else {
    stopPolling()
    refreshAll()
  }
})

onMounted(() => {
  if (hasRunningTask.value) {
    startPolling()
  }
})

onUnmounted(() => {
  stopPolling()
})

// 搜索处理
const handleSearch = () => {
  page.value = 1
  refreshPostAnalysis()
}

const handleClearSearch = () => {
  searchQuery.value = ''
  searchId.value = null
  page.value = 1
  refreshPostAnalysis()
}

// 对话框预览加载
let dialogPreviewTimer: ReturnType<typeof setTimeout> | null = null

const loadDialogPreview = async () => {
  dialogPreviewLoading.value = true
  try {
    dialogPreview.value = await getDeepAnalysisPreview(props.taskId, {
      spam_max: dialogThresholds.spamMax,
      value_min: dialogThresholds.valueMin,
      relevance_min: dialogThresholds.relevanceMin,
    })
  } catch (error) {
    console.error('Failed to load dialog preview:', error)
  } finally {
    dialogPreviewLoading.value = false
  }
}

const debouncedLoadDialogPreview = () => {
  if (dialogPreviewTimer) {
    clearTimeout(dialogPreviewTimer)
  }
  dialogPreviewTimer = setTimeout(() => {
    loadDialogPreview()
  }, 500)
}

watch(
  () => [dialogThresholds.spamMax, dialogThresholds.valueMin, dialogThresholds.relevanceMin],
  () => {
    if (deepDialogOpen.value) {
      debouncedLoadDialogPreview()
    }
  }
)

const openDeepAnalysisDialog = () => {
  dialogThresholds.spamMax = thresholds.spamMax
  dialogThresholds.valueMin = thresholds.valueMin
  dialogThresholds.relevanceMin = thresholds.relevanceMin
  deepDialogOpen.value = true
  loadDialogPreview()
}

const handleConfirmDeepAnalysis = async () => {
  thresholds.spamMax = dialogThresholds.spamMax
  thresholds.valueMin = dialogThresholds.valueMin
  thresholds.relevanceMin = dialogThresholds.relevanceMin
  deepDialogOpen.value = false
  await handleDeep()
}

// 评论深度分析弹窗状态
const commentDialogOpen = ref(false)
const commentDialogPreview = ref<DeepAnalysisPreview | null>(null)
const commentDialogPreviewLoading = ref(false)

const loadCommentDialogPreview = async () => {
  commentDialogPreviewLoading.value = true
  try {
    commentDialogPreview.value = await getDeepAnalysisPreview(props.taskId, {
      spam_max: thresholds.spamMax,
      value_min: thresholds.valueMin,
      relevance_min: thresholds.relevanceMin,
    })
  } catch (error) {
    console.error('Failed to load comment dialog preview:', error)
  } finally {
    commentDialogPreviewLoading.value = false
  }
}

const openCommentAnalysisDialog = () => {
  commentDialogOpen.value = true
  loadCommentDialogPreview()
}

const handleConfirmCommentAnalysis = async () => {
  commentDialogOpen.value = false
  await handleComment()
}

const ensureNotRunning = () => {
  if (hasRunningTask.value) {
    toast.add({
      title: '有任务正在执行',
      description: '请等待当前分析任务完成后再发起新的分析',
      color: 'warning',
    })
    return false
  }
  return true
}

const handleScreening = async () => {
  if (!ensureNotRunning()) return
  actionLoading.screening = true
  try {
    await runPostScreening(props.taskId)
    await refreshAll()
  } catch {
    // 错误已由 apiRequest 处理并显示 toast
  } finally {
    actionLoading.screening = false
  }
}

const handleDeep = async () => {
  if (!ensureNotRunning()) return
  if (deepCandidateIds.value.length === 0) {
    toast.add({
      title: '没有符合条件的帖子',
      description: '请先完成初筛，或调整阈值后再试',
      color: 'warning',
    })
    return
  }

  actionLoading.deep = true
  try {
    await runPostDeepAnalysis(props.taskId, {
      spam_max: thresholds.spamMax,
      value_min: thresholds.valueMin,
      relevance_min: thresholds.relevanceMin,
    })
    await refreshAll()
  } catch {
    // 错误已由 apiRequest 处理并显示 toast
  } finally {
    actionLoading.deep = false
  }
}

const handleComment = async () => {
  if (!ensureNotRunning()) return
  if (commentCandidateIds.value.length === 0) {
    toast.add({
      title: '没有可分析的评论',
      description: '需要先有原文深度分析结果且该贴有评论',
      color: 'warning',
    })
    return
  }

  actionLoading.comment = true
  try {
    await runCommentDeepAnalysis(props.taskId, {
      spam_max: thresholds.spamMax,
      value_min: thresholds.valueMin,
      relevance_min: thresholds.relevanceMin,
    })
    await refreshAll()
  } catch {
    // 错误已由 apiRequest 处理并显示 toast
  } finally {
    actionLoading.comment = false
  }
}

// 删除分析结果
const openDeleteDialog = () => {
  deleteDialogOpen.value = true
}

const handleDeleteAnalyses = async () => {
  if (!ensureNotRunning()) return

  actionLoading.delete = true
  try {
    await deleteTaskAnalyses(props.taskId)
    deleteDialogOpen.value = false
    await refreshAll()
  } catch {
    // 错误已由 apiRequest 处理并显示 toast，保持对话框打开以便重试
  } finally {
    actionLoading.delete = false
  }
}

// 深度分析结果弹窗
const deepResultModalOpen = ref(false)
const deepResultModalType = ref<'post' | 'comment'>('post')
const deepResultModalPostId = ref<number | null>(null)

const selectedPostForDeepResult = computed(() => {
  if (!deepResultModalPostId.value) return null
  return rows.value.find(r => r.post_id === deepResultModalPostId.value) || null
})

const openDeepResultModal = (postId: number, type: 'post' | 'comment') => {
  deepResultModalPostId.value = postId
  deepResultModalType.value = type
  deepResultModalOpen.value = true
}

/** 统一表格列定义 */
const columns = computed<TableColumn<PostAnalysisWithPostInfo>[]>(() => {
  if (!import.meta.client) return []

  const UBadge = resolveComponent('UBadge')
  const UIcon = resolveComponent('UIcon')

  return [
    {
      accessorKey: 'post_id',
      header: 'ID',
      size: 40,
      cell: ({ row }) => h('span', { class: 'text-xs text-gray-500 font-mono' }, row.original.post_id),
    },
    {
      accessorKey: 'post_id_on_platform',
      header: '平台ID',
      size: 80,
      cell: ({ row }) => h('span', { class: 'text-xs text-gray-500 font-mono truncate block max-w-[70px]', title: row.original.post_id_on_platform || '-' }, row.original.post_id_on_platform || '-'),
    },
    {
      accessorKey: 'content',
      header: '标题/内容',
      size: 180,
      cell: ({ row }) =>
        h(ExpandableText, {
          title: row.original.title || '',
          content: row.original.content || '',
          maxLength: 30,
        }),
    },
    {
      accessorKey: 'scores',
      header: '初筛',
      size: 65,
      cell: ({ row }) => {
        const { spam_score, value_score, relevance_score } = row.original
        const scoreText = (label: string, value?: number | null) =>
          h('div', { class: 'flex items-center gap-1 text-xs' }, [
            h('span', { class: 'text-gray-500' }, label),
            h(
              'span',
              { class: value == null ? 'text-gray-400' : 'font-medium' },
              value == null ? '-' : value.toFixed(1),
            ),
          ])

        return h('div', { class: 'space-y-0.5' }, [
          scoreText('广告', spam_score),
          scoreText('价值', value_score),
          scoreText('相关', relevance_score),
        ])
      },
    },
    {
      accessorKey: 'sentiment',
      header: '情感',
      size: 60,
      cell: ({ row }) => {
        const sentiment = row.original.sentiment
        if (sentiment == null) {
          return h('span', { class: 'text-gray-400 text-xs' }, '-')
        }
        // 五级情感：-2强烈负面, -1轻度负面, 0中性, 1轻度正面, 2强烈正面
        const sentimentMap: Record<number, { color: string; label: string }> = {
          [-2]: { color: 'error', label: '强烈负面' },
          [-1]: { color: 'warning', label: '轻度负面' },
          [0]: { color: 'neutral', label: '中性' },
          [1]: { color: 'info', label: '轻度正面' },
          [2]: { color: 'success', label: '强烈正面' },
        }
        const config = sentimentMap[sentiment] || { color: 'neutral', label: '中性' }
        return h(UBadge, { size: 'xs', color: config.color, variant: 'subtle' }, () => config.label)
      },
    },
    {
      accessorKey: 'cii',
      header: 'CII',
      size: 50,
      cell: ({ row }) => {
        const cii = row.original.cii
        if (cii == null) {
          return h('span', { class: 'text-gray-400 text-xs' }, '-')
        }
        // CII 0-100, 根据值显示不同颜色
        const getColor = (value: number) => {
          if (value >= 70) return 'text-green-600'
          if (value >= 40) return 'text-yellow-600'
          return 'text-gray-600'
        }
        return h('span', { class: `text-sm font-medium ${getColor(cii)}` }, cii.toFixed(1))
      },
    },
    {
      accessorKey: 'deep_analysis',
      header: '深度',
      size: 50,
      cell: ({ row }) => {
        const { post_deep_result, comment_deep_result, post_id } = row.original
        const hasPostDeep = !!post_deep_result
        const hasCommentDeep = !!comment_deep_result

        if (!hasPostDeep && !hasCommentDeep) {
          return h('span', { class: 'text-gray-400 text-xs' }, '-')
        }

        return h('div', { class: 'space-y-1' }, [
          // 原文深度标签
          hasPostDeep
            ? h(
                'button',
                {
                  class: 'flex items-center gap-1 text-xs text-green-600 hover:text-green-700 cursor-pointer',
                  onClick: () => openDeepResultModal(post_id, 'post'),
                },
                [
                  h(UIcon, { name: 'i-heroicons-document-text', class: 'w-3 h-3' }),
                  h('span', {}, '原文'),
                ]
              )
            : null,
          // 评论深度标签
          hasCommentDeep
            ? h(
                'button',
                {
                  class: 'flex items-center gap-1 text-xs text-orange-600 hover:text-orange-700 cursor-pointer',
                  onClick: () => openDeepResultModal(post_id, 'comment'),
                },
                [
                  h(UIcon, { name: 'i-heroicons-chat-bubble-left-right', class: 'w-3 h-3' }),
                  h('span', {}, '评论'),
                ]
              )
            : null,
        ])
      },
    },
    {
      accessorKey: 'engagement',
      header: '互动',
      size: 70,
      cell: ({ row }) => {
        const { likes_count, comments_count, shares_count, collected_count, views_count, danmaku_count } = row.original
        const items = [
          h('div', {}, `赞 ${formatNumber(likes_count)}`),
          h('div', {}, `评 ${formatNumber(comments_count)}`),
        ]
        // 仅在有数据时显示对应项
        if (shares_count > 0) {
          items.push(h('div', {}, `转 ${formatNumber(shares_count)}`))
        }
        if (collected_count > 0) {
          items.push(h('div', {}, `藏 ${formatNumber(collected_count)}`))
        }
        if (views_count > 0) {
          items.push(h('div', {}, `览 ${formatNumber(views_count)}`))
        }
        if (danmaku_count > 0) {
          items.push(h('div', {}, `弹 ${formatNumber(danmaku_count)}`))
        }
        return h('div', { class: 'text-xs space-y-0.5 text-gray-600 dark:text-gray-400' }, items)
      },
    },
    {
      accessorKey: 'published_at',
      header: '发布时间',
      size: 90,
      cell: ({ row }) => {
        const dt = formatDateTime(row.original.published_at)
        if (!dt) return h('span', { class: 'text-xs text-gray-400' }, '-')
        return h('div', { class: 'text-xs text-gray-500 leading-tight' }, [
          h('div', {}, dt.date),
          h('div', {}, dt.time),
        ])
      },
    },
  ]
})
</script>

<template>
  <div>
    <UCard>
    <template #header>
      <div class="flex items-center justify-between gap-4">
        <h2 class="text-lg font-semibold">
          数据分析与处理
        </h2>

        <div class="flex items-center gap-3">
          <!-- 关键词搜索 -->
          <UInput
            v-model="searchQuery"
            placeholder="搜索内容..."
            icon="i-heroicons-magnifying-glass"
            size="sm"
            class="w-40"
            @keyup.enter="handleSearch"
          />

          <!-- ID 搜索 -->
          <UInput
            v-model.number="searchId"
            type="number"
            placeholder="ID"
            size="sm"
            class="w-24"
            @keyup.enter="handleSearch"
          />

          <!-- 筛选开关 -->
          <UCheckbox
            v-model="filterAnalyzed"
            label="仅已分析"
            size="sm"
          />

          <!-- 重置按钮 -->
          <UButton
            v-if="searchQuery || searchId"
            size="xs"
            variant="ghost"
            icon="i-heroicons-x-mark"
            @click="handleClearSearch"
          />

          <!-- 删除分析结果按钮 -->
          <UButton
            size="sm"
            color="error"
            variant="soft"
            icon="i-heroicons-trash"
            :disabled="hasRunningTask || total === 0"
            @click="openDeleteDialog"
          >
            清空结果
          </UButton>
        </div>
      </div>
    </template>

    <!-- 操作按钮区 + 进度 -->
    <div class="mb-4 flex justify-between items-start flex-wrap gap-3">
      <!-- 左侧：操作按钮 -->
      <div class="flex items-center gap-2 flex-wrap">
        <UTooltip
          :text="allPostsScreened ? '所有帖子已完成初筛' : totalPostsCount === 0 ? '没有帖子数据' : ''"
          :disabled="!allPostsScreened && totalPostsCount > 0"
        >
          <UButton
            size="sm"
            color="primary"
            :loading="actionLoading.screening"
            :disabled="hasRunningTask || allPostsScreened || totalPostsCount === 0"
            icon="i-heroicons-funnel"
            @click="handleScreening"
          >
            原文初筛{{ unscreenedCount > 0 ? ` (${unscreenedCount})` : '' }}
          </UButton>
        </UTooltip>

        <UTooltip
          :text="!hasScreeningResult ? '请先完成原文初筛' : ''"
          :disabled="hasScreeningResult"
        >
          <UButton
            size="sm"
            color="success"
            :loading="actionLoading.deep"
            :disabled="hasRunningTask || !hasScreeningResult"
            icon="i-heroicons-document-text"
            @click="openDeepAnalysisDialog"
          >
            原文深度
          </UButton>
        </UTooltip>

        <UTooltip
          :text="!hasScreeningResult ? '请先完成原文初筛' : !hasDeepResult ? '请先完成原文深度分析' : ''"
          :disabled="hasScreeningResult && hasDeepResult"
        >
          <UButton
            size="sm"
            color="warning"
            :loading="actionLoading.comment"
            :disabled="hasRunningTask || !hasDeepResult"
            icon="i-heroicons-chat-bubble-left-right"
            @click="openCommentAnalysisDialog"
          >
            评论深度
          </UButton>
        </UTooltip>
      </div>

      <!-- 右侧：阈值显示 -->
      <div v-if="preview" class="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400">
        <UBadge color="neutral" variant="subtle" size="xs">
          广告{{ thresholds.spamMax }}
        </UBadge>
        <UBadge color="info" variant="subtle" size="xs">
          价值{{ thresholds.valueMin }}
        </UBadge>
        <UBadge color="success" variant="subtle" size="xs">
          相关{{ thresholds.relevanceMin }}
        </UBadge>
        <span class="text-primary-600 dark:text-primary-400 font-medium">
          符合: {{ matchedCount }}/{{ totalPostsCount }}
        </span>
      </div>
    </div>

    <!-- 初筛任务进度 -->
    <div
      v-if="screeningTask"
      class="mb-4 p-3 border rounded-lg bg-gray-50 dark:bg-gray-800"
    >
      <div class="flex items-center justify-between mb-2">
        <div class="flex items-center gap-2">
          <span class="text-sm font-medium">原文初筛任务</span>
          <UBadge
            :color="screeningTask.status === 'completed' ? 'success' : screeningTask.status === 'failed' ? 'error' : 'primary'"
            size="xs"
          >
            {{ screeningTask.status === 'completed' ? '已完成' : screeningTask.status === 'failed' ? '失败' : '进行中' }}
          </UBadge>
        </div>
        <span class="text-xs text-gray-500">
          {{ screeningTask.analyzed_count || 0 }} / {{ screeningTask.source_count || 0 }}
        </span>
      </div>
      <UProgress
        :model-value="screeningTask.source_count > 0 ? ((screeningTask.analyzed_count || 0) / screeningTask.source_count) * 100 : 0"
        :max="100"
        size="sm"
        :color="screeningTask.status === 'failed' ? 'error' : 'primary'"
      />
      <p v-if="screeningTask.status === 'failed'" class="text-xs text-red-600 mt-2">
        任务执行失败
      </p>
    </div>

    <!-- 原文深度任务进度 -->
    <div
      v-if="deepPostsTask"
      class="mb-4 p-3 border rounded-lg bg-green-50 dark:bg-green-900/20"
    >
      <div class="flex items-center justify-between mb-2">
        <div class="flex items-center gap-2">
          <span class="text-sm font-medium">原文深度分析任务</span>
          <UBadge
            :color="deepPostsTask.status === 'completed' ? 'success' : deepPostsTask.status === 'failed' ? 'error' : 'success'"
            size="xs"
          >
            {{ deepPostsTask.status === 'completed' ? '已完成' : deepPostsTask.status === 'failed' ? '失败' : '进行中' }}
          </UBadge>
        </div>
        <span class="text-xs text-gray-500">
          {{ deepPostsTask.analyzed_count || 0 }} / {{ deepPostsTask.source_count || 0 }}
        </span>
      </div>
      <UProgress
        :model-value="deepPostsTask.source_count > 0 ? ((deepPostsTask.analyzed_count || 0) / deepPostsTask.source_count) * 100 : 0"
        :max="100"
        size="sm"
        :color="deepPostsTask.status === 'failed' ? 'error' : 'success'"
      />
      <p v-if="deepPostsTask.status === 'failed'" class="text-xs text-red-600 mt-2">
        任务执行失败
      </p>
    </div>

    <!-- 评论深度任务进度 -->
    <div
      v-if="deepCommentsTask"
      class="mb-4 p-3 border rounded-lg bg-orange-50 dark:bg-orange-900/20"
    >
      <div class="flex items-center justify-between mb-2">
        <div class="flex items-center gap-2">
          <span class="text-sm font-medium">评论深度分析任务</span>
          <UBadge
            :color="deepCommentsTask.status === 'completed' ? 'success' : deepCommentsTask.status === 'failed' ? 'error' : 'warning'"
            size="xs"
          >
            {{ deepCommentsTask.status === 'completed' ? '已完成' : deepCommentsTask.status === 'failed' ? '失败' : '进行中' }}
          </UBadge>
        </div>
        <span class="text-xs text-gray-500">
          {{ deepCommentsTask.analyzed_count || 0 }} / {{ deepCommentsTask.source_count || 0 }}
        </span>
      </div>
      <UProgress
        :model-value="deepCommentsTask.source_count > 0 ? ((deepCommentsTask.analyzed_count || 0) / deepCommentsTask.source_count) * 100 : 0"
        :max="100"
        size="sm"
        :color="deepCommentsTask.status === 'failed' ? 'error' : 'warning'"
      />
      <p v-if="deepCommentsTask.status === 'failed'" class="text-xs text-red-600 mt-2">
        任务执行失败
      </p>
    </div>

    <!-- 分析结果表格 -->
    <UTable
      sticky
      :data="rows"
      :columns="columns"
      :loading="tableLoading"
      class="max-h-[600px]"
    >
      <template #empty-state>
        <div class="text-center py-10 text-gray-500">
          <UIcon name="i-heroicons-inbox" class="w-10 h-10 mx-auto mb-2 opacity-60" />
          <p class="text-sm">暂无数据，请先执行初筛或深度分析</p>
        </div>
      </template>
    </UTable>

    <!-- 分页 -->
    <template #footer>
      <div class="flex justify-between items-center">
        <div class="text-sm text-gray-500 dark:text-gray-400">
          显示 {{ (page - 1) * pageSize + 1 }} 到
          {{ Math.min(page * pageSize, total) }} 共
          {{ total }} 条记录
        </div>
        <UPagination
          v-model:page="page"
          :total="total"
          :items-per-page="pageSize"
          :sibling-count="2"
        />
      </div>
    </template>
  </UCard>

  <!-- 深度分析对话框 -->
  <UModal
    v-model:open="deepDialogOpen"
    title="设置原文深度分析阈值"
    description="配置筛选条件以确定哪些帖子需要进行深度分析"
    :ui="{ width: 'sm:max-w-xl', footer: 'justify-end' }"
  >
    <template #body>
      <div class="space-y-4">
        <UFormField
          label="最大广告分"
          hint="0-10，分数越低表示内容越自然"
        >
          <UInput
            v-model.number="dialogThresholds.spamMax"
            type="number"
            :min="0"
            :max="10"
            step="0.5"
          />
        </UFormField>

        <UFormField
          label="最小价值分"
          hint="0-10，分数越高表示内容价值越大"
        >
          <UInput
            v-model.number="dialogThresholds.valueMin"
            type="number"
            :min="0"
            :max="10"
            step="0.5"
          />
        </UFormField>

        <UFormField
          label="最小相关分"
          hint="0-10，分数越高表示与项目关键词相关度越高"
        >
          <UInput
            v-model.number="dialogThresholds.relevanceMin"
            type="number"
            :min="0"
            :max="10"
            step="0.5"
          />
        </UFormField>

        <!-- 实时预览 -->
        <div v-if="dialogPreviewLoading" class="text-center text-gray-500 py-4">
          <UIcon name="i-heroicons-arrow-path" class="w-5 h-5 animate-spin mx-auto mb-2" />
          正在加载预览...
        </div>

        <div v-else-if="dialogPreview" class="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
          <p class="text-sm text-gray-700 dark:text-gray-300">
            预计有 <strong class="text-lg text-primary">{{ dialogPreview.matched_count }}</strong> /
            {{ dialogPreview.total_posts }} 条符合条件
            <span class="ml-2 text-gray-500">
              ({{ dialogPreview.total_posts > 0 ? ((dialogPreview.matched_count / dialogPreview.total_posts) * 100).toFixed(1) : '0.0' }}%)
            </span>
          </p>
        </div>
      </div>
    </template>

    <template #footer>
      <UButton
        label="取消"
        color="neutral"
        variant="outline"
        @click="deepDialogOpen = false"
      />
      <UButton
        :label="`确定分析 (${dialogPreview?.matched_count || 0} 条)`"
        color="primary"
        :loading="actionLoading.deep"
        :disabled="!dialogPreview || dialogPreview.matched_count === 0"
        @click="handleConfirmDeepAnalysis"
      />
    </template>
  </UModal>

  <!-- 评论深度分析预览弹窗 -->
  <UModal
    v-model:open="commentDialogOpen"
    title="评论深度分析预览"
    description="对已完成原文深度分析且有评论的帖子进行评论内容分析"
    :ui="{ width: 'sm:max-w-xl', footer: 'justify-end' }"
  >
    <template #body>
      <div class="space-y-4">
        <p class="text-sm text-gray-600 dark:text-gray-400">
          评论深度分析将对已完成原文深度分析且有评论的帖子进行评论内容分析，提取评论中的实体和观点。
        </p>

        <!-- 加载状态 -->
        <div v-if="commentDialogPreviewLoading" class="text-center text-gray-500 py-4">
          <UIcon name="i-heroicons-arrow-path" class="w-5 h-5 animate-spin mx-auto mb-2" />
          正在加载预览...
        </div>

        <!-- 预览信息 -->
        <div v-else-if="commentDialogPreview" class="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg space-y-2">
          <div class="flex justify-between text-sm">
            <span class="text-gray-500">已初筛帖子</span>
            <span class="font-medium">{{ commentDialogPreview.screened_count }} 条</span>
          </div>
          <div class="flex justify-between text-sm">
            <span class="text-gray-500">已完成原文深度</span>
            <span class="font-medium">{{ commentDialogPreview.deep_done }} 条</span>
          </div>
          <div class="flex justify-between text-sm">
            <span class="text-gray-500">已完成评论深度</span>
            <span class="font-medium">{{ commentDialogPreview.comment_done }} 条</span>
          </div>
          <hr class="border-gray-200 dark:border-gray-700">
          <div class="flex justify-between text-sm">
            <span class="text-gray-700 dark:text-gray-300 font-medium">待分析评论的帖子</span>
            <span class="text-lg font-bold text-warning">{{ commentDialogPreview.comment_candidate_ids?.length || 0 }} 条</span>
          </div>
          <p class="text-xs text-gray-500 mt-2">
            仅分析已完成原文深度分析且有评论的帖子
          </p>
        </div>
      </div>
    </template>

    <template #footer>
      <UButton
        label="取消"
        color="neutral"
        variant="outline"
        @click="commentDialogOpen = false"
      />
      <UButton
        :label="`开始分析 (${commentDialogPreview?.comment_candidate_ids?.length || 0} 条)`"
        color="warning"
        :loading="actionLoading.comment"
        :disabled="!commentDialogPreview || (commentDialogPreview.comment_candidate_ids?.length || 0) === 0"
        @click="handleConfirmCommentAnalysis"
      />
    </template>
  </UModal>

  <!-- 深度分析结果弹窗 -->
  <UModal
    v-model:open="deepResultModalOpen"
    :title="deepResultModalType === 'post' ? '原文深度分析结果' : '评论深度分析结果'"
    :ui="{ width: 'sm:max-w-2xl', footer: 'justify-end' }"
  >
    <template #body>
      <div v-if="selectedPostForDeepResult" class="space-y-4">
        <!-- 帖子标题 -->
        <div class="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
          <p class="text-sm font-medium text-gray-900 dark:text-gray-100">
            {{ selectedPostForDeepResult.title || '无标题' }}
          </p>
        </div>

        <!-- 原文深度结果 -->
        <PostDeepAnalysisResult
          v-if="deepResultModalType === 'post' && selectedPostForDeepResult.post_deep_result"
          :data="selectedPostForDeepResult.post_deep_result"
        />

        <!-- 评论深度结果 -->
        <CommentDeepAnalysisResult
          v-else-if="deepResultModalType === 'comment' && selectedPostForDeepResult.comment_deep_result"
          :data="selectedPostForDeepResult.comment_deep_result"
        />

        <div v-else class="text-center text-gray-500 py-4">
          暂无分析结果
        </div>
      </div>
    </template>

    <template #footer>
      <UButton
        label="关闭"
        color="neutral"
        variant="outline"
        @click="deepResultModalOpen = false"
      />
    </template>
  </UModal>

  <!-- 删除分析结果确认对话框 -->
  <UModal
    v-model:open="deleteDialogOpen"
    title="确认删除分析结果"
    :ui="{ width: 'sm:max-w-md', footer: 'justify-end' }"
  >
    <template #body>
      <div class="space-y-4">
        <div class="flex items-center gap-3 p-4 bg-red-50 dark:bg-red-900/20 rounded-lg">
          <UIcon name="i-heroicons-exclamation-triangle" class="w-8 h-8 text-red-500" />
          <div>
            <p class="font-medium text-red-700 dark:text-red-400">此操作不可撤销</p>
            <p class="text-sm text-red-600 dark:text-red-400/80">删除后需要重新运行分析任务</p>
          </div>
        </div>

        <p class="text-sm text-gray-600 dark:text-gray-400">
          将删除此任务下所有帖子的分析结果，包括：
        </p>
        <ul class="text-sm text-gray-600 dark:text-gray-400 list-disc list-inside space-y-1">
          <li>初筛评分（广告分、价值分、相关度、情感）</li>
          <li>原文深度分析结果（实体、观点、摘要）</li>
          <li>评论深度分析结果</li>
        </ul>

        <div class="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
          <p class="text-sm">
            当前共有 <strong class="text-lg text-primary">{{ total }}</strong> 条分析记录将被删除
          </p>
        </div>
      </div>
    </template>

    <template #footer>
      <UButton
        label="取消"
        color="neutral"
        variant="outline"
        @click="deleteDialogOpen = false"
      />
      <UButton
        label="确认删除"
        color="error"
        :loading="actionLoading.delete"
        @click="handleDeleteAnalyses"
      />
    </template>
  </UModal>

  <!-- 分析报告区块 -->
  <UCard class="mt-6">
    <template #header>
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-3">
          <h2 class="text-lg font-semibold">分析报告</h2>
          <UBadge v-if="reportGeneratedAt" color="success" variant="subtle" size="xs">
            {{ reportGeneratedAt }} 生成
          </UBadge>
        </div>
        <UButton
          icon="i-heroicons-sparkles"
          :loading="actionLoading.aggregate"
          :disabled="hasRunningTask || !hasScreeningResult"
          @click="handleGenerateReport"
        >
          {{ hasAnalysisResult ? '重新生成' : '生成报告' }}
        </UButton>
      </div>
    </template>

    <!-- 加载状态 -->
    <div v-if="analysisResultLoading" class="text-center py-12">
      <UIcon name="i-heroicons-arrow-path" class="w-8 h-8 animate-spin mx-auto mb-3 text-gray-400" />
      <p class="text-gray-500 dark:text-gray-400">加载报告中...</p>
    </div>

    <!-- 无报告状态 -->
    <div v-else-if="!hasAnalysisResult" class="text-center py-12">
      <UIcon name="i-heroicons-chart-bar" class="w-12 h-12 mx-auto mb-3 text-gray-300 dark:text-gray-600" />
      <p class="text-gray-500 dark:text-gray-400 mb-2">暂无分析报告</p>
      <p class="text-sm text-gray-400 dark:text-gray-500">完成初筛分析后，点击「生成报告」查看聚合分析结果</p>
    </div>

    <!-- 报告内容 -->
    <TaskAnalysisReport
      v-else-if="analysisResult"
      :data="analysisResult"
    />
  </UCard>
  </div>
</template>
