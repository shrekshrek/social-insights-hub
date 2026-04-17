<script setup lang="ts">
import { h, computed, ref, type Component } from 'vue'
import type { TableColumn } from '@nuxt/ui'
import { UBadge, UButton, UProgress } from '#components'
import type { AnalysisJob, AnalysisType, AnalysisStatus } from '../../types'
import { PERMISSIONS } from '~/config/permissions'

definePageMeta({
  layout: 'default',
})

const toast = useToast()

const { currentUserId, hasPermission } = usePermissions()

const {
  getAnalysisJobs,
  cancelAnalysisJob,
  deleteAnalysisJob,
} = useJobsApi()

// 分页和筛选
const currentPage = ref(1)
const pageSize = ref(20)
const selectedType = ref<AnalysisType | 'all'>('all')
const selectedStatus = ref<AnalysisStatus | 'all'>('all')
const searchMonitorId = ref<number | undefined>()
const searchTaskId = ref<number | undefined>()
const refreshing = ref(false)

// 构建查询参数
const params = computed(() => ({
  page: currentPage.value,
  page_size: pageSize.value,
  analysis_type: selectedType.value === 'all' ? undefined : selectedType.value,
  status: selectedStatus.value === 'all' ? undefined : selectedStatus.value,
  // 处理空值和 NaN（暂时只支持社媒监测 ID 筛选）
  social_monitor_id: typeof searchMonitorId.value === 'number' && !Number.isNaN(searchMonitorId.value)
    ? searchMonitorId.value
    : undefined,
  social_task_id: typeof searchTaskId.value === 'number' && !Number.isNaN(searchTaskId.value)
    ? searchTaskId.value
    : undefined,
}))

// 获取分析任务列表
const {
  data: jobsData,
  pending: loading,
  refresh,
} = getAnalysisJobs(params)

const jobs = computed(() => jobsData.value?.items || [])
const total = computed(() => jobsData.value?.total || 0)

// 当前页统计
const pageStats = computed(() => {
  const items = jobs.value
  let totalTokens = 0
  let totalCost = 0
  let totalCalls = 0
  let totalTime = 0

  for (const job of items) {
    const summary = job.token_usage?.summary
    if (summary) {
      totalTokens += summary.total_tokens || 0
      totalCost += summary.total_cost_cny || 0
      totalCalls += summary.total_calls || 0
    }
    if (job.processing_time) {
      totalTime += job.processing_time
    }
  }

  return {
    totalTokens,
    totalCost,
    totalCalls,
    totalTime,
  }
})

// 刷新列表
const handleRefresh = async () => {
  refreshing.value = true
  await refresh()
  refreshing.value = false
}

// 分析类型选项
const typeOptions = [
  { label: '全部类型', value: 'all' },
  { label: '原文初筛', value: 'screening_posts' },
  { label: '原文深度', value: 'deep_posts' },
  { label: '评论深度', value: 'deep_comments' },
  { label: '实体归一化', value: 'entity_normalization' },
  { label: '观点归一化', value: 'opinion_normalization' },
  { label: '监测切片总分析', value: 'monitor_slice_summary' },
  { label: '策略·社媒探测审查', value: 'strategy_social_probe_review' },
  { label: '策略·新闻探测审查', value: 'strategy_news_probe_review' },
  { label: '策略·覆盖度验证', value: 'strategy_coverage_check' },
  { label: '策略·洞察 (Insight)', value: 'strategy_insight' },
  { label: '策略·品牌角色 (Brand Role)', value: 'strategy_brand_role' },
  { label: '策略·创意 (Big Idea)', value: 'strategy_big_idea' },
  { label: '策略·媒体议程图 (Agenda Map)', value: 'strategy_agenda_map' },
  { label: '策略·竞争格局 (Landscape)', value: 'strategy_landscape' },
  { label: '策略·战略简报 (Strategic Brief)', value: 'strategy_strategic_brief' },
  { label: '专题研究', value: 'research' },
]

