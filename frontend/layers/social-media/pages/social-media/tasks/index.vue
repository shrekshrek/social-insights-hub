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
    running: 'info',
    completed: 'success',
    failed: 'error',
  }
  return colors[status] || 'neutral'
}

// 任务状态文本
const getStatusText = (status: string) => {
  const texts: Record<string, string> = {
    pending: '待处理',
    running: '运行中',
    completed: '已完成',
    failed: '失败',
  }
  return texts[status] || status
}

// 过滤选项
const statusOptions = [
  { label: '全部', value: undefined },
  { label: '待处理', value: 'pending' },
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
      accessorKey: 'name',
      header: '任务名称',
      cell: ({ row }) => h('span', { class: 'font-medium' }, row.original.name),
    },
    {
      accessorKey: 'project_name',
      header: '所属项目',
      cell: ({ row }) => {
        if (!row.original.project_name || !row.original.project_id) {
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
      accessorKey: 'platform_name',
      header: '平台',
      cell: ({ row }) => h(Badge, { variant: 'subtle', size: 'xs' }, () => row.original.platform_name || '-'),
    },
    {
      accessorKey: 'status',
      header: '状态',
      cell: ({ row }) => h(Badge, {
        color: getStatusColor(row.original.status),
        variant: 'solid',
        size: 'xs'
      }, () => getStatusText(row.original.status)),
    },
    {
      accessorKey: 'stats',
      header: '数据统计',
      cell: ({ row }) => h('span', { class: 'text-sm text-gray-600 dark:text-gray-400' },
        `${row.original.posts_count} 原文 / ${row.original.comments_count} 评论`
      ),
    },
    {
      accessorKey: 'created_at',
      header: '创建时间',
      cell: ({ row }) => h('span', { class: 'text-sm text-gray-600 dark:text-gray-400' }, formatDateTime(row.original.created_at)),
    },
    {
      accessorKey: 'actions',
      header: '操作',
      cell: ({ row }) => h('div', { class: 'flex items-center gap-2' }, [
        h(Button, {
          size: 'xs',
          variant: 'ghost',
          icon: 'i-heroicons-eye',
          onClick: () => navigateTo(`/social-media/tasks/${row.original.id}`),
        }, () => '查看'),
        row.original.status === 'pending' && row.original.data_source === 'local_upload'
          ? h(Button, {
              size: 'xs',
              variant: 'ghost',
              icon: 'i-heroicons-arrow-up-tray',
              color: 'info',
              onClick: () => navigateTo(`/social-media/tasks/${row.original.id}/upload`),
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
          数据采集任务
        </h1>
        <p class="text-gray-600 dark:text-gray-400 mt-1">
          管理您的社交媒体数据采集任务
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
