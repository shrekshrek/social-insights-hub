<script setup lang="ts">
import { h, computed, reactive, ref, watch, onMounted, onUnmounted } from 'vue'
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
  page_size: 50, // 显示最近50条
}))

const {
  data: analysisHistory,
  refresh: refreshHistory,
} = await getAnalysisJobs(analysisJobsParams)

/** 统一的帖子分析列表（初筛 + 原文深度 + 评论深度） */
const page = ref(1)
const pageSize = ref(20)
const filterAnalyzed = ref(false) // 显示全部帖子，未分析的也能看到并用于筛选

// 搜索状态
const searchQuery = ref('')
const searchId = ref<number | null>(null)
const searchActive = computed(() => !!searchQuery.value || searchId.value !== null)

const {
  data: postAnalysisData,
  pending: tableLoading,
  refresh: refreshPostAnalysis,
} = await getTaskPostAnalyses(props.taskId, {
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

/** 阈值筛选，用于"根据初筛结果筛选再深度分析" */
const thresholds = reactive({
  spamMax: 5, // 0-10，越低越干净
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

// 初筛任务（用于显示进度）- 只显示进行中的任务
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

// 自动轮询机制：当有任务在运行时，每3秒刷新一次
let pollTimer: ReturnType<typeof setInterval> | null = null

const startPolling = () => {
  if (pollTimer) return // 已经在轮询中
  pollTimer = setInterval(() => {
    refreshHistory()
  }, 3000) // 每3秒刷新一次
}

const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// 监听是否有任务在运行，自动启动/停止轮询
watch(hasRunningTask, (isRunning) => {
  if (isRunning) {
    startPolling()
  } else {
    stopPolling()
    // 任务完成后，最后刷新一次所有数据
    refreshAll()
  }
})

// 组件挂载时检查是否需要开始轮询
onMounted(() => {
  if (hasRunningTask.value) {
    startPolling()
  }
})

// 组件卸载时停止轮询
onUnmounted(() => {
  stopPolling()
})

// 搜索处理函数
const handleSearch = () => {
  page.value = 1 // 重置到第一页
  refreshPostAnalysis()
}

const handleClearSearch = () => {
  searchQuery.value = ''
  searchId.value = null
  page.value = 1
  refreshPostAnalysis()
}

// 对话框预览加载（防抖500ms）
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

// 防抖预览加载
const debouncedLoadDialogPreview = () => {
  if (dialogPreviewTimer) {
    clearTimeout(dialogPreviewTimer)
  }
  dialogPreviewTimer = setTimeout(() => {
    loadDialogPreview()
  }, 500)
}

// 监听对话框阈值变化，触发防抖预览
watch(
  () => [dialogThresholds.spamMax, dialogThresholds.valueMin, dialogThresholds.relevanceMin],
  () => {
    if (deepDialogOpen.value) {
      debouncedLoadDialogPreview()
    }
  }
)

// 打开深度分析对话框
const openDeepAnalysisDialog = () => {
  // 复制当前阈值到对话框
  dialogThresholds.spamMax = thresholds.spamMax
  dialogThresholds.valueMin = thresholds.valueMin
  dialogThresholds.relevanceMin = thresholds.relevanceMin

  // 加载预览
  deepDialogOpen.value = true
  loadDialogPreview()
}

// 确认深度分析
const handleConfirmDeepAnalysis = async () => {
  // 保存对话框阈值到全局
  thresholds.spamMax = dialogThresholds.spamMax
  thresholds.valueMin = dialogThresholds.valueMin
  thresholds.relevanceMin = dialogThresholds.relevanceMin

  // 关闭对话框
  deepDialogOpen.value = false

  // 执行深度分析
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

/** 统一表格列定义 - 遵循项目规范 */
const columns = computed<TableColumn<PostAnalysisWithPostInfo>[]>(() => {
  if (!import.meta.client) return []

  const UBadge = resolveComponent('UBadge')

  return [
    {
      accessorKey: 'post_id',
      header: 'ID',
      cell: ({ row }) => h('span', { class: 'text-xs text-gray-500' }, row.original.post_id),
    },
    {
      accessorKey: 'content',
      header: '内容',
      cell: ({ row }) => {
        const { title, content } = row.original
        return h('div', { class: 'space-y-1 max-w-xl' }, [
          title
            ? h('p', { class: 'font-medium text-sm truncate' }, title)
            : null,
          h(
            'p',
            { class: 'text-xs text-gray-600 dark:text-gray-400 line-clamp-2' },
            content || '无内容',
          ),
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

        return h('div', { class: 'space-y-1' }, [
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
          : h('span', { class: 'text-gray-400' }, '-')
      },
    },
    {
      accessorKey: 'engagement',
      header: '互动',
      cell: ({ row }) => {
        const { likes_count, comments_count, views_count } = row.original
        return h('div', { class: 'text-xs space-y-0.5 text-gray-600 dark:text-gray-400' }, [
          h('div', {}, `👍 ${formatNumber(likes_count)}`),
          h('div', {}, `💬 ${formatNumber(comments_count)}`),
          h('div', {}, `👁 ${formatNumber(views_count)}`),
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
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <UIcon name="i-heroicons-chart-bar" class="w-5 h-5 text-primary" />
            <span class="text-lg font-semibold">数据分析与处理</span>
          </div>
        </div>
      </template>

      <!-- 操作按钮区 + 阈值显示 -->
      <div class="mb-3 flex justify-between items-start flex-wrap gap-3">
        <!-- 左侧：操作按钮 + 初筛进度 -->
        <div class="flex-1 min-w-[300px]">
          <div class="flex items-center gap-2 flex-wrap mb-2">
            <UButton
              size="sm"
              color="primary"
              :loading="actionLoading.screening"
              :disabled="hasRunningTask && screeningTask?.status === 'processing'"
              @click="handleScreening"
            >
              <UIcon name="i-heroicons-funnel" class="mr-1" />
              原文初筛
            </UButton>

            <UButton
              size="sm"
              color="green"
              :loading="actionLoading.deep"
              :disabled="hasRunningTask"
              @click="openDeepAnalysisDialog"
            >
              <UIcon name="i-heroicons-document-text" class="mr-1" />
              原文深度分析
            </UButton>

            <UButton
              size="sm"
              color="orange"
              :loading="actionLoading.comment"
              :disabled="hasRunningTask"
              @click="handleComment"
            >
              <UIcon name="i-heroicons-chat-bubble-left-right" class="mr-1" />
              评论深度分析
            </UButton>
          </div>

          <!-- 初筛任务进度（集成在按钮下方） -->
          <div
            v-if="screeningTask"
            class="p-2 border rounded bg-gray-50 dark:bg-gray-800 text-sm"
          >
            <div class="flex items-center justify-between mb-1">
              <div class="flex items-center gap-2">
                <span class="text-xs font-medium">原文初筛任务</span>
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
              :animation="false"
            />
            <p v-if="screeningTask.status === 'failed'" class="text-xs text-red-600 mt-1">
              任务执行失败
            </p>
          </div>
        </div>

        <!-- 右侧：当前阈值设置 -->
        <div v-if="preview" class="text-sm text-gray-600 dark:text-gray-400 flex items-center gap-2 flex-wrap">
          <span class="font-medium">当前阈值设置：</span>
          <UBadge color="gray" variant="subtle" size="sm">
            垃圾分 ≤ {{ thresholds.spamMax }}
          </UBadge>
          <UBadge color="blue" variant="subtle" size="sm">
            价值分 ≥ {{ thresholds.valueMin }}
          </UBadge>
          <UBadge color="green" variant="subtle" size="sm">
            相关度 ≥ {{ thresholds.relevanceMin }}
          </UBadge>
          <span class="ml-2 text-blue-600 dark:text-blue-400 font-semibold">
            (符合条件: {{ matchedCount }}/{{ totalPostsCount }})
          </span>
        </div>
      </div>

      <!-- 搜索功能区 -->
      <div class="mb-3 p-3 bg-gray-50 dark:bg-gray-800 rounded">
        <div class="grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
          <div class="md:col-span-4">
            <label class="block text-xs text-gray-600 dark:text-gray-400 mb-1">关键词搜索</label>
            <UInput
              v-model="searchQuery"
              placeholder="输入关键词搜索帖子标题或内容"
              size="sm"
              @keyup.enter="handleSearch"
            />
          </div>

          <div class="md:col-span-3">
            <label class="block text-xs text-gray-600 dark:text-gray-400 mb-1">ID 搜索</label>
            <UInput
              v-model.number="searchId"
              type="number"
              placeholder="输入帖子分析ID"
              size="sm"
              @keyup.enter="handleSearch"
            />
          </div>

          <div class="md:col-span-5 flex items-center gap-2">
            <UButton
              size="sm"
              color="primary"
              icon="i-heroicons-magnifying-glass"
              @click="handleSearch"
            >
              搜索
            </UButton>
            <UButton
              size="sm"
              variant="outline"
              @click="handleClearSearch"
            >
              重置
            </UButton>
            <span v-if="searchActive" class="text-xs text-gray-500 ml-1">
              已应用搜索条件
            </span>
          </div>
        </div>

        <!-- 搜索结果提示 -->
        <div v-if="searchActive" class="mt-2 text-xs text-blue-600 dark:text-blue-400">
          找到 <strong>{{ total }}</strong> 条结果
          <span v-if="searchQuery"> - 关键词: "{{ searchQuery }}"</span>
          <span v-if="searchId"> - ID: {{ searchId }}</span>
        </div>
      </div>

      <!-- 分析结果表格 -->
      <div class="mb-3">
        <div class="flex items-center justify-between mb-2">
          <span class="text-sm font-medium">分析结果</span>
          <UCheckbox v-model="filterAnalyzed" label="仅显示已初筛的帖子" size="sm" />
        </div>

        <div class="overflow-x-auto">
          <UTable
            :data="rows"
            :columns="columns"
            :loading="tableLoading"
            class="min-w-full"
          >
            <template #empty-state>
              <div class="text-center py-10 text-gray-500">
                <UIcon name="i-heroicons-inbox" class="w-10 h-10 mx-auto mb-2 opacity-60" />
                <p class="text-sm">暂无数据，请先执行初筛或深度分析</p>
              </div>
            </template>
          </UTable>
        </div>

        <div class="flex items-center justify-between mt-3">
          <div class="text-sm text-gray-500">
            共 {{ total }} 条数据
          </div>
          <UPagination
            v-model:page="page"
            :total="total"
            :items-per-page="pageSize"
            :sibling-count="2"
            @update:page="refreshPostAnalysis"
          />
        </div>
      </div>
    </UCard>

    <!-- 深度分析对话框 -->
    <UModal
      :open="deepDialogOpen"
      :close="{ onClick: () => deepDialogOpen = false }"
      title="设置原文深度分析阈值"
      :ui="{ width: 'sm:max-w-2xl', footer: 'justify-end' }"
    >
      <template #body>
        <div class="space-y-4">
          <UFormField
            label="最大垃圾分≤"
            hint="0-10，分数越低表示内容越干净"
          >
            <UInput
              v-model.number="dialogThresholds.spamMax"
              type="number"
              :min="0"
              :max="10"
              step="0.5"
              placeholder="0-10"
            />
          </UFormField>

          <UFormField
            label="最小价值分≥"
            hint="0-10，分数越高表示内容价值越大"
          >
            <UInput
              v-model.number="dialogThresholds.valueMin"
              type="number"
              :min="0"
              :max="10"
              step="0.5"
              placeholder="0-10"
            />
          </UFormField>

          <UFormField
            label="最小相关分≥"
            hint="0-10，分数越高表示与项目关键词相关度越高"
          >
            <UInput
              v-model.number="dialogThresholds.relevanceMin"
              type="number"
              :min="0"
              :max="10"
              step="0.5"
              placeholder="0-10"
            />
          </UFormField>

          <!-- 实时预览 -->
          <div v-if="dialogPreviewLoading" class="text-center text-gray-500 mt-4 py-3">
            <UIcon name="i-heroicons-arrow-path" class="w-5 h-5 animate-spin mx-auto mb-2" />
            正在加载预览数据...
          </div>

          <div v-else-if="dialogPreview" class="mt-4 p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
            <p class="text-sm text-gray-700 dark:text-gray-300 mb-2">
              根据当前阈值，在当前任务的 <strong>全部</strong> 原文中:
            </p>
            <p class="text-sm text-gray-700 dark:text-gray-300">
              预计有 <strong class="text-lg text-primary">{{ dialogPreview.matched_count }}</strong> /
              {{ dialogPreview.total_posts }} 条符合深度分析条件
              <span class="ml-2 text-gray-500">
                ({{ dialogPreview.total_posts > 0 ? ((dialogPreview.matched_count / dialogPreview.total_posts) * 100).toFixed(1) : '0.0' }}%)
              </span>
            </p>
          </div>
        </div>
      </template>

      <template #footer>
        <div class="flex gap-3">
          <UButton
            label="取消"
            color="neutral"
            variant="outline"
            @click="deepDialogOpen = false"
          />
          <UButton
            :label="`确定并发起分析 (${dialogPreview?.matched_count || 0} 条)`"
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
