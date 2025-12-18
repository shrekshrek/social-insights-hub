<script setup lang="ts">
import { h, computed, ref, type Component } from 'vue'
import type { TableColumn } from '@nuxt/ui'
import { UBadge, UButton, UProgress } from '#components'
import type { AnalysisJob, AnalysisType, AnalysisStatus } from '../../../analysis/types'

definePageMeta({
  layout: 'default',
})

const toast = useToast()

const {
  getAnalysisJobs,
  cancelAnalysisJob,
  deleteAnalysisJob,
} = useAnalysis()

// 分页和筛选
const currentPage = ref(1)
const pageSize = ref(20)
const selectedType = ref<AnalysisType | undefined>()
const selectedStatus = ref<AnalysisStatus | undefined>()
const refreshing = ref(false)

// 构建查询参数
const params = computed(() => ({
  page: currentPage.value,
  page_size: pageSize.value,
  analysis_type: selectedType.value,
  status: selectedStatus.value,
}))

// 获取分析任务列表
const {
  data: jobsData,
  pending: loading,
  refresh,
} = getAnalysisJobs(params)

const jobs = computed(() => jobsData.value?.items || [])
const total = computed(() => jobsData.value?.total || 0)

// 刷新列表
const handleRefresh = async () => {
  refreshing.value = true
  await refresh()
  refreshing.value = false
}

// 分析类型选项
const typeOptions = [
  { label: '全部类型', value: undefined },
  { label: '帖子初筛', value: 'screening_posts' },
  { label: '帖子深度', value: 'deep_posts' },
  { label: '评论深度', value: 'deep_comments' },
  { label: '实体归一化', value: 'entity_normalization' },
  { label: '观点归一化', value: 'opinion_normalization' },
  { label: '项目快照总分析', value: 'project_snapshot_summary' },
  { label: '主题聚类', value: 'topic_clustering' },
  { label: '竞品分析', value: 'competitive' },
]

// 状态选项
const statusOptions = [
  { label: '全部状态', value: undefined },
  { label: '等待中', value: 'pending' },
  { label: '进行中', value: 'processing' },
  { label: '已完成', value: 'completed' },
  { label: '失败', value: 'failed' },
]

