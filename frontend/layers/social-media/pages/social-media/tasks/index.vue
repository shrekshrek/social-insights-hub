<script setup lang="ts">
import { h, ref, computed, type Component } from 'vue'
import type { TableColumn } from '@nuxt/ui'
import { UBadge, UButton } from '#components'
import { PERMISSIONS } from '~/config/permissions'

definePageMeta({
  layout: 'default',
})

const { getTasks, deleteTask } = useTasks()
const { currentUserId, hasPermission } = usePermissions()
const { getPlatforms } = usePlatforms()

// 获取平台列表用于过滤
const { data: platforms } = getPlatforms()

// 分页和过滤
const currentPage = ref(1)
const pageSize = ref(10)
const searchQuery = ref('')
const selectedPlatformId = ref<number | string>('all')
const selectedStatus = ref('all')
const selectedDataSource = ref<string | undefined>()
const refreshing = ref(false)

// 获取任务列表
const params = computed(() => ({
  page: currentPage.value,
  page_size: pageSize.value,
  search: searchQuery.value || undefined,
  ...(selectedPlatformId.value !== 'all' ? { platform_id: selectedPlatformId.value } : {}),
  ...(selectedStatus.value !== 'all' ? { status: selectedStatus.value } : {}),
  data_source: selectedDataSource.value,
}))

const { data: tasksData, pending: loading, refresh } = getTasks(params)

const tasks = computed(() => tasksData.value?.items || [])
const total = computed(() => tasksData.value?.total || 0)

// 刷新列表
const handleRefresh = async () => {
  refreshing.value = true
  await refresh()
  refreshing.value = false
}

// 删除任务
const handleDelete = async (task: DataTaskWithRelations) => {
  const { $confirm } = useNuxtApp()
  const confirmed = await $confirm({
    title: '删除任务',
    message: `确定要删除任务 "${task.name}" 吗？此操作不可恢复，将同时删除所有相关的原文和评论数据。`,
    confirmText: '删除',
    cancelText: '取消',
    type: 'error',
  })

  if (!confirmed) return

  try {
    await deleteTask(task.id)
    await handleRefresh()
  } catch {
    // error handled by apiRequest
  }
}

