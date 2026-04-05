<script setup lang="ts">
import { h, ref, computed, type Component } from 'vue'
import type { TableColumn } from '@nuxt/ui'
import { UBadge, UButton } from '#components'

definePageMeta({
  layout: 'default',
})

const { getTasks, deleteTask } = useTasks()
const { getPlatforms } = usePlatforms()

// 获取平台列表用于过滤
const { data: platforms } = getPlatforms()

// 分页和过滤
const currentPage = ref(1)
const pageSize = ref(20)
const searchQuery = ref('')
const selectedPlatformId = ref<number | undefined>()
const selectedStatus = ref<string | undefined>()
const selectedDataSource = ref<string | undefined>()
const refreshing = ref(false)

// 获取任务列表
const params = computed(() => ({
  page: currentPage.value,
  page_size: pageSize.value,
  search: searchQuery.value || undefined,
  platform_id: selectedPlatformId.value,
  status: selectedStatus.value,
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
  } catch (error) {
    console.error('删除任务失败:', error)
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
  { label: '全部', value: undefined },
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
      meta: { class: { th: 'w-14', td: 'w-14' } },
      cell: ({ row }) => h('span', { class: 'text-xs text-gray-500 font-mono' }, row.original.id),
    },
    {
      accessorKey: 'name',
      header: '任务名称',
      meta: { class: { th: 'w-[200px]', td: 'w-[200px] whitespace-normal' } },
      cell: ({ row }) => h('div', { class: 'font-medium leading-snug line-clamp-2', title: row.original.name }, row.original.name),
    },
    {
      accessorKey: 'monitor_name',
      header: '所属项目',
      meta: { class: { th: 'w-[144px]', td: 'w-[144px] whitespace-normal' } },
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
      meta: { class: { th: 'w-[72px]', td: 'w-[72px]' } },
      cell: ({ row }) => h(Badge, { variant: 'subtle', size: 'xs' }, () => row.original.platform_name || '-'),
    },
    {
      accessorKey: 'status',
      header: '状态',
      meta: { class: { th: 'w-[120px]', td: 'w-[120px]' } },
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
      header: '数据统计',
      meta: { class: { th: 'w-[140px]', td: 'w-[140px] overflow-hidden' } },
      cell: ({ row }) => h('span', { class: 'text-sm text-gray-600 dark:text-gray-400 whitespace-nowrap' },
        `${row.original.posts_count} 原文 / ${row.original.comments_count} 评论`
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
      meta: { class: { th: 'w-[128px]', td: 'w-[128px]' } },
      cell: ({ row }) => h('div', { class: 'flex items-center gap-2' }, [
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
        h(Button, {
          size: 'xs',
          variant: 'ghost',
          icon: 'i-heroicons-trash',
          color: 'error',
          onClick: () => handleDelete(row.original),
        }, () => '删除'),
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
          variant="outline"
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

          <div class="flex items-center gap-3 flex-1 max-w-3xl">
            <UInput
              v-model="searchQuery"
              placeholder="搜索任务名称或关键词..."
              icon="i-heroicons-magnifying-glass"
              class="flex-1"
            />

            <USelect
              v-model="selectedPlatformId"
              :items="[
                { label: '全部平台', value: undefined },
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