// 格式化函数
const formatDateTime = (value?: string | null) => {
  if (!value) return '-'
  const date = new Date(value)
  return isNaN(date.getTime()) ? '-' : date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const formatCost = (value?: number | null) => {
  if (value == null) return '-'
  return `¥${value.toFixed(4)}`
}

const formatTokens = (value?: number | null) => {
  if (value == null) return '-'
  return value.toLocaleString()
}

const formatDuration = (seconds?: number | null) => {
  if (seconds == null) return '-'
  if (seconds < 60) return `${seconds}秒`
  const minutes = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${minutes}分${secs}秒`
}

const getAnalysisTypeLabel = (type: string) => {
  const labels: Record<string, string> = {
    screening_posts: '帖子初筛',
    deep_posts: '帖子深度',
    deep_comments: '评论深度',
    entity_normalization: '实体归一化',
    opinion_normalization: '观点归一化',
    project_snapshot_summary: '项目快照总分析',
    topic_clustering: '主题聚类',
    competitive: '竞品分析',
  }
  return labels[type] || type
}

const getStatusColor = (status: string) => {
  const colors: Record<string, string> = {
    pending: 'warning',
    processing: 'info',
    completed: 'success',
    failed: 'error',
  }
  return colors[status] || 'neutral'
}

const getStatusLabel = (status: string) => {
  const labels: Record<string, string> = {
    pending: '等待中',
    processing: '进行中',
    completed: '已完成',
    failed: '失败',
  }
  return labels[status] || status
}

// 操作处理
const handleCancel = async (job: AnalysisJob) => {
  try {
    await cancelAnalysisJob(job.id)
    await handleRefresh()
    toast.add({ title: '已取消', description: '分析任务已取消', color: 'success' })
  } catch (error) {
    toast.add({ title: '取消失败', description: String(error), color: 'error' })
  }
}

const handleDelete = async (job: AnalysisJob) => {
  const { $confirm } = useNuxtApp()
  const confirmed = await $confirm({
    title: '删除分析任务',
    message: `确定要删除此分析任务吗？此操作不可恢复。`,
    confirmText: '删除',
    cancelText: '取消',
    type: 'error',
  })

  if (!confirmed) return

  try {
    await deleteAnalysisJob(job.id)
    await handleRefresh()
    toast.add({ title: '已删除', description: '分析任务已删除', color: 'success' })
  } catch (error) {
    toast.add({ title: '删除失败', description: String(error), color: 'error' })
  }
}

// 表格列定义
const columns = computed<TableColumn<AnalysisJob>[]>(() => {
  const Badge = UBadge as Component
  const Button = UButton as Component
  const Progress = UProgress as Component

  return [
    {
      accessorKey: 'id',
      header: 'ID',
      cell: ({ row }) => h('span', { class: 'text-xs text-gray-500 font-mono' }, row.original.id),
    },
    {
      accessorKey: 'analysis_type',
      header: '分析类型',
      cell: ({ row }) => h(Badge, {
        color: 'neutral',
        variant: 'subtle',
        size: 'xs',
      }, () => getAnalysisTypeLabel(row.original.analysis_type)),
    },
    {
      accessorKey: 'status',
      header: '状态',
      cell: ({ row }) => {
        const job = row.original
        return h('div', { class: 'space-y-1' }, [
          h(Badge, {
            color: getStatusColor(job.status),
            variant: 'solid',
            size: 'xs',
          }, () => getStatusLabel(job.status)),
          ['pending', 'processing'].includes(job.status) && job.source_count > 0
            ? h(Progress, {
                modelValue: job.source_count ? (job.analyzed_count / job.source_count) * 100 : 0,
                max: 100,
                size: 'xs',
                class: 'mt-1 w-20',
              })
            : null,
        ])
      },
    },
    {
      accessorKey: 'progress',
      header: '进度',
      cell: ({ row }) => {
        const job = row.original
        return h('span', { class: 'text-sm text-gray-600 dark:text-gray-400' },
          `${job.analyzed_count || 0} / ${job.source_count || 0}`
        )
      },
    },
    {
      accessorKey: 'project_name',
      header: '项目',
      cell: ({ row }) => {
        if (!row.original.project_name) {
          return h('span', { class: 'text-gray-400' }, '-')
        }
        return h(Button, {
          variant: 'link',
          size: 'xs',
          class: 'p-0 font-normal',
          to: `/social-media/projects/${row.original.project_id}`,
        }, () => row.original.project_name)
      },
    },
    {
      accessorKey: 'task_name',
      header: '任务',
      cell: ({ row }) => {
        // 任务级：跳转任务详情
        if (row.original.task_name) {
          return h(Button, {
            variant: 'link',
            size: 'xs',
            class: 'p-0 font-normal',
            to: `/social-media/tasks/${row.original.task_id}`,
          }, () => row.original.task_name)
        }

        // 项目级快照：显示快照名并跳转快照详情
        if (row.original.snapshot_id) {
          const label = row.original.snapshot_name || `快照 #${row.original.snapshot_id}`
          return h(Button, {
            variant: 'link',
            size: 'xs',
            class: 'p-0 font-normal',
            to: `/social-media/projects/${row.original.project_id}/analysis?snapshot_id=${row.original.snapshot_id}`,
          }, () => label)
        }

        // 其他项目级：兜底
        return h('span', { class: 'text-gray-400' }, '项目级')
      },
    },
    {
      accessorKey: 'api_calls',
      header: 'API 调用',
      cell: ({ row }) => {
        const usage = row.original.token_usage?.summary
        const calls = usage?.total_calls || 0
        return h('div', { class: 'text-xs text-gray-600 dark:text-gray-400' }, [
          h('div', {}, `${calls} 次`),
          h('div', { class: 'text-gray-400' }, 'deepseek-chat'),
        ])
      },
    },
    {
      accessorKey: 'token_usage',
      header: 'Token / 成本',
      cell: ({ row }) => {
        const usage = row.original.token_usage?.summary
        return h('div', { class: 'text-xs text-gray-600 dark:text-gray-400' }, [
          h('div', {}, formatTokens(usage?.total_tokens)),
          h('div', { class: 'text-primary-500' }, formatCost(usage?.total_cost_cny)),
        ])
      },
    },
    {
      accessorKey: 'processing_time',
      header: '耗时',
      cell: ({ row }) => h('span', { class: 'text-sm text-gray-600 dark:text-gray-400' },
        formatDuration(row.original.processing_time)
      ),
    },
    {
      accessorKey: 'created_at',
      header: '创建时间',
      cell: ({ row }) => h('span', { class: 'text-sm text-gray-600 dark:text-gray-400' },
        formatDateTime(row.original.created_at)
      ),
    },
    {
      accessorKey: 'actions',
      header: '操作',
      cell: ({ row }) => {
        const job = row.original
        const isRunning = ['pending', 'processing'].includes(job.status)

        return h('div', { class: 'flex items-center gap-2' }, [
          isRunning
            ? h(Button, {
                size: 'xs',
                color: 'warning',
                variant: 'ghost',
                icon: 'i-heroicons-stop',
                onClick: () => handleCancel(job),
              }, () => '取消')
            : h(Button, {
                size: 'xs',
                color: 'error',
                variant: 'ghost',
                icon: 'i-heroicons-trash',
                onClick: () => handleDelete(job),
              }, () => '删除'),
        ])
      },
    },
  ]
})
</script>