// 格式化日期
const formatDateTime = (dateStr: string) => {
  return new Date(dateStr).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// 任务状态颜色
const getStatusColor = (status: string) => {
  const colors: Record<string, string> = {
    pending: 'neutral',
    accepted: 'neutral',
    running: 'info',
    probe_ready: 'warning',
    approved: 'info',
    completed: 'success',
    failed: 'error',
  }
  return colors[status] || 'neutral'
}

// 任务状态文本
const getStatusText = (status: string) => {
  const texts: Record<string, string> = {
    pending: '待处理',
    accepted: '已接单',
    running: '运行中',
    probe_ready: '探测完成',
    approved: '待续采',
    completed: '已完成',
    failed: '失败',
  }
  return texts[status] || status
}

// 分析状态颜色
const getAnalysisColor = (status: string | null) => {
  if (!status) return 'neutral'
  const colors: Record<string, string> = {
    pending: 'neutral',
    processing: 'info',
    completed: 'success',
    failed: 'error',
  }
  return colors[status] || 'neutral'
}

// 分析状态文本
const getAnalysisText = (status: string | null) => {
  if (!status) return '-'
  const texts: Record<string, string> = {
    pending: '待分析',
    processing: '分析中',
    completed: '分析完成',
    failed: '分析失败',
  }
  return texts[status] || status
}

// 过滤选项
const statusOptions = [
  { label: '全部状态', value: 'all' },
  { label: '待处理', value: 'pending' },
  { label: '已接单', value: 'accepted' },
  { label: '运行中', value: 'running' },
  { label: '已完成', value: 'completed' },
  { label: '失败', value: 'failed' },
]

// 表格列定义 - 使用 computed 以避免 SSR 水合问题
const columns = computed<TableColumn<DataTaskWithRelations>[]>(() => {
  const Badge = UBadge as Component
  const Button = UButton as Component

  return [
    {
      accessorKey: 'id',
      header: 'ID',
      meta: { class: { th: 'w-12', td: 'w-12' } },
      cell: ({ row }) => h('span', { class: 'text-xs text-gray-500 font-mono' }, row.original.id),
    },
    {
      accessorKey: 'name',
      header: '任务名称',
      meta: { class: { th: 'w-[158px]', td: 'w-[158px] whitespace-normal' } },
      cell: ({ row }) => h('div', { class: 'font-medium leading-snug line-clamp-2', title: row.original.name }, row.original.name),
    },
    {
      accessorKey: 'keywords',
      header: '关键词',
      meta: { class: { th: 'w-[130px]', td: 'w-[130px] whitespace-normal' } },
      cell: ({ row }) =>
        h(
          'div',
          { class: 'text-sm text-gray-600 dark:text-gray-400 leading-snug line-clamp-2', title: row.original.keywords || '' },
          row.original.keywords || '-',
        ),
    },
    {
      accessorKey: 'monitor_name',
      header: '所属项目',
      meta: { class: { th: 'w-[124px]', td: 'w-[124px] whitespace-normal' } },
      cell: ({ row }) => {
        if (!row.original.monitor_name || !row.original.monitor_id) {
          return h('span', { class: 'text-gray-400' }, '-')
        }
        return h(Button, {
          variant: 'link',
          size: 'xs',
          class: 'p-0 font-normal w-full text-left whitespace-normal leading-snug line-clamp-2',
          title: row.original.monitor_name,
          to: `/social-media/monitors/${row.original.monitor_id}`,
        }, () => row.original.monitor_name)
      },
    },
    {
      accessorKey: 'platform_name',
      header: '平台',
      meta: { class: { th: 'w-[60px]', td: 'w-[60px]' } },
      cell: ({ row }) => h(Badge, { variant: 'subtle', size: 'xs' }, () => row.original.platform_name || '-'),
    },
    {
      accessorKey: 'phase',
      header: '阶段',
      meta: { class: { th: 'w-[60px]', td: 'w-[60px]' } },
      cell: ({ row }) => {
        const phase = row.original.phase
        const text = phase === 'probe' ? '探测' : phase === 'collect' ? '全量' : '-'
        const color = phase === 'probe' ? 'info' : phase === 'collect' ? 'warning' : 'neutral'
        return h(Badge, { color, size: 'xs', variant: 'subtle' }, () => text)
      },
    },
    {
      accessorKey: 'status',
      header: '状态',
      meta: { class: { th: 'w-[60px]', td: 'w-[60px]' } },
      cell: ({ row }) => {
        const collectBadge = h(Badge, {
          color: getStatusColor(row.original.status),
          variant: 'solid',
          size: 'xs',
        }, () => getStatusText(row.original.status))

        const s = row.original.aggregation_status
        if (!s) return collectBadge

        const analysisBadge = h(Badge, {
          color: getAnalysisColor(s),
          variant: 'subtle',
          size: 'xs',
        }, () => getAnalysisText(s))

        return h('div', { class: 'flex flex-wrap items-center gap-1' }, [collectBadge, analysisBadge])
      },
    },
    {
      accessorKey: 'stats',
      header: '采集量',
      meta: { class: { th: 'w-[100px]', td: 'w-[100px] overflow-hidden' } },
      cell: ({ row }) => h(
        'span',
        { class: 'text-sm text-gray-600 dark:text-gray-400 whitespace-nowrap' },
        `${row.original.posts_count} 原 / ${row.original.comments_count} 评`,
      ),
    },
    {
      accessorKey: 'created_at',
      header: '创建时间',
      meta: { class: { th: 'w-[112px]', td: 'w-[112px]' } },
      cell: ({ row }) => h('span', { class: 'text-sm text-gray-600 dark:text-gray-400 whitespace-nowrap' }, formatDateTime(row.original.created_at)),
    },
    {
      accessorKey: 'actions',
      header: '操作',
      meta: { class: { th: 'w-[120px]', td: 'w-[120px]' } },
      cell: ({ row }) => h('div', { class: 'flex items-center gap-1' }, [
        h(Button, {
          size: 'xs',
          variant: 'ghost',
          icon: 'i-heroicons-eye',
          to: `/social-media/tasks/${row.original.id}`,
        }, () => '查看'),
        row.original.status === 'pending' && row.original.data_source === 'local_upload'
          ? h(Button, {
              size: 'xs',
              variant: 'ghost',
              icon: 'i-heroicons-arrow-up-tray',
              color: 'info',
              to: `/social-media/tasks/${row.original.id}/upload`,
            }, () => '上传')
          : null,
        (hasPermission(PERMISSIONS.SOCIAL_TASK_DELETE) || row.original.user_id === currentUserId.value)
          ? h(Button, {
              size: 'xs',
              variant: 'ghost',
              icon: 'i-heroicons-trash',
              color: 'error',
              onClick: () => handleDelete(row.original),
            }, () => '删除')
          : null,
      ].filter(Boolean)),
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
          社媒采集
        </h1>
        <p class="text-gray-600 dark:text-gray-400 mt-1">
          管理所有社交媒体采集任务
        </p>
      </div>

      <div class="flex items-center gap-3">
        <UButton
          icon="i-heroicons-plus"
          to="/social-media/tasks/create"
        >
          新建任务
        </UButton>
        <UButton
          variant="ghost"
          icon="i-heroicons-arrow-path"
          :loading="refreshing"
          @click="handleRefresh"
        >
          刷新
        </UButton>
      </div>
    </div>

    <!-- 任务列表卡片 -->
    <UCard>
      <template #header>
        <div class="flex items-center justify-between gap-4">
          <h2 class="text-lg font-semibold">
            任务列表
          </h2>

          <div class="flex items-center gap-3">
            <UInput
              v-model="searchQuery"
              placeholder="搜索任务名称或关键词..."
              icon="i-heroicons-magnifying-glass"
              class="w-60"
            />

            <USelect
              v-model="selectedPlatformId"
              :items="[
                { label: '全部平台', value: 'all' },
                ...(platforms?.map(p => ({ label: p.name, value: p.id })) || [])
              ]"
              value-key="value"
              placeholder="平台"
              class="w-36"
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
              加载任务列表中...
            </p>
          </div>
        </template>

        <UTable
          :data="tasks"
          :columns="columns"
          :loading="loading"
          class="w-full"
          :ui="{ base: 'w-full table-fixed' }"
        />
      </ClientOnly>

      <!-- 分页 -->
      <template #footer>
        <ClientOnly>
          <template #fallback>
            <div class="flex justify-between items-center">
              <div class="h-4 bg-gray-200 rounded w-32 animate-pulse" />
              <div class="h-8 bg-gray-200 rounded w-64 animate-pulse" />
            </div>
          </template>

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

