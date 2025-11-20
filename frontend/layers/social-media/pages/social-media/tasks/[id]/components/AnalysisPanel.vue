<script setup lang="ts">
import type { TaskAnalysisResult } from '../../../../../analysis/types'
import { formatDistanceToNow } from 'date-fns'
import { zhCN } from 'date-fns/locale'

const props = defineProps<{
  taskId: number
}>()

const {
  getTaskAnalysisResults,
  runPostScreening,
  runPostDeepAnalysis,
  runCommentDeepAnalysis,
  cancelAnalysis,
  deleteAnalysisResult,
} = useAnalysis()

// 获取分析历史
const {
  data: analysisData,
  pending: loading,
  refresh
} = await getTaskAnalysisResults(props.taskId)

const analysisHistory = computed(() => analysisData.value?.items || [])

// 轮询处理中的任务
const processingTasks = computed(() =>
  analysisHistory.value.filter(item =>
    ['pending', 'processing'].includes(item.status)
  )
)

// 使用 Vue 原生 API 实现轮询
let pollingTimer: ReturnType<typeof setInterval> | null = null

const startPolling = () => {
  if (pollingTimer) return
  pollingTimer = setInterval(async () => {
    if (processingTasks.value.length > 0) {
      await refresh()
    }
  }, 3000)
}

const stopPolling = () => {
  if (pollingTimer) {
    clearInterval(pollingTimer)
    pollingTimer = null
  }
}

// 监控任务状态变化
watch(processingTasks, (newTasks) => {
  if (newTasks.length > 0) {
    startPolling()
  } else {
    stopPolling()
  }
}, { immediate: true })

// 组件卸载时清理定时器
onUnmounted(() => {
  stopPolling()
})

// 快速分析操作
const isAnalyzing = ref(false)

const quickAnalysis = async (type: 'screening_posts' | 'deep_posts' | 'deep_comments') => {
  const { $confirm } = useNuxtApp()

  const typeLabels = {
    'screening_posts': '原文初筛',
    'deep_posts': '原文深度分析',
    'deep_comments': '评论深度分析'
  }

  const typeDescriptions = {
    'screening_posts': '将评估所有帖子原文的垃圾分、价值分和相关度',
    'deep_posts': '将提取所有帖子原文的实体、观点并生成摘要（消耗较多 Token）',
    'deep_comments': '将分析所有帖子的评论内容（消耗较多 Token）'
  }

  if (!await $confirm({
    title: `确认启动${typeLabels[type]}？`,
    message: typeDescriptions[type],
    type: 'info'
  })) {
    return
  }

  try {
    isAnalyzing.value = true

    if (type === 'screening_posts') {
      await runPostScreening({
        task_id: props.taskId,
        analyze_all: true
      })
    } else if (type === 'deep_posts') {
      await runPostDeepAnalysis({
        task_id: props.taskId
      })
    } else if (type === 'deep_comments') {
      await runCommentDeepAnalysis({
        task_id: props.taskId
      })
    }

    await refresh()
  } catch (error) {
    console.error('Failed to start analysis:', error)
  } finally {
    isAnalyzing.value = false
  }
}

// 辅助函数
const getAnalysisTypeLabel = (type: string) => {
  const map: Record<string, string> = {
    'screening_posts': '原文初筛',
    'deep_posts': '原文深度分析',
    'deep_comments': '评论深度分析'
  }
  return map[type] || type
}

const getAnalysisTypeIcon = (type: string) => {
  const map: Record<string, string> = {
    'screening_posts': 'i-heroicons-funnel',
    'deep_posts': 'i-heroicons-document-text',
    'deep_comments': 'i-heroicons-chat-bubble-left-right'
  }
  return map[type] || 'i-heroicons-sparkles'
}

const getStatusColor = (status: string) => {
  const map: Record<string, string> = {
    'pending': 'gray',
    'processing': 'blue',
    'completed': 'green',
    'failed': 'red'
  }
  return map[status] || 'gray'
}

const getStatusLabel = (status: string) => {
  const map: Record<string, string> = {
    'pending': '排队中',
    'processing': '处理中',
    'completed': '已完成',
    'failed': '失败'
  }
  return map[status] || status
}

const handleDelete = async (id: number, status: string) => {
  const { $confirm } = useNuxtApp()

  const isRunning = ['pending', 'processing'].includes(status)
  const message = isRunning
    ? '该任务正在运行中，删除将同时取消任务执行。确定继续吗？'
    : '删除分析记录不会影响原始数据，确定继续吗？'

  if (await $confirm({
    title: '确认删除',
    message,
    type: 'warning'
  })) {
    try {
      // 如果任务正在运行，先取消
      if (isRunning) {
        await cancelAnalysis(id)
      }
      // 删除记录
      await deleteAnalysisResult(id)
      await refresh()
    } catch (error) {
      console.error('Failed to delete analysis result:', error)
    }
  }
}

// 动态加载组件
const AnalysisProgress = resolveComponent('AnalysisProgress')
const TokenUsageCard = resolveComponent('TokenUsageCard')
</script>

