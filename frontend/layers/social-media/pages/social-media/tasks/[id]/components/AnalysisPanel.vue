<script setup lang="ts">
import { h, computed, reactive, ref, watch, onMounted, onUnmounted, resolveComponent } from 'vue'
import type { TableColumn } from '@nuxt/ui'
import type {
  PostAnalysisWithPostInfo,
  AnalysisJob,
  DeepAnalysisPreview,
} from '../../../../../analysis/types'

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

const formatDateTime = (value?: string | null) => {
  if (!value) return '-'
  const date = new Date(value)
  return isNaN(date.getTime()) ? '-' : date.toLocaleString('zh-CN')
}

/** 阈值筛选 */
const thresholds = reactive({
  spamMax: 5,
  valueMin: 6,
  relevanceMin: 6,
})

// 深度分析对话框状态
const deepDialogOpen = ref(false)
const dialogThresholds = reactive({
  spamMax: 5,
  valueMin: 6,
  relevanceMin: 6,
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

const actionLoading = reactive({
  screening: false,
  deep: false,
  comment: false,
})

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
  } catch (error) {
    toast.add({ title: '启动初筛失败', description: String(error), color: 'error' })
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
  } catch (error) {
    toast.add({ title: '启动原文分析失败', description: String(error), color: 'error' })
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
  } catch (error) {
    toast.add({ title: '启动评论分析失败', description: String(error), color: 'error' })
  } finally {
    actionLoading.comment = false
  }
}

// 内容展开状态
const expandedContentId = ref<number | null>(null)

const toggleContent = (postId: number) => {
  expandedContentId.value = expandedContentId.value === postId ? null : postId
}

/** 统一表格列定义 */
const columns = computed<TableColumn<PostAnalysisWithPostInfo>[]>(() => {
  if (!import.meta.client) return []

  const UBadge = resolveComponent('UBadge')

  return [
    {
      accessorKey: 'post_id',
      header: 'ID',
      cell: ({ row }) => h('span', { class: 'text-xs text-gray-500 font-mono' }, row.original.post_id),
    },
    {
      accessorKey: 'content',
      header: '标题/内容',
      cell: ({ row }) => {
        const { title, content, post_id } = row.original
        const isExpanded = expandedContentId.value === post_id
        const titleText = title || ''
        const contentText = content || ''
        const hasLongTitle = titleText.length > 100
        const hasLongContent = contentText.length > 100
        const needsExpand = hasLongTitle || hasLongContent

        return h('div', { class: 'max-w-md' }, [
          // 标题
          titleText
            ? h(
                'p',
                {
                  class: isExpanded
                    ? 'font-medium text-sm whitespace-pre-wrap'
                    : 'font-medium text-sm truncate',
                },
                isExpanded ? titleText : (hasLongTitle ? titleText.substring(0, 100) + '...' : titleText)
              )
            : null,
          // 内容
          h(
            'p',
            {
              class: isExpanded
                ? 'text-xs text-gray-600 dark:text-gray-400 whitespace-pre-wrap mt-1'
                : 'text-xs text-gray-600 dark:text-gray-400 truncate mt-1',
            },
            contentText
              ? (isExpanded ? contentText : (hasLongContent ? contentText.substring(0, 100) + '...' : contentText))
              : '无内容'
          ),
          // 展开/收起按钮
          needsExpand
            ? h(
                'button',
                {
                  class: 'text-xs text-primary-500 hover:text-primary-600 mt-1 font-medium',
                  onClick: () => toggleContent(post_id),
                },
                isExpanded ? '−' : '+'
              )
            : null,
        ])
      },
    },
    {
      accessorKey: 'scores',
      header: '初筛评分',
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
          scoreText('垃圾', spam_score),
          scoreText('价值', value_score),
          scoreText('相关', relevance_score),
        ])
      },
    },
    {
      accessorKey: 'sentiment',
      header: '情感',
      cell: ({ row }) => {
        const sentiment = row.original.sentiment
        const color =
          sentiment === 1 ? 'success' : sentiment === -1 ? 'error' : 'neutral'
        const label =
          sentiment === 1 ? '正面' : sentiment === -1 ? '负面' : '中性'
        return sentiment != null
          ? h(UBadge, { size: 'xs', color, variant: 'subtle' }, () => label)
          : h('span', { class: 'text-gray-400 text-xs' }, '-')
      },
    },
    {
      accessorKey: 'engagement',
      header: '互动',
      cell: ({ row }) => {
        const { likes_count, comments_count, views_count } = row.original
        return h('div', { class: 'text-xs space-y-0.5 text-gray-600 dark:text-gray-400' }, [
          h('div', {}, `赞 ${formatNumber(likes_count)}`),
          h('div', {}, `评 ${formatNumber(comments_count)}`),
          h('div', {}, `览 ${formatNumber(views_count)}`),
        ])
      },
    },
    {
      accessorKey: 'published_at',
      header: '发布时间',
      cell: ({ row }) =>
        h('span', { class: 'text-xs text-gray-500' }, formatDateTime(row.original.published_at)),
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
        </div>
      </div>
    </template>

    <!-- 操作按钮区 + 进度 -->
    <div class="mb-4 flex justify-between items-start flex-wrap gap-3">
      <!-- 左侧：操作按钮 -->
      <div class="flex items-center gap-2 flex-wrap">
        <UButton
          size="sm"
          color="primary"
          :loading="actionLoading.screening"
          :disabled="hasRunningTask && screeningTask?.status === 'processing'"
          icon="i-heroicons-funnel"
          @click="handleScreening"
        >
          原文初筛
        </UButton>

        <UButton
          size="sm"
          color="success"
          :loading="actionLoading.deep"
          :disabled="hasRunningTask"
          icon="i-heroicons-document-text"
          @click="openDeepAnalysisDialog"
        >
          原文深度
        </UButton>

        <UButton
          size="sm"
          color="warning"
          :loading="actionLoading.comment"
          :disabled="hasRunningTask"
          icon="i-heroicons-chat-bubble-left-right"
          @click="handleComment"
        >
          评论深度
        </UButton>
      </div>

      <!-- 右侧：阈值显示 -->
      <div v-if="preview" class="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400">
        <UBadge color="neutral" variant="subtle" size="xs">
          垃圾{{ thresholds.spamMax }}
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
        :value="screeningTask.source_count ? ((screeningTask.analyzed_count || 0) / screeningTask.source_count) * 100 : 0"
        size="sm"
        :color="screeningTask.status === 'failed' ? 'error' : 'primary'"
      />
      <p v-if="screeningTask.status === 'failed'" class="text-xs text-red-600 mt-2">
        任务执行失败
      </p>
    </div>

    <!-- 分析结果表格 -->
    <UTable
      :data="rows"
      :columns="columns"
      :loading="tableLoading"
      class="w-full"
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
    :ui="{ width: 'sm:max-w-xl' }"
  >
    <template #body>
      <div class="space-y-4">
        <UFormField
          label="最大垃圾分"
          hint="0-10，分数越低表示内容越干净"
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
      <div class="flex gap-3 justify-end">
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
      </div>
    </template>
  </UModal>
  </div>
</template>