// 状态选项
const statusOptions = [
  { label: '全部状态', value: 'all' },
  { label: '等待中', value: 'pending' },
  { label: '进行中', value: 'running' },
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
    screening_posts: '原文初筛',
    deep_posts: '原文深度',
    deep_comments: '评论深度',
    entity_normalization: '实体归一化',
    opinion_normalization: '观点归一化',
    monitor_slice_summary: '监测切片总分析',
    strategy_social_probe_review: '策略·社媒探测审查',
    strategy_news_probe_review: '策略·新闻探测审查',
    strategy_coverage_check: '策略·覆盖度验证',
    strategy_insight: '策略·洞察 (Insight)',
    strategy_brand_role: '策略·品牌角色 (Brand Role)',
    strategy_big_idea: '策略·创意 (Big Idea)',
    strategy_agenda_map: '策略·媒体议程图 (Agenda Map)',
    strategy_landscape: '策略·竞争格局 (Landscape)',
    strategy_strategic_brief: '策略·战略简报 (Strategic Brief)',
    research: '专题研究',
  }
  return labels[type] || type
}

const getStatusColor = (status: string) => {
  const colors: Record<string, string> = {
    pending: 'neutral',
    running: 'info',
    completed: 'success',
    failed: 'error',
  }
  return colors[status] || 'neutral'
}