<template>
  <div class="space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
          AI 分析
        </h1>
        <p class="text-gray-600 dark:text-gray-400 mt-1">
          查看所有AI分析任务的执行记录
        </p>
      </div>

      <UButton
        variant="outline"
        icon="i-heroicons-arrow-path"
        :loading="refreshing"
        @click="handleRefresh"
      >
        刷新
      </UButton>
    </div>

    <!-- 分析任务列表卡片 -->
    <UCard>
      <template #header>
        <div class="flex items-center justify-between gap-4">
          <h2 class="text-lg font-semibold">
            分析记录
          </h2>

          <div class="flex items-center gap-3">
            <USelect
              v-model="selectedType"
              :items="typeOptions"
              value-key="value"
              placeholder="类型"
              class="w-32"
            />

            <USelect
              v-model="selectedStatus"
              :items="statusOptions"
              value-key="value"
              placeholder="状态"
              class="w-32"
            />
          </div>
        </div>
      </template>

      <!-- 任务表格 -->
      <ClientOnly>
        <template #fallback>
          <div class="text-center py-8">
            <p class="text-gray-600 dark:text-gray-400">
              加载分析记录中...
            </p>
          </div>
        </template>

        <UTable
          :data="jobs"
          :columns="columns"
          :loading="loading"
          class="w-full"
        >
          <template #empty-state>
            <div class="text-center py-10 text-gray-500">
              <UIcon name="i-heroicons-inbox" class="w-10 h-10 mx-auto mb-2 opacity-60" />
              <p class="text-sm">暂无分析任务记录</p>
            </div>
          </template>
        </UTable>
      </ClientOnly>

      <!-- 分页 -->
      <template #footer>
        <ClientOnly>
          <div class="flex justify-between items-center">
            <div class="text-sm text-gray-500 dark:text-gray-400">
              显示 {{ (currentPage - 1) * pageSize + 1 }} 到
              {{ Math.min(currentPage * pageSize, total) }} 共
              {{ total }} 条记录
            </div>
            <UPagination
              v-model:page="currentPage"
              :total="total"
              :items-per-page="pageSize"
              :sibling-count="2"
            />
          </div>
        </ClientOnly>
      </template>
    </UCard>
  </div>
</template>