<template>
  <div class="space-y-6">
    <!-- 快速分析操作区 -->
    <UCard>
      <template #header>
        <div class="flex items-center gap-2">
          <UIcon name="i-heroicons-sparkles" class="w-5 h-5 text-primary" />
          <h3 class="text-lg font-medium">AI 分析</h3>
        </div>
      </template>

      <div class="space-y-4">
        <p class="text-sm text-gray-600 dark:text-gray-400">
          点击按钮快速分析任务下的所有数据
        </p>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
          <!-- 原文初筛 -->
          <UButton
            block
            size="lg"
            color="primary"
            variant="soft"
            :loading="isAnalyzing"
            :disabled="processingTasks.length > 0"
            @click="quickAnalysis('screening_posts')"
          >
            <template #leading>
              <UIcon name="i-heroicons-funnel" />
            </template>
            原文初筛
          </UButton>

          <!-- 原文深度分析 -->
          <UButton
            block
            size="lg"
            color="primary"
            variant="soft"
            :loading="isAnalyzing"
            :disabled="processingTasks.length > 0"
            @click="quickAnalysis('deep_posts')"
          >
            <template #leading>
              <UIcon name="i-heroicons-document-text" />
            </template>
            原文深度分析
          </UButton>

          <!-- 评论深度分析 -->
          <UButton
            block
            size="lg"
            color="primary"
            variant="soft"
            :loading="isAnalyzing"
            :disabled="processingTasks.length > 0"
            @click="quickAnalysis('deep_comments')"
          >
            <template #leading>
              <UIcon name="i-heroicons-chat-bubble-left-right" />
            </template>
            评论深度分析
          </UButton>
        </div>

        <div v-if="processingTasks.length > 0" class="bg-blue-50 dark:bg-blue-900/20 p-3 rounded-lg text-sm text-blue-600 dark:text-blue-300">
          <UIcon name="i-heroicons-information-circle" class="inline-block align-text-bottom mr-1" />
          当前有 {{ processingTasks.length }} 个任务正在处理中，请等待完成后再启动新任务
        </div>
      </div>
    </UCard>

    <!-- 分析任务记录 -->
    <div class="space-y-4">
      <h3 class="text-lg font-medium text-gray-900 dark:text-white">分析历史</h3>

      <div class="space-y-3">
        <div
          v-for="item in analysisHistory"
          :key="item.id"
          class="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 hover:shadow-md transition-shadow"
        >
          <!-- 任务头部：类型、状态、操作 -->
          <div class="flex items-center justify-between mb-3">
            <div class="flex items-center gap-2">
              <UIcon :name="getAnalysisTypeIcon(item.analysis_type)" class="w-4 h-4 text-gray-500" />
              <span class="font-medium text-sm">{{ getAnalysisTypeLabel(item.analysis_type) }}</span>
              <UBadge :color="getStatusColor(item.status)" variant="subtle" size="xs">
                {{ getStatusLabel(item.status) }}
              </UBadge>
            </div>
            <div class="flex items-center gap-2">
              <span class="text-xs text-gray-500">
                {{ formatDistanceToNow(new Date(item.created_at), { addSuffix: true, locale: zhCN }) }}
              </span>
              <UButton
                size="xs"
                variant="ghost"
                icon="i-heroicons-trash"
                color="red"
                @click="handleDelete(item.id, item.status)"
              />
            </div>
          </div>

          <!-- 进度条（处理中状态） -->
          <div v-if="['pending', 'processing'].includes(item.status)" class="space-y-2">
            <div class="flex justify-between text-sm">
              <span class="text-gray-600 dark:text-gray-400">
                {{ item.status === 'pending' ? '队列等待中...' : '正在分析...' }}
              </span>
              <span class="font-medium text-primary">
                {{ item.analyzed_count || 0 }} / {{ item.source_count || 0 }}
              </span>
            </div>
            <UProgress
              :value="item.source_count ? ((item.analyzed_count || 0) / item.source_count * 100) : 0"
              color="primary"
              size="sm"
            />
          </div>

          <!-- 完成状态 -->
          <div v-else-if="item.status === 'completed'" class="space-y-2">
            <!-- 统计信息 -->
            <div class="grid grid-cols-3 gap-4 text-sm">
              <div>
                <div class="text-gray-500 text-xs mb-1">分析数量</div>
                <div class="font-semibold">{{ item.analyzed_count }} / {{ item.source_count }}</div>
              </div>
              <div v-if="item.token_usage">
                <div class="text-gray-500 text-xs mb-1">Token 使用</div>
                <div class="font-semibold">{{ item.token_usage.summary.total_tokens.toLocaleString() }}</div>
              </div>
              <div v-if="item.token_usage">
                <div class="text-gray-500 text-xs mb-1">成本</div>
                <div class="font-semibold text-green-600">¥{{ item.token_usage.summary.cost_cny.toFixed(4) }}</div>
              </div>
            </div>

            <!-- 成功率指示 -->
            <div v-if="item.analyzed_count && item.source_count">
              <UProgress
                :value="(item.analyzed_count / item.source_count) * 100"
                :color="(item.analyzed_count / item.source_count) >= 0.95 ? 'green' : 'yellow'"
                size="sm"
              />
            </div>
          </div>

          <!-- 失败状态 -->
          <div v-else-if="item.status === 'failed'" class="space-y-1">
            <div class="text-sm text-red-600 dark:text-red-400">
              <UIcon name="i-heroicons-exclamation-triangle" class="inline w-4 h-4 mr-1" />
              任务失败
            </div>
            <div class="text-xs text-gray-500 bg-red-50 dark:bg-red-900/20 p-2 rounded">
              {{ item.error_message || '未知错误' }}
            </div>
          </div>
        </div>

        <!-- 空状态 -->
        <div v-if="!loading && analysisHistory.length === 0" class="text-center py-12 text-gray-500">
          <UIcon name="i-heroicons-inbox" class="w-12 h-12 mx-auto mb-3 opacity-50" />
          <p>暂无分析记录</p>
          <p class="text-sm mt-1">点击上方按钮开始分析</p>
        </div>
      </div>
    </div>
  </div>
</template>