const getStatusLabel = (status: string) => {
  const labels: Record<string, string> = {
    pending: '等待中',
    running: '进行中',
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
      footer: () => h('span', { class: 'text-xs font-semibold text-gray-600 dark:text-gray-400 whitespace-nowrap' }, '合计'),
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
          ['pending', 'running'].includes(job.status) && job.source_count > 0
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
      accessorKey: 'social_monitor_name',
      header: '项目',
      meta: { class: { th: 'w-[160px]', td: 'w-[160px] whitespace-normal' } },
      cell: ({ row }) => {
        const job = row.original

        // 专题研究：链接到 research-agent 详情页
        if (job.analysis_type === 'research') {
          const cfg = job.analysis_config as Record<string, unknown> | null
          const researchId = cfg?.research_task_id
          const researchTitle = cfg?.research_task_title as string | undefined
          if (!researchId) return h('span', { class: 'text-gray-400' }, '-')
          return h(Button, {
            variant: 'link',
            size: 'xs',
            class: 'p-0 font-normal text-left whitespace-normal leading-snug line-clamp-2',
            to: `/research-agent/${researchId}`,
          }, () => [
            h('span', { class: 'text-gray-400 font-mono mr-1' }, `#${researchId}`),
            researchTitle || '-',
          ])
        }

        // 社媒 / 新闻监测
        const monitorId = job.social_monitor_id || job.news_monitor_id
        const monitorName = job.social_monitor_name || job.news_monitor_name
        const isNews = !job.social_monitor_id && !!job.news_monitor_id
        const link = isNews
          ? `/news-media/monitors/${monitorId}`
          : `/social-media/monitors/${monitorId}`
        if (!monitorId) {
          return h('span', { class: 'text-gray-400' }, '-')
        }
        return h(Button, {
          variant: 'link',
          size: 'xs',
          class: 'p-0 font-normal text-left whitespace-normal leading-snug line-clamp-2',
          to: link,
        }, () => [
          h('span', { class: 'text-gray-400 font-mono mr-1' }, `#${monitorId}`),
          monitorName || '-',
        ])
      },
    },
    {
      accessorKey: 'social_task_name',
      header: '任务',
      meta: { class: { th: 'w-[180px]', td: 'w-[180px] whitespace-normal' } },
      cell: ({ row }) => {
        const job = row.original

        // 专题研究：项目列已显示研究任务，此列留空
        if (job.analysis_type === 'research') {
          return h('span', { class: 'text-gray-400' }, '-')
        }

        // 社媒 / 新闻任务
        const taskId = job.social_task_id || job.news_task_id
        const taskName = job.social_task_name || job.news_task_name
        const isNews = !job.social_task_id && !!job.news_task_id
        const taskLink = isNews
          ? `/news-media/tasks/${taskId}`
          : `/social-media/tasks/${taskId}`

        // 任务级：显示 ID + 任务名（允许换行）
        if (taskId) {
          return h(Button, {
            variant: 'link',
            size: 'xs',
            class: 'p-0 font-normal text-left whitespace-normal leading-snug line-clamp-2',
            to: taskLink,
          }, () => [
            h('span', { class: 'text-gray-400 font-mono mr-1' }, `#${taskId}`),
            taskName || '-',
          ])
        }

        // 项目级切片：显示切片名并跳转切片详情
        if (job.slice_id) {
          const label = job.slice_name || `切片 #${job.slice_id}`
          return h(Button, {
            variant: 'link',
            size: 'xs',
            class: 'p-0 font-normal',
            to: `/social-media/monitors/${job.social_monitor_id}/analysis?slice_id=${job.slice_id}`,
          }, () => label)
        }

        // 其他项目级：兜底
        return h('span', { class: 'text-gray-400' }, '-')
      },
    },
    {
      accessorKey: 'api_calls',
      header: () => h('span', { class: 'whitespace-nowrap' }, 'API 调用'),
      cell: ({ row }) => {
        const usage = row.original.token_usage?.summary
        const calls = usage?.total_calls || 0
        return h('span', { class: 'text-xs text-gray-600 dark:text-gray-400 whitespace-nowrap' }, `${calls} 次`)
      },
      footer: () => h('span', { class: 'text-xs font-semibold text-gray-700 dark:text-gray-300 whitespace-nowrap' },
        `${pageStats.value.totalCalls.toLocaleString()} 次`
      ),
    },
    {
      accessorKey: 'token_usage',
      header: () => h('span', { class: 'whitespace-nowrap' }, 'Token/成本'),
      cell: ({ row }) => {
        const usage = row.original.token_usage?.summary
        return h('div', { class: 'text-xs text-gray-600 dark:text-gray-400 whitespace-nowrap' }, [
          h('span', {}, formatTokens(usage?.total_tokens)),
          h('span', { class: 'text-primary-500 ml-1' }, formatCost(usage?.total_cost_cny)),
        ])
      },
      footer: () => h('div', { class: 'text-xs font-semibold whitespace-nowrap' }, [
        h('span', { class: 'text-gray-700 dark:text-gray-300' }, formatTokens(pageStats.value.totalTokens)),
        h('span', { class: 'text-primary-500 ml-1' }, formatCost(pageStats.value.totalCost)),
      ]),
    },
    {
      accessorKey: 'processing_time',
      header: '耗时',
      cell: ({ row }) => h('span', { class: 'text-sm text-gray-600 dark:text-gray-400 whitespace-nowrap' },
        formatDuration(row.original.processing_time)
      ),
      footer: () => h('span', { class: 'text-xs font-semibold text-gray-700 dark:text-gray-300 whitespace-nowrap' },
        formatDuration(pageStats.value.totalTime)
      ),
    },
    {
      accessorKey: 'created_at',
      header: () => h('span', { class: 'whitespace-nowrap' }, '创建时间'),
      cell: ({ row }) => h('span', { class: 'text-xs text-gray-600 dark:text-gray-400 whitespace-nowrap' },
        formatDateTime(row.original.created_at)
      ),
    },
    {
      accessorKey: 'actions',
      header: '操作',
      cell: ({ row }) => {
        const job = row.original
        const isRunning = ['pending', 'running'].includes(job.status)
        const canAct = job.user_id === currentUserId.value || hasPermission(PERMISSIONS.ANALYSIS_DELETE)

        return h('div', { class: 'flex items-center gap-2' }, [
          canAct
            ? (isRunning
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
                  }, () => '删除'))
            : null,
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
          AI 统计
        </h1>
        <p class="text-gray-600 dark:text-gray-400 mt-1">
          跨渠道 AI 分析任务的状态、进度与成本
        </p>
      </div>

      <UButton
        variant="ghost"
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
            调用记录
          </h2>

          <div class="flex items-center gap-3">
            <UInput
              v-model.number="searchMonitorId"
              type="number"
              placeholder="项目ID"
              class="w-24"
              :ui="{ base: 'text-sm' }"
            />

            <UInput
              v-model.number="searchTaskId"
              type="number"
              placeholder="任务ID"
              class="w-24"
              :ui="{ base: 'text-sm' }"
            />

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
              加载记录中...
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
              show-first
              show-last
              show-edges
            />
          </div>
        </ClientOnly>
      </template>
    </UCard>
  </div>
</template>
